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
suspects="$(grep -rlE '[│├└┌┐┘─╔╗╚╝║]' skills/ 2>/dev/null || true)"
[ -z "$suspects" ] && report ok "aucun art ASCII" \
    || { report MANQUE "art ASCII trouve dans :"; echo "$suspects" | sed 's/^/         /'; }

echo
if [ "$failures" -eq 0 ]; then
    echo "tout ce que le README affirme est vrai."
else
    echo "$failures affirmation(s) du README sont fausses."
fi
exit $(( failures > 0 ))
