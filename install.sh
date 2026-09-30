#!/usr/bin/env bash
# Installs the craft pack into ~/.claude/skills, so that it is available in ALL
# Claude Code sessions, whatever the repository open.
#
# By default it places LINKS to this repository (junctions on Windows, symbolic links
# elsewhere): a single source of truth, so no copy that will diverge. Editing in the
# repository or in ~/.claude/skills becomes the same file.
#
# See ./install.sh --help
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO_ROOT/skills"
DEST="${HOME}/.claude/skills"

SKILLS=(
  cycle-de-dev
  explorer-le-code
  challenger-le-sujet
  cadrer-et-planifier
  concevoir-avant-coder
  tests-first
  code-comme-poesie
  commencer-ferme
  doc-derivee
  journal-et-debogueur
  trouver-la-cause
  mesure-et-telemetrie
  rendre-l-etat-visible
  se-faire-comprendre
  tracer-le-travail
  relire-une-pr
  garder-les-frontieres
  tenir-la-forge
)

AGENTS=(
  artisan
  essayeur
)
AGENT_SRC="$REPO_ROOT/agents"
AGENT_DEST="${HOME}/.claude/agents"
AGENT_MARK='craft-skills : copie generee par install.sh'

MODE=link   # link (default) | copy
ACTION=install

usage() {
  cat <<'EOF'
install.sh -- installs the craft pack into ~/.claude/skills and ~/.claude/agents

SYNOPSIS
  ./install.sh [--copy] [--status] [--uninstall] [--help]

WHAT IT DOES TO THE WORLD
  WRITES into ~/.claude/skills and ~/.claude/agents (creates the directories if needed).
  Never touches this repository, nor your git configuration, nor anything else.

AGENTS
  The `artisan` and `essayeur` agents (agents/*.md) are GENERATED, never linked: their
  hooks call agents/hooks/*-gate.cjs through the absolute path of this repository. After
  changing a file in agents/, run ./install.sh again (--status says whether a copy
  is stale). Their hooks require `node`.
  Usage: claude --agent artisan    (work according to the pack)
         claude --agent essayeur   (review a PR, without publishing anything)

MODES
  (default)     places one LINK per skill to this repository: a junction on Windows, a
                symbolic link elsewhere. A single source of truth.
  --copy        copies the files instead of linking. Use it when links are
                impossible, or to install on a machine without this repository. WARNING:
                two copies will diverge.
  --status      writes nothing; says for each skill whether it is linked, copied or missing,
                and reports a link whose target has disappeared.
  --uninstall   removes from the destination directory only the entries of this pack.

REFUSAL
  If a destination already exists as a REAL directory and its content DIFFERS from
  the repository's, the script REFUSES and names the files at fault, rather than
  overwrite unversioned work. Same rule for an agent: a file with the same name that
  does not carry this repository's mark is never overwritten.

EXIT CODES
  0  success
  1  invalid usage
  2  conflict: a destination differs from the repository (nothing was written for it)
  3  environment: link creation impossible (try --copy)

EXAMPLES
  ./install.sh                # installs as links
  ./install.sh --status       # what is the current installation worth?
  ./install.sh --copy         # machine without this repository, or links forbidden
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --copy)      MODE=copy ;;
    --status)    ACTION=status ;;
    --uninstall) ACTION=uninstall ;;
    -h|--help)   usage; exit 0 ;;
    *)           echo "Unknown argument: $1" >&2; echo "See ./install.sh --help" >&2; exit 1 ;;
  esac
  shift
done

is_windows() { case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) return 0 ;; *) return 1 ;; esac; }

to_win() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else echo "$1"; fi
}

craft_root_for_hooks() {
  if is_windows && command -v cygpath >/dev/null 2>&1; then cygpath -m "$REPO_ROOT"; else echo "$REPO_ROOT"; fi
}

render_agent() {
  sed "s|{{CRAFT_ROOT}}|$(craft_root_for_hooks)|g" "$AGENT_SRC/$1.md"
}

has_mark() { [[ -f "$1" ]] && grep -qF "$AGENT_MARK" "$1"; }

# Git Bash presents an NTFS junction as a symbolic link: -L and readlink are enough
# on both sides, without asking cmd.
is_link()     { [[ -L "$1" ]]; }
link_target() { readlink "$1" 2>/dev/null; }

make_link() {
  local target="$1" link="$2"
  if is_windows; then
    # A JUNCTION (/J) requires NEITHER administrator rights NOR developer mode,
    # unlike a Windows symbolic link.
    #
    # TRAP ALREADY PAID FOR: NEVER set MSYS_NO_PATHCONV=1 on this line. The `//c` idiom
    # exists BECAUSE MSYS converts `//c` into `/c`; turning the conversion off makes
    # cmd receive `//c` literally, and it prints its banner, creates nothing, and
    # returns 0. A silent no-op with a zero exit code.
    cmd //c mklink //J "$(to_win "$link")" "$(to_win "$target")" >/dev/null
  else
    ln -s "$target" "$link"
  fi
  # The command's exit code proves NOTHING (see the trap above):
  # the only proof is to read back through the link.
  [[ -f "$link/SKILL.md" ]]
}

case "$ACTION" in
  status)
    echo "repository  : $REPO_ROOT"
    echo "destination : $DEST"
    echo
    for s in "${SKILLS[@]}"; do
      d="$DEST/$s"
      if [[ ! -e "$d" ]]; then
        printf '  [ ] %-24s missing\n' "$s"
      elif is_link "$d"; then
        t="$(link_target "$d")"
        if [[ -f "$d/SKILL.md" ]]; then
          printf '  [L] %-24s link -> %s\n' "$s" "${t:-<unreadable target>}"
        else
          printf '  [!] %-24s BROKEN LINK -> %s\n' "$s" "${t:-<unreadable target>}"
        fi
      else
        if diff -rq "$SRC/$s" "$d" >/dev/null 2>&1; then
          printf '  [C] %-24s copy, identical to the repository\n' "$s"
        else
          printf '  [C] %-24s copy, DIFFERS from the repository\n' "$s"
        fi
      fi
    done
    echo
    echo "agents      : $AGENT_DEST"
    for a in "${AGENTS[@]}"; do
      d="$AGENT_DEST/$a.md"
      if [[ ! -e "$d" ]]; then
        printf '  [ ] %-24s missing\n' "$a"
      elif ! has_mark "$d"; then
        printf '  [!] %-24s FOREIGN file (without the mark of this repository), not managed\n' "$a"
      elif diff -q <(render_agent "$a") "$d" >/dev/null 2>&1; then
        printf '  [G] %-24s generated, up to date\n' "$a"
      else
        printf '  [G] %-24s generated, STALE: run ./install.sh again\n' "$a"
      fi
    done
    command -v node >/dev/null 2>&1 \
      || echo "  WARNING: node not found, the agents' hooks will not be able to run."
    exit 0
    ;;

  uninstall)
    for s in "${SKILLS[@]}"; do
      d="$DEST/$s"
      [[ -e "$d" || -L "$d" ]] || continue
      # Same rule as at installation: on a link, rm -f removes the link, never its target.
      if is_link "$d"; then rm -f "$d"; else rm -rf "$d"; fi
      echo "[removed] $s"
    done
    for a in "${AGENTS[@]}"; do
      d="$AGENT_DEST/$a.md"
      [[ -e "$d" ]] || continue
      if has_mark "$d"; then rm -f "$d"; echo "[removed] agent $a"
      else echo "[kept   ] agent $a: foreign file, not generated by this repository"; fi
    done
    echo
    echo "The repository was not touched."
    exit 0
    ;;
esac

# --- installation ---------------------------------------------------------------------

[[ -d "$SRC" ]] || { echo "ERROR: $SRC not found (incomplete repository?)" >&2; exit 3; }
mkdir -p "$DEST"

conflicts=0
for s in "${SKILLS[@]}"; do
  src="$SRC/$s"
  dst="$DEST/$s"

  [[ -d "$src" ]] || { echo "ERROR: $src not found" >&2; exit 3; }

  if [[ -e "$dst" ]] && ! is_link "$dst"; then
    if ! diff -rq "$src" "$dst" >/dev/null 2>&1; then
      echo "REFUSED: $dst is a real directory whose content DIFFERS from the repository." >&2
      diff -rq "$src" "$dst" 2>&1 | sed 's/^/       /' >&2
      echo "       Nothing was written for this skill. Settle the difference, then run again." >&2
      conflicts=$((conflicts + 1))
      continue
    fi
  fi

  # At this point: missing, or a link, or an identical copy -> it can be replaced without loss.
  if [[ -e "$dst" || -L "$dst" ]]; then
    # On a link, `rm -f` removes the link and NEVER its target.
    if is_link "$dst"; then rm -f "$dst"; else rm -rf "$dst"; fi
  fi

  if [[ "$MODE" == copy ]]; then
    cp -r "$src" "$dst"
    echo "[copy ] $s"
  else
    if ! make_link "$src" "$dst"; then
      echo "ERROR: unusable link for $s (reading SKILL.md back is impossible)." >&2
      echo "       Try again with --copy." >&2
      exit 3
    fi
    echo "[link ] $s"
  fi
done

mkdir -p "$AGENT_DEST"
for a in "${AGENTS[@]}"; do
  src="$AGENT_SRC/$a.md"
  dst="$AGENT_DEST/$a.md"
  [[ -f "$src" ]] || { echo "ERROR: $src not found" >&2; exit 3; }
  if [[ -e "$dst" ]] && ! has_mark "$dst"; then
    echo "REFUSED: $dst exists and does not carry this repository's mark: it is not our copy." >&2
    echo "       Nothing was written for this agent. Rename or remove this file, then run again." >&2
    conflicts=$((conflicts + 1))
    continue
  fi
  render_agent "$a" > "$dst"
  has_mark "$dst" || { echo "ERROR: $dst unreadable after writing." >&2; exit 3; }
  echo "[agent] $a (generated)"
done
command -v node >/dev/null 2>&1 \
  || echo "WARNING: node not found; the agents' hooks will not run as long as it is missing." >&2

echo
if [[ $conflicts -gt 0 ]]; then
  echo "$conflicts item(s) not installed because of a conflict. See above." >&2
  exit 2
fi

echo "Installed: ${#SKILLS[@]} skills in $DEST, ${#AGENTS[@]} agent(s) in $AGENT_DEST"
echo "Agents: claude --agent artisan | claude --agent essayeur"
[[ "$MODE" == link ]] && echo "LINK mode: editing in the repository or in the destination is equivalent."
echo "Restart the Claude Code session for the skills to appear."
echo "Check: ./install.sh --status"
