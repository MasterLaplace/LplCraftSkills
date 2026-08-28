#!/usr/bin/env bash
# Ce que le conteneur doit regler AVANT de laisser le pilote parler a git ou a gh.
# Chacun de ces quatre points est une panne concrete si on l'omet.
set -euo pipefail

# 1. git refuse de travailler dans un depot dont le proprietaire n'est pas
#    l'utilisateur courant. Un volume monte depuis l'hote a l'uid de l'hote, donc
#    sans ceci la premiere commande git echoue sur "detected dubious ownership",
#    ce qui ressemble a un probleme de permissions et n'en est pas un.
git config --global --add safe.directory '*'

# 2. un commit sans identite echoue. Reglable de l'exterieur, avec un defaut qui
#    ne se fait pas passer pour un humain.
git config --global user.name  "${GIT_AUTHOR_NAME:-forgeron}"
git config --global user.email "${GIT_AUTHOR_EMAIL:-forgeron@localhost.invalid}"

# 3. dire lequel des deux modes d'authentification est actif, sans jamais imprimer
#    la valeur. Un conteneur qui demarre sans credential doit le dire ici plutot
#    que d'echouer plus tard, au milieu d'un run, en ayant deja pousse une branche.
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
    echo "[entrypoint] claude : token d'abonnement (CLAUDE_CODE_OAUTH_TOKEN)" >&2
elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    echo "[entrypoint] claude : cle d'API — FACTUREE EN PLUS de ton abonnement" >&2
elif [ -f "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.credentials.json" ]; then
    echo "[entrypoint] claude : credentials montes depuis l'hote" >&2
else
    echo "[entrypoint] ERREUR : aucune authentification claude." >&2
    echo "[entrypoint] Voir docs/INSTALLATION.md section 4.2." >&2
    exit 3
fi

if [ -z "${GH_TOKEN:-}" ] && ! gh auth status >/dev/null 2>&1; then
    echo "[entrypoint] ERREUR : ni GH_TOKEN ni session gh. Voir section 4.2." >&2
    exit 3
fi

exec python3 -m forgeron "$@"
