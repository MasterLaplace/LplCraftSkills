"""Le vérificateur, contre un vrai disque. Aucun fake ici, et c'est délibéré.

Ce qu'il promet est qu'une commande reproduit un fichier. Le prouver contre un
double reviendrait à demander au double de confirmer, et la panne qu'on veut
attraper est précisément celle qui a l'air d'aller : une commande qui ne fait
rien, devant un fichier déjà présent.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from forgeron.regenerator import ShellRegenerator


class RealDisk(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tempfile.mkdtemp()
        self.regenerator = ShellRegenerator(timeout_seconds=2)
        self.write("rendu.png", b"PIXELS")

    def write(self, name: str, content: bytes) -> str:
        path = os.path.join(self.root, name)
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    def read(self, name: str) -> bytes:
        with open(os.path.join(self.root, name), "rb") as handle:
            return handle.read()

    def reproduce(self, name: str, command: str):
        return self.regenerator.reproduce(self.root, name, command)

    # -- le cas qui doit passer ---------------------------------------------

    def test_a_command_that_rebuilds_the_file_is_accepted(self) -> None:
        outcome = self.reproduce("rendu.png", "printf 'PIXELS' > rendu.png")
        self.assertTrue(outcome.ok, outcome.reason)
        self.assertTrue(outcome.identical, "memes octets, donc rendu deterministe")
        self.assertEqual(self.read("rendu.png"), b"PIXELS")

    def test_a_producer_that_is_not_byte_stable_is_still_accepted(self) -> None:
        # Un encodeur qui date ses images reste un producteur legitime : ce qui est
        # exige est la reproductibilite, pas le determinisme. La difference est
        # rapportee plutot que refusee.
        outcome = self.reproduce("rendu.png", "printf 'PIXELS-%s' $$ > rendu.png")
        self.assertTrue(outcome.ok, outcome.reason)
        self.assertFalse(outcome.identical)
        self.assertIn("octets differents", outcome.reason)

    # -- les cas qui doivent echouer, et l'original doit survivre ------------

    def test_a_command_that_does_nothing_is_refused(self) -> None:
        # LE test. Sans la mise a l'ecart, le fichier est deja la et la commande
        # la plus inutile du monde passe le controle.
        outcome = self.reproduce("rendu.png", "true")
        self.assertFalse(outcome.ok)
        self.assertIn("sans reproduire", outcome.reason)
        self.assertEqual(self.read("rendu.png"), b"PIXELS", "l'original est restaure")

    def test_a_failing_command_is_refused_and_the_file_survives(self) -> None:
        outcome = self.reproduce("rendu.png", "rm rendu.png; echo 'boum' >&2; exit 3")
        self.assertFalse(outcome.ok)
        self.assertIn("sort en 3", outcome.reason)
        self.assertIn("boum", outcome.reason)
        self.assertEqual(self.read("rendu.png"), b"PIXELS")

    def test_a_command_that_hangs_is_refused_and_the_file_survives(self) -> None:
        outcome = self.reproduce("rendu.png", "sleep 30")
        self.assertFalse(outcome.ok)
        self.assertIn("depasse", outcome.reason)
        self.assertEqual(self.read("rendu.png"), b"PIXELS")

    # -- ce qui ne doit meme pas etre tente ----------------------------------

    def test_a_path_leaving_the_worktree_is_refused(self) -> None:
        # Le chemin vient de l'agent et le fichier part sur une forge : publier
        # hors du worktree publierait ce que personne n'a propose de publier.
        outcome = self.reproduce("../../secret.png", "true")
        self.assertFalse(outcome.ok)
        self.assertIn("hors du worktree", outcome.reason)

    def test_an_extension_the_forge_does_not_render_is_refused(self) -> None:
        self.write("notes.txt", b"x")
        outcome = self.reproduce("notes.txt", "true")
        self.assertFalse(outcome.ok)
        self.assertIn("non rendue", outcome.reason)

    def test_a_missing_file_is_refused(self) -> None:
        outcome = self.reproduce("jamais-ecrit.png", "true")
        self.assertFalse(outcome.ok)
        self.assertIn("absent", outcome.reason)

    def test_a_file_above_the_ceiling_is_refused(self) -> None:
        small = ShellRegenerator(timeout_seconds=2, max_bytes=4)
        outcome = small.reproduce(self.root, "rendu.png", "true")
        self.assertFalse(outcome.ok)
        self.assertIn("plafond", outcome.reason)
        self.assertEqual(self.read("rendu.png"), b"PIXELS")


if __name__ == "__main__":
    unittest.main()
