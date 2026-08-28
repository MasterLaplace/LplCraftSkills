# forgeron dans un conteneur.
#
# ATTENTION : cette image n'a PAS ete construite. Il n'y a ni docker ni kubectl sur
# la machine ou elle a ete ecrite, donc c'est une recette fondee sur les sources
# officielles, pas un compte rendu d'execution. La commande de build et ce qu'elle
# doit afficher sont dans docs/INSTALLATION.md section 4.
#
# Trois choix, avec leur raison :
#  - debian:trixie-slim et non python:3-slim, parce que l'image a de toute facon
#    besoin de git, curl et gh : partir d'une base Python n'economise rien et fige
#    une version de Python dont le pilote n'a pas besoin (stdlib seule, 3.10+) ;
#  - un utilisateur NON root, parce que l'agent execute des commandes que le prompt
#    ne decide pas entierement, et que root dans un conteneur monte l'hote ;
#  - AUCUN secret dans l'image. Une couche est publique des que l'image est poussee,
#    et une instruction qui supprime un fichier n'efface pas la couche d'avant.

FROM debian:trixie-slim

ARG DEBIAN_FRONTEND=noninteractive
ARG USERNAME=forgeron
ARG UID=1000
ARG GID=1000

# curl/ca-certificates : l'installateur claude et le depot gh
# git              : les worktrees, les commits
# python3          : le pilote
# jq, zstd         : optionnels, mais l'installateur claude s'en sert s'ils sont la
# openssh-client   : si un jour le remote est en ssh plutot qu'en https
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git python3 jq zstd openssh-client gnupg \
    && rm -rf /var/lib/apt/lists/*

# gh, depuis le depot officiel : la version d'un depot de distribution a des mois
# de retard, et c'est justement ce qui a prive forgeron de `gh pr checks --json`.
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
         -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
         > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g "$GID" "$USERNAME" \
    && useradd -m -u "$UID" -g "$GID" -s /bin/bash "$USERNAME"

USER $USERNAME
WORKDIR /home/$USERNAME

# L'installateur refuse sudo depuis le shell d'un utilisateur, mais sa garde ne se
# declenche que si SUDO_USER est renseigne : un utilisateur normal, ici, passe.
# Il pose le binaire dans ~/.local/bin, d'ou le PATH ci-dessous.
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/home/${USERNAME}/.local/bin:${PATH}"

COPY --chown=$UID:$GID forgeron/ /opt/forgeron/forgeron/
COPY --chown=$UID:$GID docker/entrypoint.sh /usr/local/bin/entrypoint.sh

ENV PYTHONPATH=/opt/forgeron \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Un healthcheck qui ment est pire que pas de healthcheck : celui-ci n'affirme que
# ce qu'il verifie, a savoir que le pilote se charge et sait s'auto-decrire.
HEALTHCHECK --interval=60s --timeout=15s --start-period=10s --retries=3 \
    CMD python3 -m forgeron --version || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["--help"]
