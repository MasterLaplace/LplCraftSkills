#!/usr/bin/env bash
set -uo pipefail
export HOOKED_VOICE_DISABLED=1

WORK="$(mktemp -d)"
USER_AGENTS="$HOME/.claude/agents"
HOOKED="probe-subagent-hooks-$$"
TOOLED="probe-subagent-tools-$$"
trap 'rm -rf "$WORK"; rm -f "$USER_AGENTS/$HOOKED.md" "$USER_AGENTS/$TOOLED.md"' EXIT
GATE="$WORK/gate.cjs"
GATE_FOR_HOOK="$( (command -v cygpath >/dev/null && cygpath -m "$GATE") || echo "$GATE")"

cat > "$GATE" <<'EOF'
const fs = require('fs');
let raw = ''; process.stdin.on('data', c => raw += c).on('end', () => {
  const input = JSON.parse(raw || '{}');
  fs.appendFileSync(__dirname + '/hook.log', `${input.hook_event_name} ${input.tool_name} ${input.agent_type}\n`);
  if (input.hook_event_name === 'PreToolUse') { process.stderr.write('BLOCKED-BY-PROBE'); process.exit(2); }
  process.exit(0);
});
EOF

mkdir -p "$USER_AGENTS"
{ echo '---'; echo "name: $HOOKED"; echo "description: Probe agent $HOOKED."
  printf '%s\n' 'hooks:' '  PreToolUse:' '    - matcher: "Write|Edit|Bash"' '      hooks:' '        - type: command'
  echo "          command: node \"$GATE_FOR_HOOK\""
  echo '---'; echo 'You are a probe. Do exactly what you are asked.'; } > "$USER_AGENTS/$HOOKED.md"
{ echo '---'; echo "name: $TOOLED"; echo "description: Probe agent $TOOLED."
  echo 'tools: Read, NoSuchTool-7Q2'
  echo '---'; echo 'You are a probe. Do exactly what you are asked.'; } > "$USER_AGENTS/$TOOLED.md"

main() {
    (cd "$WORK" && printf '%s' "$1" | claude -p --model sonnet --max-budget-usd 0.80 \
        --permission-mode acceptEdits) 2>&1 | grep -v '^SessionEnd hook' | tail -3
}

echo "== S1: frontmatter hooks of a user-level agent run as a SUBAGENT =="
echo "   expected if they fire: out.txt refused, 'PreToolUse Write $HOOKED' in the log"
main "Use the Agent tool with subagent_type '$HOOKED'. Ask it to create the file out.txt containing hello with its Write tool, then to report in one line whether it worked. Relay its answer in one line. Do not write the file yourself."
echo "out.txt: $(test -f "$WORK/out.txt" && echo created || echo refused)"

echo
echo "== S2: 'tools:' naming an unknown tool, run as a subagent =="
echo "   expected: the agent loads, and its tool list is Read only"
main "Use the Agent tool with subagent_type '$TOOLED'. Ask it to list, comma-separated, the exact names of every tool it can call, and nothing else. Relay its list verbatim."

echo
echo "== S3: can a subagent launch a subagent? =="
echo "   expected: the list of tools of a subagent WITHOUT 'tools:' restriction, look for Agent or Task"
main "Use the Agent tool with subagent_type 'general-purpose'. Ask it to list, comma-separated, the exact names of every tool it can call, and nothing else. Relay its list verbatim."

echo
echo "--- hook log:"
cat "$WORK/hook.log" 2>/dev/null || echo "(empty)"
