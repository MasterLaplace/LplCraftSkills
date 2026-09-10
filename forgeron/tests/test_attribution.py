"""La barrière contre l'attribution IA, sur ses trois couches.

L'auteur de ce dépôt refuse un `Co-Authored-By: Claude` dans son historique, et le
harnais réinjecte la consigne à chaque mise à jour. Une règle dans un prompt ne
tient pas contre ça : il faut que la ligne ne PUISSE pas arriver, et que si elle
arrive quand même, rien n'avance.
"""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest

from forgeron import attribution
from forgeron.model import Phase
from tests.test_engine import Harness

HARNESS_TRAILER = "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
GENERATED_LINE = "🤖 Generated with [Claude Code](https://claude.com/claude-code)"


class WhatCounts(unittest.TestCase):
    def test_the_two_lines_the_harness_pushes_are_caught(self) -> None:
        for line in (HARNESS_TRAILER, GENERATED_LINE, "Claude-session: abc123"):
            with self.subTest(line=line[:40]):
                self.assertEqual(len(attribution.offending_lines(f"feat: x\n\n{line}")), 1)

    def test_a_human_co_author_is_left_alone(self) -> None:
        # Co-auteurer avec une personne est legitime et courant. Un filtre qui
        # emporterait cette ligne casserait une convention utile pour en tenir une autre.
        message = "feat: x\n\nCo-authored-by: Alice Martin <alice@example.com>"
        self.assertEqual(attribution.offending_lines(message), ())
        self.assertEqual(attribution.strip(message), message)

    def test_a_body_with_blank_lines_in_the_middle_survives_intact(self) -> None:
        # Le filtre porte sur la FORME de la ligne, jamais sur sa position : une
        # ligne vide au milieu separe des paragraphes et doit rester.
        message = "feat: x\n\nPremier paragraphe.\n\nSecond paragraphe."
        self.assertEqual(attribution.strip(message), message)

    def test_the_trailer_goes_and_the_body_stays(self) -> None:
        message = f"feat: un cache\n\nPourquoi.\n\n{HARNESS_TRAILER}"
        self.assertEqual(attribution.strip(message), "feat: un cache\n\nPourquoi.")


class TheGeneratedHook(unittest.TestCase):
    """Le hook est DERIVE des motifs, et on le fait tourner pour de vrai.

    Deux listes de motifs finiraient par ne pas s'accorder, donc la couche qui
    previent cesserait de proteger ce que la couche qui verifie refuse. Le seul
    moyen de le savoir est d'executer le script produit.
    """

    def run_hook(self, message: str) -> str:
        root = tempfile.mkdtemp()
        hook = os.path.join(root, "commit-msg")
        with open(hook, "w", encoding="utf-8") as handle:
            handle.write(attribution.hook_script())
        os.chmod(hook, os.stat(hook).st_mode | stat.S_IEXEC)

        target = os.path.join(root, "COMMIT_EDITMSG")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(message)
        done = subprocess.run([hook, target], capture_output=True, text=True, timeout=10)
        self.assertEqual(done.returncode, 0, done.stderr)
        with open(target, encoding="utf-8") as handle:
            return handle.read().rstrip("\n")

    def test_it_strips_what_the_patterns_declare(self) -> None:
        self.assertEqual(self.run_hook(f"feat: x\n\nCorps.\n\n{HARNESS_TRAILER}"),
                         "feat: x\n\nCorps.")

    def test_it_strips_the_generated_line_despite_its_emoji_prefix(self) -> None:
        self.assertEqual(self.run_hook(f"fix: y\n\n{GENERATED_LINE}"), "fix: y")

    def test_it_agrees_with_the_python_side(self) -> None:
        message = f"feat: x\n\nUn corps.\n\nCo-authored-by: Alice <a@b.c>\n{HARNESS_TRAILER}"
        self.assertEqual(self.run_hook(message), attribution.strip(message))


class TheDriverRefusesToAdvance(unittest.TestCase):
    """La troisieme couche : ni prevenue ni contournable, elle regarde le resultat.

    `git commit --no-verify` saute le hook et un conteneur neuf n'en a aucun, donc
    la prevention a deux trous connus. Celle-ci les couvre.
    """

    def branch_with(self, message: str) -> Harness:
        harness = Harness()
        harness.step()                                   # plan
        harness.workspace.branch_commits = [("abc1234", message)]
        harness.step()                                   # implement
        return harness

    def test_a_tainted_commit_blocks_the_round(self) -> None:
        harness = self.branch_with(f"feat: un cache\n\n{HARNESS_TRAILER}")
        self.assertEqual(harness.record.phase, Phase.BLOCKED)
        self.assertIn("attribution IA", harness.record.note)

    def test_the_pull_request_names_the_commit_and_the_line(self) -> None:
        harness = self.branch_with(f"feat: un cache\n\n{HARNESS_TRAILER}")
        body = harness.forge.bodies("pr")[-1]
        self.assertIn("abc1234", body)
        self.assertIn("Co-Authored-By", body)
        self.assertTrue(harness.events("attribution_found"))

    def test_a_clean_branch_advances_normally(self) -> None:
        harness = self.branch_with("feat: un cache\n\nUn corps honnete.")
        self.assertEqual(harness.record.phase, Phase.IMPLEMENTED)

    def test_a_human_co_author_does_not_block(self) -> None:
        harness = self.branch_with("feat: x\n\nCo-authored-by: Alice <a@b.c>")
        self.assertEqual(harness.record.phase, Phase.IMPLEMENTED)


class TheDriverNeverPublishesIt(unittest.TestCase):
    """Le hook couvre les messages de commit. Il ne couvre pas les corps de PR.

    Le `summary` et les `answers` de l'agent partent verbatim dans un commentaire,
    donc c'est un quatrieme chemin, et il est nettoye plutot que bloque : ce texte
    appartient au pilote au moment ou il le publie.
    """

    def test_the_agent_summary_is_scrubbed_before_publication(self) -> None:
        harness = Harness()
        harness.agent.work = dict(harness.agent.work,
                                  summary=f"Cache ajoute.\n\n{GENERATED_LINE}")
        harness.step(); harness.step()

        published = "\n".join(harness.forge.bodies())
        self.assertIn("Cache ajoute.", published)
        self.assertNotIn("Generated with", published)

    def test_nothing_published_ever_carries_an_attribution(self) -> None:
        # L'assertion porte sur la SORTIE et pas sur l'endroit ou le nettoyage est
        # appele : un chemin de publication ajoute plus tard sans nettoyage doit
        # faire echouer ce test.
        harness = Harness()
        harness.agent.work = dict(harness.agent.work,
                                  summary=f"Fait.\n{HARNESS_TRAILER}",
                                  answers=[f"Renomme.\n{GENERATED_LINE}"])
        harness.forge.ci_green()
        for _ in range(4):
            harness.step()
        harness.forge.human_says("Ce nom est vague.")
        for _ in range(3):
            harness.step()

        for body in harness.forge.bodies():
            self.assertEqual(attribution.offending_lines(body), (),
                             f"attribution publiee dans : {body[:120]}")


if __name__ == "__main__":
    unittest.main()
