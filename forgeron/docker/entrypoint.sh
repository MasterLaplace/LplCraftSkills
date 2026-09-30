#!/usr/bin/env bash
# What the container must set up BEFORE letting the driver talk to git or gh.
# Each of these four points is a concrete failure if it is left out.
set -euo pipefail

# 1. git refuses to work in a repository whose owner is not the current
#    user. A volume mounted from the host has the host's uid, so without
#    this the first git command fails on "detected dubious ownership",
#    which looks like a permissions problem and is not one.
git config --global --add safe.directory '*'

# 2. a commit without an identity fails. Settable from outside, with a default that
#    does not pass itself off as a human.
git config --global user.name  "${GIT_AUTHOR_NAME:-forgeron}"
git config --global user.email "${GIT_AUTHOR_EMAIL:-forgeron@localhost.invalid}"

# 3. say which of the two authentication modes is active, without ever printing
#    the value. A container that starts without a credential must say so here rather
#    than fail later, in the middle of a run, after having already pushed a branch.
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
    echo "[entrypoint] claude: subscription token (CLAUDE_CODE_OAUTH_TOKEN)" >&2
elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    echo "[entrypoint] claude: API key — BILLED ON TOP OF your subscription" >&2
elif [ -f "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.credentials.json" ]; then
    echo "[entrypoint] claude: credentials mounted from the host" >&2
else
    echo "[entrypoint] ERROR: no claude authentication." >&2
    echo "[entrypoint] See docs/INSTALLATION.md section 4.2." >&2
    exit 3
fi

if [ -z "${GH_TOKEN:-}" ] && ! gh auth status >/dev/null 2>&1; then
    echo "[entrypoint] ERROR: neither GH_TOKEN nor a gh session. See section 4.2." >&2
    exit 3
fi

exec python3 -m forgeron "$@"
