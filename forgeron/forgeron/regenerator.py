"""Vérifie qu'une commande reproduit bien le fichier qu'elle prétend produire.

Un port à une seule méthode, et son nom dit ce qu'il fait plutôt que ce qu'il
utilise. « Lancer une commande » serait une capacité bien plus large à confier à
un agent ; « vérifier que cette commande reproduit ce fichier » est bornée par sa
propre signature.

Le geste qui compte est le déplacement : le fichier est écarté AVANT de relancer,
et il doit revenir. Sans ça, une commande qui ne fait rien du tout passe le
contrôle, puisque le fichier était déjà là. C'est le piège que ce dépôt a payé
cinq fois, une vérification incapable d'échouer.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import subprocess

# GitHub ne rend que ça dans un commentaire. Une extension hors liste est refusée
# plutôt qu'envoyée : un fichier qui ne s'affiche pas est un lien mort au milieu
# d'une revue, et l'auteur ne le verra pas puisqu'il ne relit pas sa propre PR.
RENDERABLE = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm", ".mov")


@dataclasses.dataclass(frozen=True, slots=True)
class Reproduction:
    ok: bool
    reason: str = ""
    identical: bool = False   # les octets sont-ils les mêmes, donc le rendu est-il déterministe


class ShellRegenerator:
    def __init__(self, timeout_seconds: int = 120, max_bytes: int = 10 * 1024 * 1024) -> None:
        self._timeout = timeout_seconds
        self._max_bytes = max_bytes

    def reproduce(self, worktree: str, path: str, command: str) -> Reproduction:
        """Écarte le fichier, relance la commande, exige qu'il revienne.

        Restaure l'original quoi qu'il arrive : un contrôle qui détruit l'artefact
        qu'il examine transforme un refus en perte de travail.
        """
        root = os.path.realpath(worktree)
        target = os.path.realpath(os.path.join(root, path))

        # Le chemin vient de l'agent et le fichier part sur une forge. Un chemin
        # qui sort du worktree publierait ce que personne n'a proposé de publier.
        if os.path.commonpath([root, target]) != root:
            return Reproduction(False, f"chemin hors du worktree : {path}")
        if os.path.splitext(target)[1].lower() not in RENDERABLE:
            return Reproduction(False, f"extension non rendue par la forge : {path}")
        if not os.path.isfile(target):
            return Reproduction(False, f"fichier absent : {path}")

        size = os.path.getsize(target)
        if size > self._max_bytes:
            return Reproduction(False, f"{size} octets, au-dessus du plafond de {self._max_bytes}")

        before = _digest(target)
        aside = target + ".forgeron-aside"
        os.replace(target, aside)
        try:
            done = subprocess.run(command, shell=True, cwd=root, capture_output=True,
                                  text=True, timeout=self._timeout)
        except subprocess.TimeoutExpired:
            os.replace(aside, target)
            return Reproduction(False, f"la commande a depasse {self._timeout} s")
        except Exception as failure:
            os.replace(aside, target)
            return Reproduction(False, f"{type(failure).__name__}: {failure}")

        if done.returncode != 0:
            os.replace(aside, target)
            detail = (done.stderr or done.stdout).strip().splitlines()
            return Reproduction(False, f"la commande sort en {done.returncode} : "
                                       f"{detail[-1][:160] if detail else 'aucune sortie'}")

        if not os.path.isfile(target):
            os.replace(aside, target)
            return Reproduction(False, "la commande a reussi sans reproduire le fichier")

        # Le fichier est revenu : la commande le produit bel et bien. L'identité
        # des octets est une information de PLUS, pas la condition — un encodeur
        # qui date ses images reste un producteur légitime.
        identical = _digest(target) == before
        os.remove(aside)
        return Reproduction(True, "reproduit" + ("" if identical else " (octets differents)"),
                            identical)


def _digest(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()
