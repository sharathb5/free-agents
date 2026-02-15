from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app import cli


def test_print_help_includes_new_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    cli._print_help()
    output = capsys.readouterr().out
    assert "agent-toolbox doctor" in output
    assert "agent-toolbox bootstrap" in output


def test_main_setup_subcommand_prints_setup_and_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {}

    def fake_get_settings() -> SimpleNamespace:
        return SimpleNamespace(agent_preset="summarizer", provider_name="stub")

    def fake_setup_banner(preset: str, provider: str, port: int, *, for_startup: bool) -> None:
        calls["preset"] = preset
        calls["provider"] = provider
        calls["port"] = port
        calls["for_startup"] = for_startup

    monkeypatch.setattr("app.config.get_settings", fake_get_settings)
    monkeypatch.setattr(cli, "_print_setup_banner", fake_setup_banner)
    monkeypatch.setattr(cli.sys, "argv", ["agent-toolbox", "setup"])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0
    assert calls == {
        "preset": "summarizer",
        "provider": "stub",
        "port": 4280,
        "for_startup": False,
    }


def test_print_doctor_reports_runtime_info(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "/tmp/agent-toolbox")
    monkeypatch.setattr(cli.subprocess, "check_output", lambda *_args, **_kwargs: "pip X.Y.Z")

    cli._print_doctor()
    output = capsys.readouterr().out
    assert "Agent Toolbox Doctor" in output
    assert "PATH bin: /tmp/agent-toolbox" in output
    assert "pip X.Y.Z" in output
    assert "python -m pip install agent-toolbox" in output


def test_run_bootstrap_creates_venv_and_installs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []

    class FakeEnvBuilder:
        def __init__(self, with_pip: bool) -> None:
            assert with_pip is True

        def create(self, target: Path) -> None:
            bin_dir = target / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            python_bin = bin_dir / "python"
            python_bin.write_text("#!/usr/bin/env python\n", encoding="utf-8")
            python_bin.chmod(0o755)

    def fake_run(cmd: list[str], check: bool) -> None:
        assert check is True
        commands.append(cmd)

    monkeypatch.setattr(cli, "_ensure_supported_python", lambda: None)
    monkeypatch.setattr(cli.venv, "EnvBuilder", FakeEnvBuilder)
    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    venv_dir = tmp_path / "venv"
    cli._run_bootstrap(str(venv_dir))

    assert len(commands) == 2
    assert commands[0][-4:] == ["pip", "install", "--upgrade", "pip"]
    assert commands[1][-3:] == ["pip", "install", "agent-toolbox"]
