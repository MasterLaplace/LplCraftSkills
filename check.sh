#!/usr/bin/env bash
# Verifie ce que le README AFFIRME sur le pack. Rien d'autre.
#
# Il existe parce que trois skills avaient perdu leur porte de sortie sans que
# personne ne s'en apercoive : le README le promettait, et rien ne le verifiait.
# Une affirmation invérifiable finit toujours par etre fausse, c'est le fil rouge
# du pack applique au pack lui-meme.
#
# Sortie : 0 si tout tient, 1 sinon, avec la liste de ce qui manque.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

failures=0
report() { printf '%-7s %s\n' "$1" "$2"; [ "$1" = "MANQUE" ] && failures=$((failures + 1)); return 0; }

echo "== chaque skill se termine par une porte de sortie =="
for skill in skills/*/SKILL.md; do
    name="$(basename "$(dirname "$skill")")"
    last="$(grep -E '^## ' "$skill" | tail -1)"
    if echo "$last" | grep -qi 'porte de sortie'; then
        report ok "$name"
    else
        report MANQUE "$name — derniere section : ${last:-aucune}"
    fi
done

echo
echo "== chaque skill porte un nom et une description de declenchement =="
for skill in skills/*/SKILL.md; do
    name="$(basename "$(dirname "$skill")")"
    head -1 "$skill" | grep -q '^---$' || { report MANQUE "$name — pas de frontmatter"; continue; }
    grep -qE '^name: ' "$skill" && grep -qE '^description: ' "$skill" \
        && report ok "$name" || report MANQUE "$name — name: ou description: absent"
done

echo
echo "== le README et le dossier skills/ listent les memes skills =="
listed="$(grep -oE '\[`[a-z-]+`\]\(skills/' README.md | grep -oE '`[a-z-]+`' | tr -d '`' | sort -u)"
present="$(find skills -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)"
if [ "$listed" = "$present" ]; then
    report ok "$(echo "$present" | wc -l) skills des deux cotes"
else
    report MANQUE "le tableau du README et skills/ divergent :"
    diff <(echo "$listed") <(echo "$present") | sed 's/^/         /'
fi

echo
echo "== les schemas sont en Mermaid, jamais en art ASCII =="
# Un bloc de code contenant des caracteres de boite est un schema dessine a la main.
box=()
for char in '│' '├' '└' '┌' '┐' '┘' '─' '╔' '╗' '╚' '╝' '║'; do box+=(-e "$char"); done
suspects="$(grep -rlF "${box[@]}" skills/ agents/ 2>/dev/null || true)"
[ -z "$suspects" ] && report ok "aucun art ASCII" \
    || { report MANQUE "art ASCII trouve dans :"; echo "$suspects" | sed 's/^/         /'; }

echo
echo "== chaque agent porte un nom, une description, et la carte de TOUS les skills =="
for agent in agents/*.md; do
    name="$(basename "$agent" .md)"
    grep -qE '^name: ' "$agent" && grep -qE '^description: ' "$agent" \
        || { report MANQUE "$name — name: ou description: absent"; continue; }
    missing=""
    for skill in $present; do
        grep -qF "\`$skill\`" "$agent" || missing="$missing $skill"
    done
    [ -z "$missing" ] && report ok "$name nomme les $(echo "$present" | wc -l) skills" \
        || report MANQUE "$name ne nomme pas :$missing"
done

echo
echo "== les hooks des agents passent leurs tests =="
if command -v node >/dev/null 2>&1; then
    if node --test agents/hooks/ > /dev/null 2>&1; then
        report ok "node --test agents/hooks/"
    else
        report MANQUE "node --test agents/hooks/ echoue (le relancer pour le detail)"
    fi
else
    report SAUTE "node introuvable, les tests des hooks n'ont pas tourne"
fi

echo
echo "== la prose porte une espace insecable avant ; : ! ? =="
normal_spaces="$(find . -name '*.md' -not -path './.git/*' -print0 | xargs -0 awk '
    FNR == 1 { front = 0; fence = 0 }
    FNR == 1 && /^---[[:space:]]*$/ { front = 1; next }
    front { if (/^---[[:space:]]*$/) front = 0; next }
    /^[[:space:]]*```/ { fence = !fence; next }
    fence || /^[[:space:]]*<!--/ { next }
    { line = $0; gsub(/`[^`]*`/, "", line); gsub(/[a-z]+:\/\/[^ )]*/, "", line)
      if (line ~ / [;:!?]/) print FILENAME ":" FNR }')"
[ -z "$normal_spaces" ] && report ok "aucune espace normale devant une ponctuation double" \
    || { report MANQUE "espace normale devant ; : ! ? (typographie francaise) :"; echo "$normal_spaces" | head -20 | sed 's/^/         /'; }

echo
if [ "$failures" -eq 0 ]; then
    echo "tout ce que le README affirme est vrai."
else
    echo "$failures affirmation(s) du README sont fausses."
fi
exit $(( failures > 0 ))
