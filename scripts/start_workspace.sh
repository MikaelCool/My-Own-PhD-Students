#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${1:-$ROOT_DIR/config.arc.yaml}"
HOST="${2:-127.0.0.1}"
PORT="${3:-8080}"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif [[ -x "$ROOT_DIR/.venv/Scripts/python.exe" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/Scripts/python.exe"
else
  echo "ERROR: Python virtual environment not found"
  echo "Expected one of:"
  echo "  $ROOT_DIR/.venv/bin/python"
  echo "  $ROOT_DIR/.venv/Scripts/python.exe"
  echo
  echo "Create it first:"
  echo "  python -m venv .venv"
  echo "  .venv setup complete, then install the project"
  exit 1
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "ERROR: Config file not found: $CONFIG_PATH"
  exit 1
fi

echo "Launching My Own PhD Students workspace"
echo "Root:   $ROOT_DIR"
echo "Config: $CONFIG_PATH"
echo "URL:    http://$HOST:$PORT/"
echo

cd "$ROOT_DIR"
exec "$PYTHON_BIN" -m researchclaw.cli serve --config "$CONFIG_PATH" --host "$HOST" --port "$PORT"
