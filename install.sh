#!/usr/bin/env bash
# Installe le pack craft dans ~/.claude/skills, pour qu'il soit disponible dans TOUTES
# les sessions Claude Code, quel que soit le depot ouvert.
#
# Par defaut il pose des LIENS vers ce depot (jonctions sous Windows, liens symboliques
# ailleurs) : une seule source de verite, donc aucune copie qui divergera. Editer dans le
# depot ou dans ~/.claude/skills devient le meme fichier.
#
# Voir ./install.sh --help
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
)

AGENTS=(
  artisan
  essayeur
)
AGENT_SRC="$REPO_ROOT/agents"
AGENT_DEST="${HOME}/.claude/agents"
AGENT_MARK='craft-skills : copie generee par install.sh'

MODE=link   # link (defaut) | copy
ACTION=install

usage() {
  cat <<'EOF'
install.sh -- installe le pack craft dans ~/.claude/skills et ~/.claude/agents

SYNOPSIS
  ./install.sh [--copy] [--status] [--uninstall] [--help]

CE QU'IL FAIT DU MONDE
  ECRIT dans ~/.claude/skills et ~/.claude/agents (cree les dossiers au besoin). Ne
  touche jamais a ce depot, ni a votre configuration git, ni a quoi que ce soit d'autre.

AGENTS
  Les agents `artisan` et `essayeur` (agents/*.md) sont GENERES, jamais lies : leurs
  hooks appellent agents/hooks/*-gate.cjs par le chemin absolu de ce depot. Apres une
  modification d'un fichier de agents/, relancer ./install.sh (--status dit si une copie
  est perimee). Leurs hooks demandent `node`.
  Utilisation : claude --agent artisan    (travailler selon le pack)
                claude --agent essayeur   (relire une PR, sans rien publier)

MODES
  (defaut)      pose un LIEN par skill vers ce depot : jonction sous Windows, lien
                symbolique ailleurs. Une seule source de verite.
  --copy        copie les fichiers au lieu de lier. A utiliser quand les liens sont
                impossibles, ou pour installer sur une machine sans ce depot. ATTENTION :
                deux copies divergeront.
  --status      n'ecrit rien ; dit pour chaque skill s.il est lie, copie ou absent,
                et signale un lien dont la cible a disparu.
  --uninstall   retire du dossier de destination les seules entrees de ce pack.

REFUS
  Si une destination existe deja en tant que VRAI dossier et que son contenu DIFFERE de
  celui du depot, le script REFUSE et nomme les fichiers en cause, plutot que d'ecraser
  un travail non versionne. Meme regle pour un agent : un fichier du meme nom qui ne
  porte pas la marque de ce depot n'est jamais ecrase.

CODES DE SORTIE
  0  succes
  1  usage invalide
  2  conflit : une destination differe du depot (rien n'a ete ecrit pour elle)
  3  environnement : creation de lien impossible (essayer --copy)

EXEMPLES
  ./install.sh                # installe en liens
  ./install.sh --status       # que vaut l'installation actuelle ?
  ./install.sh --copy         # machine sans ce depot, ou liens interdits
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --copy)      MODE=copy ;;
    --status)    ACTION=status ;;
    --uninstall) ACTION=uninstall ;;
    -h|--help)   usage; exit 0 ;;
    *)           echo "Argument inconnu: $1" >&2; echo "Voir ./install.sh --help" >&2; exit 1 ;;
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

# Git Bash presente une jonction NTFS comme un lien symbolique : -L et readlink suffisent
# des deux cotes, sans interroger cmd.
is_link()     { [[ -L "$1" ]]; }
link_target() { readlink "$1" 2>/dev/null; }

make_link() {
  local target="$1" link="$2"
  if is_windows; then
    # Une JONCTION (/J) ne demande NI droits administrateur NI mode developpeur,
    # contrairement a un lien symbolique Windows.
    #
    # PIEGE PAYE : ne JAMAIS poser MSYS_NO_PATHCONV=1 sur cette ligne. L'idiome `//c`
    # existe PARCE QUE MSYS convertit `//c` en `/c` ; desactiver la conversion fait
    # recevoir `//c` litteralement par cmd, qui affiche sa banniere, ne cree rien, et
    # rend 0. Un no-op silencieux a code de sortie zero.
    cmd //c mklink //J "$(to_win "$link")" "$(to_win "$target")" >/dev/null
  else
    ln -s "$target" "$link"
  fi
  # Le code de sortie de la commande ne prouve RIEN (voir le piege ci-dessus) :
  # la seule preuve est de relire a travers le lien.
  [[ -f "$link/SKILL.md" ]]
}

case "$ACTION" in
  status)
    echo "depot       : $REPO_ROOT"
    echo "destination : $DEST"
    echo
    for s in "${SKILLS[@]}"; do
      d="$DEST/$s"
      if [[ ! -e "$d" ]]; then
        printf '  [ ] %-24s absente\n' "$s"
      elif is_link "$d"; then
        t="$(link_target "$d")"
        if [[ -f "$d/SKILL.md" ]]; then
          printf '  [L] %-24s lien -> %s\n' "$s" "${t:-<cible illisible>}"
        else
          printf '  [!] %-24s LIEN CASSE -> %s\n' "$s" "${t:-<cible illisible>}"
        fi
      else
        if diff -rq "$SRC/$s" "$d" >/dev/null 2>&1; then
          printf '  [C] %-24s copie, identique au depot\n' "$s"
        else
          printf '  [C] %-24s copie, DIFFERE du depot\n' "$s"
        fi
      fi
    done
    echo
    echo "agents      : $AGENT_DEST"
    for a in "${AGENTS[@]}"; do
      d="$AGENT_DEST/$a.md"
      if [[ ! -e "$d" ]]; then
        printf '  [ ] %-24s absent\n' "$a"
      elif ! has_mark "$d"; then
        printf '  [!] %-24s fichier ETRANGER (sans la marque de ce depot), non gere\n' "$a"
      elif diff -q <(render_agent "$a") "$d" >/dev/null 2>&1; then
        printf '  [G] %-24s genere, a jour\n' "$a"
      else
        printf '  [G] %-24s genere, PERIME : relancer ./install.sh\n' "$a"
      fi
    done
    command -v node >/dev/null 2>&1 \
      || echo "  ATTENTION : node introuvable, les hooks des agents ne pourront pas tourner."
    exit 0
    ;;

  uninstall)
    for s in "${SKILLS[@]}"; do
      d="$DEST/$s"
      [[ -e "$d" || -L "$d" ]] || continue
      # Meme regle que a l'installation : sur un lien, rm -f retire le lien, jamais sa cible.
      if is_link "$d"; then rm -f "$d"; else rm -rf "$d"; fi
      echo "[retire] $s"
    done
    for a in "${AGENTS[@]}"; do
      d="$AGENT_DEST/$a.md"
      [[ -e "$d" ]] || continue
      if has_mark "$d"; then rm -f "$d"; echo "[retire] agent $a"
      else echo "[garde ] agent $a : fichier etranger, pas genere par ce depot"; fi
    done
    echo
    echo "Le depot n'a pas ete touche."
    exit 0
    ;;
esac

# --- installation ---------------------------------------------------------------------

[[ -d "$SRC" ]] || { echo "ERREUR: $SRC introuvable (depot incomplet ?)" >&2; exit 3; }
mkdir -p "$DEST"

conflicts=0
for s in "${SKILLS[@]}"; do
  src="$SRC/$s"
  dst="$DEST/$s"

  [[ -d "$src" ]] || { echo "ERREUR: $src introuvable" >&2; exit 3; }

  if [[ -e "$dst" ]] && ! is_link "$dst"; then
    if ! diff -rq "$src" "$dst" >/dev/null 2>&1; then
      echo "REFUS: $dst est un vrai dossier dont le contenu DIFFERE du depot." >&2
      diff -rq "$src" "$dst" 2>&1 | sed 's/^/       /' >&2
      echo "       Rien n'a ete ecrit pour cette skill. Reglez l'ecart, puis relancez." >&2
      conflicts=$((conflicts + 1))
      continue
    fi
  fi

  # A ce stade : absent, ou lien, ou copie identique -> on peut remplacer sans perte.
  if [[ -e "$dst" || -L "$dst" ]]; then
    # Sur un lien, `rm -f` retire le lien et JAMAIS sa cible.
    if is_link "$dst"; then rm -f "$dst"; else rm -rf "$dst"; fi
  fi

  if [[ "$MODE" == copy ]]; then
    cp -r "$src" "$dst"
    echo "[copie] $s"
  else
    if ! make_link "$src" "$dst"; then
      echo "ERREUR: lien inutilisable pour $s (relecture de SKILL.md impossible)." >&2
      echo "       Reessayez avec --copy." >&2
      exit 3
    fi
    echo "[lien ] $s"
  fi
done

mkdir -p "$AGENT_DEST"
for a in "${AGENTS[@]}"; do
  src="$AGENT_SRC/$a.md"
  dst="$AGENT_DEST/$a.md"
  [[ -f "$src" ]] || { echo "ERREUR: $src introuvable" >&2; exit 3; }
  if [[ -e "$dst" ]] && ! has_mark "$dst"; then
    echo "REFUS: $dst existe et ne porte pas la marque de ce depot : ce n'est pas notre copie." >&2
    echo "       Rien n'a ete ecrit pour cet agent. Renommez ou retirez ce fichier, puis relancez." >&2
    conflicts=$((conflicts + 1))
    continue
  fi
  render_agent "$a" > "$dst"
  has_mark "$dst" || { echo "ERREUR: $dst illisible apres ecriture." >&2; exit 3; }
  echo "[agent] $a (genere)"
done
command -v node >/dev/null 2>&1 \
  || echo "ATTENTION : node introuvable ; les hooks des agents ne tourneront pas tant qu'il manque." >&2

echo
if [[ $conflicts -gt 0 ]]; then
  echo "$conflicts element(s) non installe(s) pour cause de conflit. Voir ci-dessus." >&2
  exit 2
fi

echo "Installe : ${#SKILLS[@]} skills dans $DEST, ${#AGENTS[@]} agent(s) dans $AGENT_DEST"
echo "Agents : claude --agent artisan | claude --agent essayeur"
[[ "$MODE" == link ]] && echo "Mode LIEN : editer dans le depot ou dans la destination est equivalent."
echo "Redemarrer la session Claude Code pour que les skills apparaissent."
echo "Verifier : ./install.sh --status"
