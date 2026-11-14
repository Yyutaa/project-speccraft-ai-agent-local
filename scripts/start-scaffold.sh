#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_ROOT="$REPO_ROOT/apps/web"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3.12 || true)}"
VENV_ROOT="$REPO_ROOT/.venv"

if [[ ! -x "$VENV_ROOT/bin/python" ]]; then
  if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
    echo "需要 Python 3.12。"
    exit 1
  fi
  "$PYTHON_BIN" -m venv "$VENV_ROOT"
fi

if ! "$VENV_ROOT/bin/python" -c "import fastapi, deliveryflow_speccraft" >/dev/null 2>&1; then
  "$VENV_ROOT/bin/python" -m pip install \
    -e "$REPO_ROOT/packages/contracts[dev]" \
    -e "$REPO_ROOT/packages/agent-kernel" \
    -e "$REPO_ROOT/packages/speccraft"
fi

if [[ ! -d "$WEB_ROOT/node_modules" ]]; then
  npm --prefix "$WEB_ROOT" install
fi

cd "$REPO_ROOT"
exec "$VENV_ROOT/bin/python" -m apps.dev.supervisor
