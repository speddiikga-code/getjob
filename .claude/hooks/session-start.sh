#!/bin/bash
# Installs the project into .venv so tests and linters work in Claude Code on the web.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --quiet --disable-pip-version-check -e ".[dev]"

{
  echo "export VIRTUAL_ENV=\"$CLAUDE_PROJECT_DIR/.venv\""
  echo "export PATH=\"$CLAUDE_PROJECT_DIR/.venv/bin:\$PATH\""
} >> "$CLAUDE_ENV_FILE"
