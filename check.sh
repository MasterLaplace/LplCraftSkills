#!/usr/bin/env bash
# Checks what the README CLAIMS about the pack. Nothing else.
#
# It exists because three skills had lost their exit gate without
# anybody noticing: the README promised it, and nothing checked it.
# An uncheckable claim always ends up false, it is the common thread
# of the pack applied to the pack itself.
#
# Exit: 0 if everything holds, 1 otherwise, with the list of what is missing.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

failures=0
report() { printf '%-7s %s\n' "$1" "$2"; [ "$1" = "MISSING" ] && failures=$((failures + 1)); return 0; }

echo "== every skill ends with an exit gate (porte de sortie) =="
for skill in skills/*/SKILL.md; do
    name="$(basename "$(dirname "$skill")")"
    last="$(grep -E '^## ' "$skill" | tail -1)"
    if echo "$last" | grep -qi 'porte de sortie'; then
        report ok "$name"
    else
        report MISSING "$name — last section: ${last:-none}"
    fi
done

echo
echo "== every skill carries a name and a trigger description =="
for skill in skills/*/SKILL.md; do
    name="$(basename "$(dirname "$skill")")"
    head -1 "$skill" | grep -q '^---$' || { report MISSING "$name — no frontmatter"; continue; }
    grep -qE '^name: ' "$skill" && grep -qE '^description: ' "$skill" \
        && report ok "$name" || report MISSING "$name — name: or description: missing"
done

echo
echo "== the README and the skills/ directory list the same skills =="
listed="$(grep -oE '\[`[a-z-]+`\]\(skills/' README.md | grep -oE '`[a-z-]+`' | tr -d '`' | sort -u)"
present="$(find skills -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)"
if [ "$listed" = "$present" ]; then
    report ok "$(echo "$present" | wc -l) skills on both sides"
else
    report MISSING "the README table and skills/ diverge:"
    diff <(echo "$listed") <(echo "$present") | sed 's/^/         /'
fi

echo
echo "== diagrams are in Mermaid, never in ASCII art =="
# A code block containing box-drawing characters is a hand-drawn diagram.
box=()
for char in '│' '├' '└' '┌' '┐' '┘' '─' '╔' '╗' '╚' '╝' '║'; do box+=(-e "$char"); done
suspects="$(grep -rlF "${box[@]}" skills/ agents/ 2>/dev/null || true)"
[ -z "$suspects" ] && report ok "no ASCII art" \
    || { report MISSING "ASCII art found in:"; echo "$suspects" | sed 's/^/         /'; }

echo
echo "== every agent carries a name, a description, and the map of ALL the skills =="
for agent in agents/*.md; do
    name="$(basename "$agent" .md)"
    grep -qE '^name: ' "$agent" && grep -qE '^description: ' "$agent" \
        || { report MISSING "$name — name: or description: missing"; continue; }
    missing=""
    for skill in $present; do
        grep -qF "\`$skill\`" "$agent" || missing="$missing $skill"
    done
    [ -z "$missing" ] && report ok "$name names the $(echo "$present" | wc -l) skills" \
        || report MISSING "$name does not name:$missing"
done

echo
echo "== the agents' hooks pass their tests =="
if command -v node >/dev/null 2>&1; then
    if node --test agents/hooks/ > /dev/null 2>&1; then
        report ok "node --test agents/hooks/"
    else
        report MISSING "node --test agents/hooks/ fails (run it again for the detail)"
    fi
else
    report SKIPPED "node not found, the hooks' tests did not run"
fi

echo
echo "== the prose carries a non-breaking space before ; : ! ? =="
normal_spaces="$(find . -name '*.md' -not -path './.git/*' -print0 | xargs -0 awk '
    FNR == 1 { front = 0; fence = 0 }
    FNR == 1 && /^---[[:space:]]*$/ { front = 1; next }
    front { if (/^---[[:space:]]*$/) front = 0; next }
    /^[[:space:]]*```/ { fence = !fence; next }
    fence || /^[[:space:]]*<!--/ { next }
    { line = $0; gsub(/`[^`]*`/, "", line); gsub(/[a-z]+:\/\/[^ )]*/, "", line)
      if (line ~ / [;:!?]/) print FILENAME ":" FNR }')"
[ -z "$normal_spaces" ] && report ok "no normal space before a double punctuation mark" \
    || { report MISSING "normal space before ; : ! ? (French typography):"; echo "$normal_spaces" | head -20 | sed 's/^/         /'; }

echo
if [ "$failures" -eq 0 ]; then
    echo "everything the README claims is true."
else
    echo "$failures claim(s) of the README are false."
fi
exit $(( failures > 0 ))
