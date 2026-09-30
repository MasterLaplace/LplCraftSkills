# forgeron in a container.
#
# Three choices, with their reason:
#  - debian:trixie-slim and not python:3-slim, because the image needs git, curl
#    and gh anyway: starting from a Python base saves nothing and pins
#    a Python version the driver does not need (stdlib only, 3.10+);
#  - a NON-root user, because the agent runs commands the prompt does not
#    entirely decide, and root in a container mounts the host;
#  - NO secret in the image. A layer is public as soon as the image is pushed,
#    and an instruction that deletes a file does not erase the layer before it.

FROM debian:trixie-slim

ARG DEBIAN_FRONTEND=noninteractive
ARG USERNAME=forgeron
ARG UID=1000
ARG GID=1000

# curl/ca-certificates: the claude installer and the gh repository
# git              : the worktrees, the commits
# python3          : the driver
# jq, zstd         : optional, but the claude installer uses them if they are there
# openssh-client   : in case the remote is one day over ssh rather than https
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git python3 nodejs jq zstd openssh-client gnupg \
    && rm -rf /var/lib/apt/lists/*

# gh, from the official repository: the version in a distribution repository is months
# behind, and that is precisely what deprived forgeron of `gh pr checks --json`.
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

# The installer refuses sudo from a user's shell, but its guard only
# triggers when SUDO_USER is set: a normal user, here, gets through.
# It puts the binary in ~/.local/bin, hence the PATH below.
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/home/${USERNAME}/.local/bin:${PATH}"

COPY --chown=$UID:$GID skills/ /opt/craft/skills/
COPY --chown=$UID:$GID agents/ /opt/craft/agents/
COPY --chown=$UID:$GID install.sh /opt/craft/install.sh
RUN /opt/craft/install.sh

COPY --chown=$UID:$GID forgeron/forgeron/ /opt/forgeron/forgeron/
COPY --chown=$UID:$GID forgeron/docker/entrypoint.sh /usr/local/bin/entrypoint.sh

ENV PYTHONPATH=/opt/forgeron \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# The AI attribution prevention must exist WHERE THE AGENT COMMITS, and not
# only on the author's machine: a fresh container has no hook, so the
# layer that prevents would be missing there exactly where the agent is the least
# watched. The script is derived from the same patterns as the driver's check.
RUN python3 -m forgeron hook --install "/home/${USERNAME}/.config/git/hooks" \
    && git config --global core.hooksPath "/home/${USERNAME}/.config/git/hooks"

# A healthcheck that lies is worse than no healthcheck: this one only claims
# what it checks, namely that the driver loads and can describe itself.
HEALTHCHECK --interval=60s --timeout=15s --start-period=10s --retries=3 \
    CMD python3 -m forgeron --version || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["--help"]
