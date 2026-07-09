#!/usr/bin/env bash
# drive-cmux installer — copies the skill into ~/.claude/skills/ and checks prereqs.
# Usage (from the cloned repo):  ./install.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.claude/skills/drive-cmux"

mkdir -p "$HOME/.claude/skills"
rm -rf "$DEST"
cp -R "$HERE/skills/drive-cmux" "$DEST"
echo "✓ Installed the drive-cmux skill -> $DEST"

if command -v python3 >/dev/null; then echo "✓ python3: $(python3 --version)"; else echo "✗ Please install Python 3 (3.10+)"; fi
command -v claude >/dev/null && echo "✓ Claude Code found" || echo "• Install Claude Code (Sonnet 5 / Opus lanes): https://www.anthropic.com/claude-code"
command -v codex  >/dev/null && echo "✓ Codex CLI found"   || echo "• Install the Codex CLI (GPT-5.6 lane)"

cat <<'NEXT'

Almost there — three one-time manual steps (~2 min):
  1) cmux  ->  Settings  ->  Socket Control Mode  ->  Password
  2) python3 ~/.claude/skills/drive-cmux/dcx.py set-password --generate   # paste the printed value into cmux
  3) python3 ~/.claude/skills/drive-cmux/dcx.py preflight                 # expect {"ok": true}
  (and for the model lanes)  claude setup-token  &&  claude -p "ping"     # expect: pong

Then just tell Claude Code:  "use drive-cmux to ..."
NEXT
