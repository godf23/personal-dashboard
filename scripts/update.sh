#!/usr/bin/env bash
# Pull latest dashboard code from GitHub and refresh dependencies.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BRANCH="${1:-main}"

cd "$ROOT"

if [[ ! -d .git ]]; then
  echo "Not a git repository" >&2
  exit 1
fi

git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

if [[ -x .venv/bin/pip ]]; then
  .venv/bin/pip install -r requirements.txt -q
elif [[ -x .venv/Scripts/pip.exe ]]; then
  .venv/Scripts/pip.exe install -r requirements.txt -q
else
  echo "Virtual environment pip not found" >&2
  exit 1
fi

echo "Updated to $(git rev-parse --short HEAD)"
