#!/usr/bin/env bash
# One-time local setup: virtualenv, dependencies, .env, and an offline health check.
# Usage: ./scripts/setup.sh
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
if ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
  echo "Python 3.11+ is required (found: $("$PYTHON" --version 2>&1))" >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "==> Creating virtualenv in .venv"
  "$PYTHON" -m venv .venv
fi

echo "==> Installing dependencies"
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e ".[dev]"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> Created .env from .env.example - fill in your secrets"
fi

echo "==> Checking environment"
.venv/bin/getjob doctor --offline

cat <<'EOF'

Done. Next:
  1. Edit config/search.yaml  (your keywords, districts, experience)
  2. Edit .env                (Telegram / email secrets)
  3. source .venv/bin/activate && getjob doctor
EOF
