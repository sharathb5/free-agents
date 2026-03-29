"""CLI entry point for the agent-toolbox package."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path

# OpenRouter: one API key for many models (OpenAI, Claude, Gemini, etc.)
OPENROUTER_KEYS_URL = "https://openrouter.ai/keys"
MIN_PYTHON = (3, 10)


def _print_setup_banner(
    preset: str,
    provider: str,
    port: int,
    *,
    for_startup: bool = True,
) -> None:
    """Print setup/LLM instructions. If for_startup, show 'gateway started' line; else show 'Setup' header."""
    provider_note = "no API key required" if provider == "stub" else "API key from .env"
    base = f"http://localhost:{port}"
    print()
    if for_startup:
        print("✅ Agent gateway started — agent preset: {}".format(preset))
    else:
        print("Agent Toolbox — Setup")
        print("Agent preset: {}  |  Provider: {} ({})".format(preset, provider, provider_note))
    if for_startup:
        print("Provider: {} ({})".format(provider, provider_note))
    print()
    print("Docs:     {}/docs".format(base))
    print("Schema:   {}/schema".format(base))
    print("Examples: {}/examples".format(base))
    print()
    print("────────────────────────────────────────────")
    print("Get an API key from OpenRouter (one key for many models):")
    print("   {}".format(OPENROUTER_KEYS_URL))
    print()
    print("Create a .env file in this folder (or edit it if you already have one).")
    print("   Mac/Linux:  nano .env")
    print("   Windows:    notepad .env")
    print()
    print("Copy the block below into .env and replace YOUR_KEY_HERE with your key.")
    print("   Change OPENROUTER_MODEL to use a different model (see openrouter.ai/models).")
    print()
    print("   PROVIDER=openrouter")
    print("   OPENROUTER_API_KEY=YOUR_KEY_HERE")
    print("   OPENROUTER_MODEL=openai/gpt-4o-mini")
    print()
    print("Then restart: stop the server (Ctrl+C) and run agent-toolbox again.")
    print()


def _python_version_str() -> str:
    return ".".join(str(part) for part in sys.version_info[:3])


def _ensure_supported_python() -> None:
    if sys.version_info < MIN_PYTHON:
        print(
            "Error: Python {} detected. agent-toolbox requires Python {}.{}+.".format(
                _python_version_str(),
                MIN_PYTHON[0],
                MIN_PYTHON[1],
            ),
            file=sys.stderr,
        )
        sys.exit(2)


def _print_help() -> None:
    print("Agent Toolbox CLI")
    print()
    print("Usage:")
    print("  agent-toolbox               Start the gateway server")
    print("  agent-toolbox setup         Print setup/env guidance")
    print("  agent-toolbox doctor        Print install/environment diagnostics")
    print("  agent-toolbox bootstrap     Create .venv and install agent-toolbox")
    print("  agent-toolbox bootstrap <venv_dir>")
    print("  agent-toolbox logs tail [--n N]   Tail last N lines of run log (env FREE_AGENTS_LOG_PATH)")
    print("  agent-toolbox logs show <run_id>  Show log lines for a run")
    print("  agent-toolbox deploy --replit   Prepare Replit config + open import URL (same as free-agents)")
    print()


def _logs_tail(n: int = 100) -> None:
    """Print last N lines from FREE_AGENTS_LOG_PATH (default ~/.free_agents/logs.jsonl)."""
    path = os.environ.get("FREE_AGENTS_LOG_PATH")
    if not path:
        path = str(Path.home() / ".free_agents" / "logs.jsonl")
    if not os.path.isfile(path):
        print(f"Log file not found: {path}")
        print("Set FREE_AGENTS_LOG_PATH or run the server with logging enabled to create it.")
        return
    with open(path) as f:
        lines = f.readlines()
    for line in lines[-n:]:
        print(line.rstrip())


def _logs_show(run_id: str) -> None:
    """Print log lines for the given run_id (matches run_id or runId field only)."""
    path = os.environ.get("FREE_AGENTS_LOG_PATH")
    if not path:
        path = str(Path.home() / ".free_agents" / "logs.jsonl")
    if not os.path.isfile(path):
        print(f"Log file not found: {path}")
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            # Match run_id or runId field exactly (avoid substring matches in output, etc.)
            rec_run_id = rec.get("run_id") or rec.get("runId")
            if rec_run_id == run_id:
                print(line)


def _run_bootstrap(venv_dir: str = ".venv") -> None:
    _ensure_supported_python()

    target = Path(venv_dir)
    print(f"Using Python {_python_version_str()} at {sys.executable}")
    print(f"Creating virtual environment at {target}")
    venv.EnvBuilder(with_pip=True).create(target)

    if os.name == "nt":
        venv_python = target / "Scripts" / "python.exe"
    else:
        venv_python = target / "bin" / "python"

    if not venv_python.exists():
        print(f"Error: could not find venv interpreter at {venv_python}", file=sys.stderr)
        sys.exit(2)

    print("Upgrading pip in venv")
    subprocess.run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], check=True)
    print("Installing agent-toolbox into venv")
    subprocess.run([str(venv_python), "-m", "pip", "install", "agent-toolbox"], check=True)
    print()
    if os.name == "nt":
        print(rf"Bootstrap complete. Activate with: .\{venv_dir}\Scripts\activate")
    else:
        print(f"Bootstrap complete. Activate with: source {venv_dir}/bin/activate")
    print("Then run: agent-toolbox setup")


def _print_env_path_hint() -> None:
    """Print where .env is loaded from and whether the file exists (for setup/diagnosis)."""
    env_path = Path.cwd() / ".env"
    status = "found" if env_path.exists() else "not found"
    print(".env path: {} ({})".format(env_path.resolve(), status))
    print()


def _print_doctor() -> None:
    print("Agent Toolbox Doctor")
    print()
    _print_env_path_hint()
    print(f"Platform: {platform.platform()}")
    print(f"Python:   {_python_version_str()}")
    print(f"Exe:      {sys.executable}")
    print(f"In venv:  {'yes' if sys.prefix != sys.base_prefix else 'no'}")
    print(f"PATH bin: {shutil.which('agent-toolbox') or 'not found'}")

    try:
        pip_version = subprocess.check_output(
            [sys.executable, "-m", "pip", "--version"],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except Exception as exc:  # pragma: no cover - diagnostics fallback
        pip_version = f"unavailable ({exc})"
    print(f"Pip:      {pip_version}")

    pip_index = os.environ.get("PIP_INDEX_URL", "").strip()
    print(f"Index:    {pip_index or 'default (pypi.org)'}")
    if sys.version_info < MIN_PYTHON:
        print(
            f"Issue: Python is below required minimum {MIN_PYTHON[0]}.{MIN_PYTHON[1]}."
        )
    print()
    print("Recommended install flow:")
    print("  pipx install agent-toolbox")
    print("If pipx is missing:")
    if os.name == "nt":
        print(r"  py -m pip install --user pipx")
        print(r"  py -m pipx ensurepath")
    else:
        print("  python3 -m pip install --user pipx")
        print("  python3 -m pipx ensurepath")
    print("Fallback (venv):")
    print("  python3 -m venv .venv")
    if os.name == "nt":
        print(r"  .\.venv\Scripts\activate")
    else:
        print("  source .venv/bin/activate")
    print("  python -m pip install -U pip")
    print("  python -m pip install agent-toolbox")


def main() -> None:
    """Run the agent gateway or handle setup/doctor/bootstrap commands."""
    from .config import get_settings

    port = int(os.environ.get("PORT", "4280"))
    host = os.environ.get("HOST", "0.0.0.0")
    settings = get_settings()

    if len(sys.argv) > 1:
        subcommand = sys.argv[1].strip().lower()
        if subcommand in {"-h", "--help", "help"}:
            _print_help()
            sys.exit(0)
        if subcommand == "logs":
            if len(sys.argv) < 3:
                print("Usage: agent-toolbox logs tail [--n N] | agent-toolbox logs show <run_id>")
                sys.exit(1)
            logs_cmd = sys.argv[2].strip().lower()
            if logs_cmd == "tail":
                n = 100
                args = sys.argv[3:]
                for j, a in enumerate(args):
                    if a in ("-n", "--n") and j + 1 < len(args):
                        try:
                            n = int(args[j + 1])
                        except ValueError:
                            pass
                        break
                _logs_tail(n)
            elif logs_cmd == "show":
                if len(sys.argv) < 4:
                    print("Usage: agent-toolbox logs show <run_id>")
                    sys.exit(1)
                _logs_show(sys.argv[3].strip())
            else:
                print("Usage: agent-toolbox logs tail [--n N] | agent-toolbox logs show <run_id>")
                sys.exit(1)
            sys.exit(0)
        if subcommand == "setup":
            _print_env_path_hint()
            _print_setup_banner(
                preset=settings.agent_preset,
                provider=settings.provider_name,
                port=port,
                for_startup=False,
            )
            sys.exit(0)
        if subcommand == "doctor":
            _print_doctor()
            sys.exit(0)
        if subcommand == "bootstrap":
            target = sys.argv[2] if len(sys.argv) > 2 else ".venv"
            _run_bootstrap(target)
            sys.exit(0)
        if subcommand == "deploy":
            from .cli_replit_deploy import run_deploy_replit

            rest = [a.strip() for a in sys.argv[2:]]
            if "--replit" not in rest:
                print("Usage: agent-toolbox deploy --replit   (alias: free-agents deploy --replit)")
                print("Prepares .replit / replit.nix, lists Secrets to add, opens Replit import.")
                sys.exit(1)
            run_deploy_replit()
            sys.exit(0)

    import uvicorn

    _print_setup_banner(
        preset=settings.agent_preset,
        provider=settings.provider_name,
        port=port,
        for_startup=True,
    )

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        factory=False,
    )


if __name__ == "__main__":
    main()
    sys.exit(0)
