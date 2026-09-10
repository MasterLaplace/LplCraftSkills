"""Les motifs d'attribution IA, déclarés une fois, et ce qu'on en fait.

Le harnais Claude Code pousse par défaut un pied de page « Co-Authored-By » et une
ligne « Generated with Claude Code ». Trois couches s'y opposent, et elles échouent
différemment, ce qui est la raison d'en avoir trois :

1. le réglage `attribution` de `~/.claude/settings.json`, qu'une mise à jour peut
   ne pas préserver ;
2. un hook `commit-msg`, qui prévient à la source mais que `--no-verify` contourne
   et qui n'existe pas dans un conteneur neuf ;
3. la vérification de ce module, qui ne prévient rien et n'est contournable par
   rien, parce qu'elle regarde le résultat.

Les motifs vivent ici et le hook est DÉRIVÉ d'eux : deux listes finiraient par ne
pas s'accorder sur ce qui compte, et la couche qui prévient cesserait de protéger
ce que la couche qui vérifie refuse.
"""

from __future__ import annotations

import re

# Un co-auteur HUMAIN est légitime : seules les lignes qui nomment l'outil partent.
# Le `.{0,4}` de la deuxième laisse passer un préfixe d'emoji ou de puce.
PATTERNS = (
    r"^\s*co-authored-by:.*(claude|anthropic)",
    r"^.{0,4}generated with \[?claude code\]?",
    r"^\s*claude-session:",
)

_MATCHERS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in PATTERNS)


def offending_lines(text: str) -> tuple[str, ...]:
    """Les lignes d'attribution présentes. Vide veut dire propre."""
    return tuple(line for line in text.splitlines()
                 if any(matcher.search(line) for matcher in _MATCHERS))


def strip(text: str) -> str:
    """Retire les lignes fautives, et rien d'autre.

    Par le MOTIF et jamais par la position : supprimer « la dernière ligne »
    détruirait une ligne légitime quand il n'y a pas de pied de page. Les lignes
    vides de fin partent aussi, mais pas celles du milieu, qui séparent des
    paragraphes.
    """
    kept = [line for line in text.splitlines()
            if not any(matcher.search(line) for matcher in _MATCHERS)]
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept)


def hook_script() -> str:
    """Le hook `commit-msg`, dérivé des motifs ci-dessus.

    Il abandonne le commit s'il ne peut pas tourner, plutôt que de le laisser
    passer non filtré : une garde qui se tait quand elle casse ne garde rien.
    """
    alternation = "|".join(
        pattern.replace(r"\s*", "[[:space:]]*").replace(r"\[?", r"\[?").replace(r"\]?", r"\]?")
        for pattern in PATTERNS
    )
    return f"""#!/bin/sh
# Retire toute attribution IA d'un message de commit, quelle que soit sa position.
# GENERE par forgeron depuis attribution.PATTERNS : ne pas editer a la main, les
# motifs vivent dans forgeron/attribution.py et la verification utilise les memes.
set -eu

msg="${{1:-}}"
[ -n "$msg" ] && [ -f "$msg" ] || exit 0

motif='{alternation}'

tmp=$(mktemp) || exit 1
trap 'rm -f "$tmp"' EXIT

grep -viE "$motif" "$msg" > "$tmp" || true
awk '{{l[NR]=$0}} END{{n=NR; while (n>0 && l[n] ~ /^[[:space:]]*$/) n--; \
for (i=1;i<=n;i++) print l[i]}}' "$tmp" > "$msg"
"""
