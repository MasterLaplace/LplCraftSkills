#!/usr/bin/env bash
# Probe: does --resume <uuid> carry the conversation across processes?
# Round-based review means every round is a NEW process on the SAME session.
set -uo pipefail
UUID="11111111-2222-3333-4444-555555555555"
SCHEMA='{"type":"object","properties":{"remembered_number":{"type":"integer"}},"required":["remembered_number"],"additionalProperties":false}'
printf '%s' "What was files_touched in your previous answer? Reply as remembered_number." | claude -p \
  --resume "$UUID" \
  --output-format json \
  --json-schema "$SCHEMA" \
  --max-budget-usd 0.20 \
  --model sonnet \
  --tools ""
echo "--- exit=$? ---"
