#!/usr/bin/env bash
set -euo pipefail
REPO="$(pwd)"
if ! git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Run install.sh from the root of the target Git repository." >&2
  exit 2
fi
cat > "$REPO/morph-once" <<'WRAP'
#!/usr/bin/env bash
set -euo pipefail
REPO="$(pwd)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/morph_system" && pwd)"
if [[ "${1:-}" == "doctor" ]]; then
  shift
  PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}" python3 -m morph doctor --repo "$REPO" "$@"
else
  PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}" python3 -m morph run --repo "$REPO" "$@"
fi
WRAP
chmod +x "$REPO/morph-once"
if [[ ! -f "$REPO/morph.yaml" ]]; then
  cp "$REPO/morph_system/morph.yaml" "$REPO/morph.yaml"
fi
mkdir -p "$REPO/.morph"
cat > "$REPO/.morph/.gitignore" <<'GI'
runs/
memory/
GI
if [[ -d "$REPO/.git/info" ]]; then
  grep -qxF '.morph-worktrees/' "$REPO/.git/info/exclude" 2>/dev/null || echo '.morph-worktrees/' >> "$REPO/.git/info/exclude"
  grep -qxF '.morph/' "$REPO/.git/info/exclude" 2>/dev/null || echo '.morph/' >> "$REPO/.git/info/exclude"
fi
echo "MORPH installed locally. One-shot command:"
echo '  ./morph-once --adapter auto --apply "YOUR TASK"'
