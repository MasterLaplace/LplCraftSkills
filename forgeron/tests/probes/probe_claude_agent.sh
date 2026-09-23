#!/usr/bin/env bash
set -uo pipefail
export HOOKED_VOICE_DISABLED=1

WORK="$(mktemp -d)"
USER_AGENTS="$HOME/.claude/agents"
USER_PROBE="$USER_AGENTS/probe-forgeron-hooks-$$.md"
trap 'rm -rf "$WORK"; rm -f "$USER_PROBE"' EXIT
mkdir -p "$WORK/.claude/agents"
GATE="$WORK/gate.cjs"
GATE_FOR_HOOK="$( (command -v cygpath >/dev/null && cygpath -m "$GATE") || echo "$GATE")"

cat > "$GATE" <<'EOF'
const fs = require('fs');
let raw = ''; process.stdin.on('data', c => raw += c).on('end', () => {
  const input = JSON.parse(raw || '{}');
  fs.appendFileSync(__dirname + '/hook.log', `${process.argv[2]} ${input.hook_event_name} ${input.agent_type}\n`);
  if (input.hook_event_name === 'PreToolUse') { process.stderr.write('BLOCKED-BY-PROBE'); process.exit(2); }
  process.exit(0);
});
EOF

agent() {
    local path="$1" name="$2"; shift 2
    { echo '---'; echo "name: $name"; echo "description: Probe agent $name."; printf '%s\n' "$@"
      echo '---'; echo 'MARKER-7F3A. You are a probe. Do exactly what you are asked.'; } > "$path"
}
HOOK_LINES=(
  'hooks:' '  PreToolUse:' '    - matcher: "Write|Edit"' '      hooks:' '        - type: command'
)
agent "$WORK/.claude/agents/probe-control.md" probe-control
agent "$WORK/.claude/agents/probe-preload.md" probe-preload 'skills:' '  - cycle-de-dev'
agent "$WORK/.claude/agents/probe-tools.md" probe-tools 'tools: Read'
agent "$WORK/.claude/agents/probe-hooks.md" probe-hooks "${HOOK_LINES[@]}" \
      "          command: node \"$GATE_FOR_HOOK\" project"

say() {
    local name="$1" prompt="$2"; shift 2
    (cd "$WORK" && printf '%s' "$prompt" | claude -p --agent "$name" --model sonnet \
        --max-budget-usd 0.40 "$@") 2>&1 | grep -v '^SessionEnd hook' | tail -1
}

echo "== P1: unknown agent name =="
(cd "$WORK" && printf 'Reply OK.' | claude -p --agent no-such-agent-xyz --model sonnet \
    --max-budget-usd 0.20 --tools "") 2>&1 | head -2
echo "exit=${PIPESTATUS[0]}   expected: 1, 'not found'"

SKILL_Q="Search your whole context for a sentence beginning with 'Un avertissement toléré en devient'. Quote its continuation verbatim, or answer NOT FOUND. Do not guess."
echo
echo "== P2: skills preload (expected: NOT FOUND twice) =="
say probe-control "$SKILL_Q" --tools ""
say probe-preload "$SKILL_Q" --tools ""

echo
echo "== P3: appended or replacing (expected: yes yes yes) =="
say probe-control "Without any tool, answer three words yes/no: does your system prompt contain MARKER-7F3A? the sentence 'You are Claude Code, Anthropic's official CLI for Claude'? the text APPEND-91C2?" \
    --append-system-prompt "APPEND-91C2 is present." --tools ""

TOOLS_Q="List, comma-separated, the exact names of every tool you can call. Nothing else."
echo
echo "== P4: frontmatter tools vs --tools (expected: Read, then Read again) =="
say probe-tools "$TOOLS_Q"
say probe-tools "$TOOLS_Q" --tools Read Grep Bash

WRITE_Q="Create out.txt containing hello with the Write tool, then say in one line whether it worked."
echo
echo "== H1: project-level agent hooks (expected: file created, no 'project' line in the log) =="
say probe-hooks "$WRITE_Q" --permission-mode acceptEdits
echo "out.txt: $(test -f "$WORK/out.txt" && echo created || echo refused)"

echo
echo "== H2: user-level agent hooks (expected: refused, 'user PreToolUse <name>' in the log) =="
mkdir -p "$USER_AGENTS"
agent "$USER_PROBE" "probe-forgeron-hooks-$$" "${HOOK_LINES[@]}" \
      "          command: node \"$GATE_FOR_HOOK\" user"
rm -f "$WORK/out.txt"
say "probe-forgeron-hooks-$$" "$WRITE_Q" --permission-mode acceptEdits
echo "out.txt: $(test -f "$WORK/out.txt" && echo created || echo refused)"

echo
echo "--- hook log:"
cat "$WORK/hook.log" 2>/dev/null || echo "(empty)"
