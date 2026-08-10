#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(pwd)"
if ! git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "MORPH: run this command from inside the target Git repository." >&2
  exit 2
fi
if [[ $# -lt 1 ]]; then
  echo 'Usage: bash morph_system/run-once.sh [--adapter claude|codex|auto] [--apply|--commit|--push] "TASK"' >&2
  exit 2
fi
PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}" python3 -m morph run --repo "$REPO" "$@"
