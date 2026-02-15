#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="${1:-.venv}"

choose_python() {
  if command -v python3.12 >/dev/null 2>&1; then
    echo "python3.12"
    return 0
  fi
  if command -v python3.11 >/dev/null 2>&1; then
    echo "python3.11"
    return 0
  fi
  if command -v python3.10 >/dev/null 2>&1; then
    echo "python3.10"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    echo "python"
    return 0
  fi
  return 1
}

PYTHON_BIN="$(choose_python || true)"
if [[ -z "${PYTHON_BIN}" ]]; then
  echo "Error: Python not found. Install Python 3.10+ and retry." >&2
  exit 1
fi

"${PYTHON_BIN}" - <<'PY'
import sys
if sys.version_info < (3, 10):
    v = ".".join(map(str, sys.version_info[:3]))
    raise SystemExit(
        f"Error: Python {v} detected. agent-toolbox requires Python 3.10+."
    )
PY

echo "Using ${PYTHON_BIN} to create ${VENV_DIR}"
"${PYTHON_BIN}" -m venv "${VENV_DIR}"

VENV_PYTHON="${VENV_DIR}/bin/python"
if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "Error: ${VENV_PYTHON} not found after creating venv." >&2
  exit 1
fi

"${VENV_PYTHON}" -m pip install --upgrade pip

if [[ -f "pyproject.toml" ]]; then
  echo "Installing local package in editable mode."
  "${VENV_PYTHON}" -m pip install --no-build-isolation -e .
else
  echo "Installing agent-toolbox from PyPI."
  "${VENV_PYTHON}" -m pip install agent-toolbox
fi

echo
echo "Bootstrap complete."
echo "Activate with: source ${VENV_DIR}/bin/activate"
echo "Then run: agent-toolbox setup"
