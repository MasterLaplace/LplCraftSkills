#!/usr/bin/env bash
# Probe: does `claude -p` return a schema-validated JSON verdict we can parse?
# The orchestrator reads a machine verdict instead of prose, so this must hold.
#
# FINDING (2026-08-27): --tools / --allowedTools / --add-dir are VARIADIC, so a
# positional prompt after them is eaten as another value and claude reports
# "Input must be provided either through stdin or as a prompt argument".
# Rule: always feed the prompt on STDIN.
set -uo pipefail
SCHEMA='{"type":"object","properties":{"verdict":{"type":"string","enum":["ok","blocked"]},"files_touched":{"type":"integer"}},"required":["verdict","files_touched"],"additionalProperties":false}'
UUID="11111111-2222-3333-4444-555555555555"
printf '%s' "Answer with verdict=ok and files_touched=3. Nothing else." | claude -p \
  --session-id "$UUID" \
  --output-format json \
  --json-schema "$SCHEMA" \
  --max-budget-usd 0.20 \
  --model sonnet \
  --tools ""
echo "--- exit=$? ---"
