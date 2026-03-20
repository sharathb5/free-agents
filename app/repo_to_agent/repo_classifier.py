"""
Repo classification (purpose-aware) for repo-to-agent.

This is intentionally deterministic and lightweight: it uses only the already-produced
RepoScoutOutput + RepoArchitectureOutput signals (paths, language/framework hints, summary)
and optional explicit markers from earlier deterministic inspection (agent.json/system prompt).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import os
import re


RepoType = str  # "explicit_agent" | "agent_framework" | "automation_scripts" | "docs_tutorial" | "library_framework" | "unknown"


@dataclass(frozen=True)
class RepoTypeResult:
    repo_type: RepoType
    confidence: float  # 0.0-1.0
    evidence: List[str]
    scores: Dict[str, float]


def _as_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if x is not None and str(x).strip()]
    s = str(v).strip()
    return [s] if s else []


def _norm_paths(paths: List[str]) -> List[str]:
    return [p.strip().replace("\\", "/") for p in paths if isinstance(p, str) and p.strip()]


def _count_if(paths_lower: List[str], pred) -> int:
    return sum(1 for p in paths_lower if pred(p))


def classify_repo_type(
    scout: Any,
    architecture: Any,
    *,
    has_agent_json: bool = False,
    has_system_prompt: bool = False,
    discovered_repo_tools: Optional[List[Dict[str, Any]]] = None,
) -> RepoTypeResult:
    """
    Classify repository into a small purpose-aware type.

    Precedence note:
      - This classifier is *advisory*. Explicit agent markers (agent.json/system prompt)
        should be treated as stronger evidence in downstream decision policies.
    """
    scout_d = scout.model_dump() if hasattr(scout, "model_dump") else scout if isinstance(scout, dict) else {}
    arch_d = architecture.model_dump() if hasattr(architecture, "model_dump") else architecture if isinstance(architecture, dict) else {}

    important = _norm_paths(_as_list(scout_d.get("important_files")))
    key_paths = _norm_paths(_as_list(arch_d.get("key_paths")))
    entrypoints = _norm_paths(_as_list(arch_d.get("entrypoints")))
    languages = [x.lower() for x in _as_list(arch_d.get("languages") or scout_d.get("language_hints"))]
    frameworks = [x.lower() for x in _as_list(arch_d.get("frameworks") or scout_d.get("framework_hints"))]
    repo_summary = str(scout_d.get("repo_summary") or "")

    all_paths = important + key_paths + entrypoints
    paths_lower = [p.lower() for p in all_paths]

    # --- Raw feature counts ---
    md_count = _count_if(paths_lower, lambda p: p.endswith(".md") or p.endswith(".markdown"))
    md_like_count = _count_if(
        paths_lower,
        lambda p: p.endswith((".md", ".markdown", ".rst", ".txt")),
    )
    code_count = _count_if(
        paths_lower,
        lambda p: p.endswith((".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".rb", ".php", ".c", ".cpp")),
    )
    py_file_count = _count_if(paths_lower, lambda p: p.endswith(".py"))
    # Shallow python scripts are a strong proxy for "script collection" repos:
    # e.g. root-level or one-folder-deep scripts.
    py_shallow_count = _count_if(
        paths_lower,
        lambda p: p.endswith(".py") and p.count("/") <= 1,
    )
    py_mid_shallow_count = _count_if(
        paths_lower,
        lambda p: p.endswith(".py") and p.count("/") <= 2,
    )
    init_py_count = _count_if(paths_lower, lambda p: p.endswith("__init__.py"))
    top_level_pkg_dir_count = _count_if(
        paths_lower,
        lambda p: (
            p
            and p.count("/") == 0
            and "." not in p
            and p not in {"src", "tests", "test", "docs", "scripts", "bin", "cli", "tools", "tasks", "automation", "ci"}
        ),
    )
    has_pkg_dirs = top_level_pkg_dir_count > 0
    doc_dir_count = _count_if(paths_lower, lambda p: p.startswith("docs/") or "/docs/" in p)
    script_dir_count = _count_if(
        paths_lower,
        lambda p: p.startswith(("scripts/", "bin/", "cli/", "tools/", "tasks/", "automation/"))
        or any(seg in p for seg in ("/scripts/", "/bin/", "/cli/", "/tools/", "/tasks/", "/automation/")),
    )
    script_ext_count = _count_if(paths_lower, lambda p: p.endswith((".sh", ".bash", ".ps1", ".py")))
    makefile_present = any(p.endswith(("makefile", "gnumakefile")) for p in paths_lower)
    docker_present = any(p.endswith(("dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")) for p in paths_lower)

    py_pkg_present = any(p.endswith(("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")) for p in paths_lower)
    node_pkg_present = any(p.endswith(("package.json", "pnpm-lock.yaml", "yarn.lock")) for p in paths_lower)
    src_present = any(p.startswith("src/") or "/src/" in p for p in paths_lower)
    tests_present = any(p.startswith(("tests/", "test/")) or "/tests/" in p or "/test/" in p for p in paths_lower)

    summary_lower = repo_summary.lower()
    # Normalize separators so names like "30-Days-Of-Python" still trigger
    # tutorial-style keyword checks.
    summary_words = re.sub(r"[-_/]+", " ", summary_lower)
    has_tutorial_terms = any(k in summary_lower for k in ("tutorial", "learn", "days of", "course", "examples", "beginner"))
    if not has_tutorial_terms:
        has_tutorial_terms = any(k in summary_words for k in ("tutorial", "learn", "days of", "course", "examples", "beginner"))
    has_agent_terms = any(k in summary_lower for k in ("agent", "multi-agent", "orchestration", "assistant", "tool calling"))
    has_framework_terms = any(k in summary_lower for k in ("sdk", "framework", "library", "package", "api"))

    explicit_marker_paths = any(
        p in paths_lower
        for p in (
            "agent.json",
            "prompts/system_prompt.md",
        )
    )

    # --- Score each class ---
    scores: Dict[str, float] = {
        "explicit_agent": 0.0,
        "agent_framework": 0.0,
        "automation_scripts": 0.0,
        "docs_tutorial": 0.0,
        "library_framework": 0.0,
        "unknown": 0.05,
    }
    evidence: Dict[str, List[str]] = {k: [] for k in scores.keys()}

    # --- Library structure detection ---
    # This is intentionally lightweight: we only use already-supplied `key_paths`/`important_files`.
    # If packaging metadata exists and we also see a likely Python package directory name (e.g., "pvlib"),
    # this repo is far more likely to be a library/framework than an automation scripts collection.
    has_library_structure = py_pkg_present and (src_present or tests_present or has_pkg_dirs or init_py_count > 0)

    # explicit_agent: hard evidence first
    if has_agent_json or has_system_prompt or explicit_marker_paths:
        scores["explicit_agent"] += 2.5
        if has_agent_json:
            evidence["explicit_agent"].append("marker:agent.json")
        if has_system_prompt:
            evidence["explicit_agent"].append("marker:prompts/system_prompt.md")
        if explicit_marker_paths:
            evidence["explicit_agent"].append("paths:explicit_agent_markers")
    # agent terms in summary/framework hints can support
    if has_agent_terms or any("agent" in f for f in frameworks):
        scores["explicit_agent"] += 0.7
        evidence["explicit_agent"].append("text:agent_terms")

    # docs/tutorial: docs-dominant and/or tutorial terms
    if md_count + doc_dir_count > 0:
        docs_density = (md_count + doc_dir_count) / max(1, len(paths_lower))
        if docs_density >= 0.35:
            scores["docs_tutorial"] += 1.2
            evidence["docs_tutorial"].append(f"density:docs={docs_density:.2f}")
        else:
            scores["docs_tutorial"] += 0.4
            evidence["docs_tutorial"].append("paths:docs_present")
    if has_tutorial_terms:
        scores["docs_tutorial"] += 0.8
        evidence["docs_tutorial"].append("text:tutorial_terms")
    if code_count == 0 and md_count > 0:
        scores["docs_tutorial"] += 0.6
        evidence["docs_tutorial"].append("shape:docs_only")
    # If code strongly dominates docs, dampen docs_tutorial so script-heavy repos don't get misclassified.
    docsish = md_like_count + doc_dir_count
    if code_count >= 18 and code_count >= 2 * max(1, docsish):
        scores["docs_tutorial"] *= 0.35
        evidence["docs_tutorial"].append("dampen:code_dominates_docs")

    # automation/scripts: script dirs + entrypoints + automation markers
    if script_dir_count > 0:
        # If we already see strong library/package structure, keep script-dir evidence weaker.
        script_dir_factor = 1.0
        if has_library_structure and script_dir_count <= 2:
            script_dir_factor = 0.35
        scores["automation_scripts"] += script_dir_factor * min(1.3, 0.25 * script_dir_count)
        evidence["automation_scripts"].append(f"paths:script_dirs={script_dir_count}")
    if makefile_present:
        scores["automation_scripts"] += 0.7
        evidence["automation_scripts"].append("file:Makefile")
    if docker_present:
        scores["automation_scripts"] += 0.3
        evidence["automation_scripts"].append("file:Docker")
    if entrypoints:
        scores["automation_scripts"] += 0.35
        evidence["automation_scripts"].append("arch:entrypoints_present")
    # Many scripts across surfaced paths (rough proxy)
    if script_ext_count >= 8:
        scores["automation_scripts"] += 0.8
        evidence["automation_scripts"].append(f"count:scripts_ext={script_ext_count}")
    elif script_ext_count >= 3 and script_dir_count > 0:
        scores["automation_scripts"] += 0.4
        evidence["automation_scripts"].append(f"count:scripts_ext={script_ext_count}")
    # Python script collection boost (covers repos that don't use scripts/ bin/ but have many .py files).
    if py_file_count >= 30:
        scores["automation_scripts"] += 1.35
        evidence["automation_scripts"].append(f"count:py_files={py_file_count}")
    elif py_file_count >= 15:
        scores["automation_scripts"] += 0.8
        evidence["automation_scripts"].append(f"count:py_files={py_file_count}")
    # Shallow layout boost: lots of root/near-root scripts typically implies "Amazing Scripts" style repos.
    if py_shallow_count >= 8:
        scores["automation_scripts"] += 0.7
        evidence["automation_scripts"].append(f"shape:py_shallow={py_shallow_count}")
    elif py_mid_shallow_count >= 20 and not src_present and not tests_present:
        scores["automation_scripts"] += 0.45
        evidence["automation_scripts"].append(f"shape:py_mid_shallow={py_mid_shallow_count}")
    # If it's a python-heavy repo without packaging metadata, it's more likely a scripts collection than a library.
    if py_file_count >= 15 and not py_pkg_present and not src_present:
        scores["automation_scripts"] += 0.3
        evidence["automation_scripts"].append("shape:python_no_packaging")
    # Optional boost: if upstream repo tool discovery found multiple script entrypoints.
    non_packaging_script_like = 0
    if discovered_repo_tools:
        script_like = 0
        packaging_script_like = 0
        for t in discovered_repo_tools:
            # Accept both dicts and objects (e.g. Pydantic models from repo_tool_discovery).
            if isinstance(t, dict):
                tt_raw = t.get("tool_type")
                path_raw = (
                    t.get("path")
                    or t.get("file_path")
                    or t.get("source_path")
                    or t.get("name")
                )
            else:
                tt_raw = getattr(t, "tool_type", None)
                path_raw = (
                    getattr(t, "path", None)
                    or getattr(t, "file_path", None)
                    or getattr(t, "source_path", None)
                    or getattr(t, "name", None)
                )
            tt = str(tt_raw or "").strip().lower()
            if tt in ("python_script", "script", "cli_script"):
                script_like += 1
                path_lower = str(path_raw or "").strip().lower()
                # Heuristic: treat setup.py and close cousins as packaging, not automation scripts.
                if path_lower.endswith("setup.py") or "/setup.py" in path_lower:
                    packaging_script_like += 1
                else:
                    non_packaging_script_like += 1
        if script_like >= 1:
            evidence["automation_scripts"].append(f"tools:script_like={script_like}")
        if packaging_script_like > 0 and py_pkg_present:
            evidence["library_framework"].append("tools:packaging_script_detected")
        # Key fix for repos like Amazing-Python-Scripts: key_paths may be directory-heavy (no extensions),
        # but discovered tools prove executable/script content exists. Only count non-packaging scripts.
        effective_scripts = non_packaging_script_like
        if effective_scripts >= 3:
            scores["automation_scripts"] += 1.0
        elif effective_scripts >= 2:
            scores["automation_scripts"] += 0.85
        elif effective_scripts == 1:
            # A single script-like tool is only weak evidence on its own.
            scores["automation_scripts"] += 0.35
        # If we only have a weak docs signal, dampen it so scripts aren't misclassified as docs.
        if effective_scripts >= 1 and scores["docs_tutorial"] > 0 and scores["docs_tutorial"] <= 0.6:
            scores["docs_tutorial"] *= 0.5
            evidence["docs_tutorial"].append("dampen:tool_suggests_scripts")

    # Temporary debug logging (enable with REPO_CLASSIFIER_DEBUG=1).
    # Logs key signals to help diagnose runtime mismatches.
    if os.getenv("REPO_CLASSIFIER_DEBUG", "").strip().lower() in ("1", "true", "yes"):
        try:
            # Keep logs single-line and low-volume.
            print(
                "repo_classifier_debug",
                {
                    "py_pkg_present": py_pkg_present,
                    "src_present": src_present,
                    "tests_present": tests_present,
                    "script_dir_count": script_dir_count,
                    "py_file_count": py_file_count,
                    "md_like_count": md_like_count,
                    "code_count": code_count,
                    "script_like": int(locals().get("script_like", 0)),
                    "packaging_script_like": int(locals().get("packaging_script_like", 0)),
                    "non_packaging_script_like": int(locals().get("non_packaging_script_like", 0)),
                },
            )
        except Exception:
            pass

    # library/framework: packaging metadata + src/tests + code-heavy, not docs-only, not scripts-dominant
    if (py_pkg_present or node_pkg_present) and (src_present or tests_present) and (code_count > 0 or languages):
        base = 1.1
        if py_pkg_present:
            base += 0.4
            evidence["library_framework"].append("pkg:python")
        if node_pkg_present:
            base += 0.3
            evidence["library_framework"].append("pkg:node")
        if src_present:
            base += 0.4
            evidence["library_framework"].append("paths:src/")
        if tests_present:
            base += 0.25
            evidence["library_framework"].append("paths:tests/")
        if has_framework_terms:
            base += 0.2
            evidence["library_framework"].append("text:framework_terms")
        # Extra nudge for well-structured Python libraries with both src/ and tests/.
        if py_pkg_present and src_present and tests_present:
            base += 0.25
            evidence["library_framework"].append("shape:src+tests_library")
        # Packaged libraries without obvious automation dirs are unlikely to be pure scripts repos.
        if py_pkg_present and src_present and not script_dir_count and not makefile_present and not docker_present:
            base += 0.2
            evidence["library_framework"].append("shape:packaged_no_automation_dirs")
        scores["library_framework"] += base

    # Strong library override: packaging + package directory name / __init__.py
    # This handles shallow architectures where we don't yet see many .py paths.
    if py_pkg_present and (has_pkg_dirs or init_py_count > 0) and not has_agent_json and not has_system_prompt:
        # Ensure libraries out-rank single-tool automation evidence like `setup.py` being discovered as script-like.
        scores["library_framework"] += 2.2
        evidence["library_framework"].append(
            f"override:pkg_structure=(top_pkg_dirs={top_level_pkg_dir_count},init_py={init_py_count})"
        )
        # Damp automation when package structure is clear but runnable script evidence is weak.
        if scores["automation_scripts"] > 0:
            scores["automation_scripts"] *= 0.55
            evidence["automation_scripts"].append("dampen:clear_python_package_structure")
    # If scripts appear dominant, dampen library score slightly; but if library structure is strong
    # and script evidence is thin (e.g. only setup.py), dampen automation instead.
    if scores["automation_scripts"] >= 1.4:
        scores["library_framework"] *= 0.75
    if (
        py_pkg_present
        and (src_present or tests_present)
        and scores["library_framework"] > 0
        and scores["automation_scripts"] > 0
        and script_dir_count == 0
        and non_packaging_script_like <= 1
    ):
        scores["automation_scripts"] *= 0.6
        evidence["automation_scripts"].append("dampen:library_structure_strong")

    # agent_framework: agent-ish + library-like packaging, or frameworks mention agents
    if (has_agent_terms or any("agent" in f for f in frameworks)) and (py_pkg_present or node_pkg_present):
        scores["agent_framework"] += 1.3
        evidence["agent_framework"].append("mix:agent_terms+packaging")
    if any(k in summary_lower for k in ("sdk", "framework")) and has_agent_terms:
        scores["agent_framework"] += 0.6
        evidence["agent_framework"].append("text:agent_sdk_framework")
    if any(seg in " ".join(paths_lower) for seg in ("src/", "examples/", "docs/")) and (has_agent_terms or any("agent" in f for f in frameworks)):
        scores["agent_framework"] += 0.3
        evidence["agent_framework"].append("shape:src_examples_docs_with_agent_terms")

    # If explicit agent markers exist, keep agent_framework below explicit_agent by default
    if scores["explicit_agent"] >= 2.0 and scores["agent_framework"] > 0:
        scores["agent_framework"] *= 0.6

    # Choose best by score, then stable tie-break.
    best_type: str = "unknown"
    best_score = -1.0
    for k, s in scores.items():
        if s > best_score or (s == best_score and k < best_type):
            best_type = k
            best_score = s

    # Confidence: softmax-ish without importing math heavy; scale by separation.
    sorted_scores = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top = sorted_scores[0][1]
    second = sorted_scores[1][1] if len(sorted_scores) > 1 else 0.0
    margin = max(0.0, top - second)
    confidence = max(0.2, min(0.98, 0.35 + 0.25 * margin + 0.1 * min(3.0, top)))

    # Evidence: only for chosen type, capped for readability.
    chosen_evidence = evidence.get(best_type, [])[:8]
    if not chosen_evidence:
        chosen_evidence = ["no_strong_markers"]

    return RepoTypeResult(
        repo_type=best_type,
        confidence=float(confidence),
        evidence=chosen_evidence,
        scores={k: float(v) for k, v in scores.items()},
    )

