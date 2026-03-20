from __future__ import annotations

from app.repo_to_agent.internal_runner import run_specialist_with_internal_runner
from app.repo_to_agent.repo_classifier import classify_repo_type
from app.repo_to_agent.templates import AGENT_DESIGNER_TEMPLATE
from app.repo_to_agent.tool_discovery import discover_tools_from_repo


def test_repo_classifier_docs_tutorial() -> None:
    scout = {
        "repo_summary": "30 days of Python tutorial content.",
        "important_files": ["README.md", "docs/usage.md", "docs/lesson1.md"],
        "language_hints": [],
        "framework_hints": [],
    }
    arch = {
        "languages": [],
        "frameworks": [],
        "services": [],
        "entrypoints": [],
        "integrations": [],
        "key_paths": ["docs/", "README.md"],
    }
    r = classify_repo_type(scout, arch)
    assert r.repo_type == "docs_tutorial"
    assert r.confidence >= 0.2


def test_repo_classifier_automation_scripts() -> None:
    scout = {
        "repo_summary": "A collection of automation scripts.",
        "important_files": ["scripts/run.py", "Makefile", "bin/doit"],
        "language_hints": ["Python"],
        "framework_hints": [],
    }
    arch = {
        "languages": ["Python"],
        "frameworks": [],
        "services": [],
        "entrypoints": ["scripts/run.py"],
        "integrations": [],
        "key_paths": ["scripts/", "bin/", "Makefile"],
    }
    r = classify_repo_type(scout, arch)
    assert r.repo_type == "automation_scripts"


def test_repo_classifier_library_framework() -> None:
    scout = {
        "repo_summary": "A Python library for solar modeling.",
        "important_files": ["pyproject.toml", "src/pvlib/__init__.py", "tests/test_core.py"],
        "language_hints": ["Python"],
        "framework_hints": [],
    }
    arch = {
        "languages": ["Python"],
        "frameworks": [],
        "services": [],
        "entrypoints": [],
        "integrations": [],
        "key_paths": ["src/", "pvlib/", "tests/"],
    }
    r = classify_repo_type(scout, arch)
    assert r.repo_type == "library_framework"


def test_repo_classifier_explicit_agent_markers_win() -> None:
    scout = {
        "repo_summary": "Customer support agent demo.",
        "important_files": ["agent.json", "prompts/system_prompt.md", "README.md"],
        "language_hints": ["Python"],
        "framework_hints": [],
    }
    arch = {
        "languages": ["Python"],
        "frameworks": [],
        "services": [],
        "entrypoints": ["python-backend/main.py"],
        "integrations": [],
        "key_paths": ["agent.json", "prompts/system_prompt.md", "python-backend/"],
    }
    r = classify_repo_type(scout, arch)
    assert r.repo_type == "explicit_agent"
    assert any("agent.json" in e for e in r.evidence) or r.confidence >= 0.2


def test_internal_runner_agent_designer_primitive_varies_by_repo_type() -> None:
    # docs -> transform
    docs_payload = {
        "scout": {"repo_summary": "Tutorial docs.", "important_files": ["README.md", "docs/intro.md"]},
        "architecture": {"languages": [], "frameworks": [], "services": [], "entrypoints": [], "integrations": [], "key_paths": ["docs/"]},
    }
    docs_out = run_specialist_with_internal_runner(AGENT_DESIGNER_TEMPLATE, docs_payload)
    assert docs_out["draft_agent_spec"]["primitive"] == "transform"

    # scripts -> extract
    scripts_payload = {
        "scout": {"repo_summary": "Automation scripts.", "important_files": ["scripts/run.py", "Makefile"]},
        "architecture": {"languages": ["Python"], "frameworks": [], "services": [], "entrypoints": ["scripts/run.py"], "integrations": [], "key_paths": ["scripts/", "Makefile"]},
    }
    scripts_out = run_specialist_with_internal_runner(AGENT_DESIGNER_TEMPLATE, scripts_payload)
    assert scripts_out["draft_agent_spec"]["primitive"] == "extract"

    # library -> classify
    lib_payload = {
        "scout": {"repo_summary": "A Python library.", "important_files": ["pyproject.toml", "src/lib/__init__.py", "tests/test_a.py"]},
        "architecture": {"languages": ["Python"], "frameworks": [], "services": [], "entrypoints": [], "integrations": [], "key_paths": ["src/", "tests/"]},
    }
    lib_out = run_specialist_with_internal_runner(AGENT_DESIGNER_TEMPLATE, lib_payload)
    assert lib_out["draft_agent_spec"]["primitive"] == "classify"


def test_bundle_bias_matches_repo_type_when_scores_close() -> None:
    # docs/tutorial should prefer no_tools_writer
    docs_scout = {"repo_summary": "Docs-heavy tutorial.", "important_files": ["README.md", "docs/guide.md"], "language_hints": [], "framework_hints": []}
    docs_arch = {"languages": [], "frameworks": [], "services": [], "entrypoints": [], "integrations": [], "key_paths": ["docs/", "README.md"]}
    out_docs = discover_tools_from_repo(docs_scout, docs_arch)
    assert out_docs["bundle_id"] == "no_tools_writer"

    # automation scripts should prefer repo_to_agent (best available bundle today)
    auto_scout = {"repo_summary": "Automation scripts.", "important_files": ["scripts/run.py", "Makefile"], "language_hints": ["Python"], "framework_hints": []}
    auto_arch = {"languages": ["Python"], "frameworks": [], "services": [], "entrypoints": ["scripts/run.py"], "integrations": [], "key_paths": ["scripts/", "Makefile"]}
    out_auto = discover_tools_from_repo(auto_scout, auto_arch)
    assert out_auto["bundle_id"] in ("repo_to_agent", "github_reader")


def test_repo_classifier_amazing_python_scripts_regression() -> None:
    """
    Regression: https://github.com/avinashkranjan/Amazing-Python-Scripts
    This is a script-heavy automation repo, not a docs/tutorial repo.
    """
    scout = {
        "repo_summary": "Amazing Python Scripts: collection of useful Python scripts and examples.",
        "important_files": ["README.md", "CONTRIBUTING.md", "LICENSE"],
        "language_hints": ["Python"],
        "framework_hints": [],
    }
    # Simulate a large flat-ish script repo surface: lots of .py across many folders,
    # with some markdown alongside.
    key_paths = ["README.md"]
    key_paths += [f"scripts_{i}.py" for i in range(10)]
    key_paths += [f"Category{i}/tool_{j}.py" for i in range(8) for j in range(5)]
    key_paths += [f"Category{i}/README.md" for i in range(6)]
    arch = {
        "languages": ["Python"],
        "frameworks": [],
        "services": [],
        "entrypoints": ["scripts_0.py"],
        "integrations": [],
        "key_paths": key_paths,
    }
    r = classify_repo_type(scout, arch)
    # Must not classify as docs_tutorial.
    assert r.repo_type != "docs_tutorial"
    # Prefer automation_scripts for this shape.
    assert r.scores.get("automation_scripts", 0.0) >= r.scores.get("docs_tutorial", 0.0)
    assert r.repo_type == "automation_scripts"

    # And downstream primitive should not be transform.
    payload = {"scout": scout, "architecture": arch}
    out = run_specialist_with_internal_runner(AGENT_DESIGNER_TEMPLATE, payload)
    assert out["draft_agent_spec"]["primitive"] != "transform"
    assert out["draft_agent_spec"]["primitive"] == "extract"


def test_repo_classifier_pvlib_python_regression() -> None:
    """
    Regression: https://github.com/pvlib/pvlib-python
    This is a structured Python library/framework repo, not an automation scripts repo.
    """
    scout = {
        "repo_summary": "pvlib-python: a Python library for simulating the performance of photovoltaic energy systems.",
        "important_files": [
            "setup.py",
            "pyproject.toml",
            "src/pvlib/__init__.py",
            "src/pvlib/model.py",
            "tests/test_model.py",
        ],
        "language_hints": ["Python"],
        "framework_hints": [],
    }
    arch = {
        "languages": ["Python"],
        "frameworks": [],
        "services": [],
        "entrypoints": [],
        "integrations": [],
        "key_paths": ["setup.py", "pyproject.toml", "src/", "src/pvlib/", "tests/"],
    }
    # Simulate repo_tool_discovery treating setup.py as a python_script tool.
    # In real runs this arrives as `source_path` rather than `path`.
    discovered_repo_tools = [
        {"tool_type": "python_script", "source_path": "setup.py"},
    ]
    r = classify_repo_type(scout, arch, discovered_repo_tools=discovered_repo_tools)
    # Must not classify as automation_scripts.
    assert r.repo_type != "automation_scripts"
    # Prefer library_framework for this shape.
    assert r.repo_type == "library_framework"
    assert r.scores.get("library_framework", 0.0) >= r.scores.get("automation_scripts", 0.0)

    # And downstream primitive for a library-style payload should not be extract.
    payload = {"scout": scout, "architecture": arch}
    out = run_specialist_with_internal_runner(AGENT_DESIGNER_TEMPLATE, payload)
    assert out["draft_agent_spec"]["primitive"] != "extract"


def test_repo_classifier_pvlib_python_regression_shallow_shape() -> None:
    """
    Regression: pvlib-python shallow architecture shape.
    This mirrors the live payload where only packaging + package dir names are present
    (no representative .py paths surfaced in key_paths yet).
    """
    scout = {
        "repo_summary": "pvlib-python: a Python library for simulating the performance of photovoltaic energy systems.",
        "important_files": ["setup.py", "pyproject.toml", "README.md"],
        "language_hints": [],
        "framework_hints": [],
    }
    arch = {
        "languages": [],
        "frameworks": [],
        "services": [],
        "entrypoints": [],
        "integrations": [],
        # Shallow: package dir name and tests dir exist, but no .py paths.
        "key_paths": ["setup.py", "pyproject.toml", "pvlib", "tests"],
    }
    discovered_repo_tools = [
        {"tool_type": "python_script", "source_path": "setup.py"},
    ]
    r = classify_repo_type(scout, arch, discovered_repo_tools=discovered_repo_tools)
    assert r.repo_type == "library_framework"
    assert r.scores.get("library_framework", 0.0) > r.scores.get("automation_scripts", 0.0)

