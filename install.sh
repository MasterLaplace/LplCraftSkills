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
  tracer-le-travail
)

MODE=link   # link (defaut) | copy
ACTION=install

usage() {
  cat <<'EOF'
install.sh -- installe le pack craft dans ~/.claude/skills

SYNOPSIS
  ./install.sh [--copy] [--status] [--uninstall] [--help]

CE QU'IL FAIT DU MONDE
  ECRIT dans ~/.claude/skills (cree le dossier au besoin). Ne touche jamais a ce depot,
  ni a votre configuration git, ni a quoi que ce soit d'autre.

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
  un travail non versionne.

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

echo
if [[ $conflicts -gt 0 ]]; then
  echo "$conflicts skill(s) non installe(s) pour cause de conflit. Voir ci-dessus." >&2
  exit 2
fi

echo "Installe : ${#SKILLS[@]} skills dans $DEST"
[[ "$MODE" == link ]] && echo "Mode LIEN : editer dans le depot ou dans la destination est equivalent."
echo "Redemarrer la session Claude Code pour que les skills apparaissent."
echo "Verifier : ./install.sh --status"
