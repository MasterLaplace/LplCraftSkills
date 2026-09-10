"""Ce que le pilote fait du verdict du vérificateur.

`test-regenerator` prouve le verdict contre un vrai disque ; ici on prouve la
décision qui l'entoure, avec des doubles : qu'est-ce qui est attaché, qu'est-ce
qui est écarté, et qu'est-ce que le relecteur en apprend.
"""

from __future__ import annotations

import unittest

from tests.test_engine import Harness

IMAGE = {"path": "rendu.png", "caption": "avant et apres la correction",
         "command": "xmake run test-terrain-render --dump rendu.png"}


def with_visuals(harness: Harness, *visuals) -> None:
    harness.agent.work = dict(harness.agent.work, visuals=list(visuals))


class AcceptedVisual(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = Harness()
        with_visuals(self.harness, IMAGE)
        self.harness.step()          # plan
        self.harness.step()          # implement, avec le visuel

    def test_the_command_is_run_before_anything_is_uploaded(self) -> None:
        self.assertEqual(self.harness.regenerator.calls,
                         [(IMAGE["path"], IMAGE["command"])])

    def test_it_is_attached_with_its_caption(self) -> None:
        self.assertEqual(self.harness.forge.attachments,
                         [(IMAGE["path"], IMAGE["caption"])])

    def test_the_comment_publishes_the_command_that_regenerates_it(self) -> None:
        # La regle de `rendre-l-etat-visible` doit etre visible pour le LECTEUR :
        # sans cette ligne il ne peut pas savoir si l'image decrit encore le code.
        body = self.harness.forge.bodies("pr")[-1]
        self.assertIn("#### Visuels", body)
        self.assertIn(IMAGE["command"], body)

    def test_the_body_references_the_local_path_so_the_forge_rewrites_it(self) -> None:
        # gh remplace une reference deja presente par l'URL televersee, et ajoute
        # a la fin celles qu'il ne trouve pas. Referencer place donc l'image ou
        # elle a du sens plutot qu'en vrac en bas.
        body = self.harness.forge.bodies("pr")[-1]
        self.assertIn(f"![{IMAGE['caption']}]({IMAGE['path']})", body)


class RefusedVisual(unittest.TestCase):
    def test_a_visual_whose_command_does_not_reproduce_it_is_never_uploaded(self) -> None:
        harness = Harness()
        harness.regenerator.refuse[IMAGE["path"]] = "la commande a reussi sans reproduire le fichier"
        with_visuals(harness, IMAGE)
        harness.step()
        harness.step()

        self.assertEqual(harness.forge.attachments, [])
        body = harness.forge.bodies("pr")[-1]
        self.assertIn("ecarte", body)
        self.assertIn("sans reproduire", body)

    def test_the_refusal_is_said_rather_than_silent(self) -> None:
        # Un relecteur doit savoir qu'il manque quelque chose, plutot que de croire
        # qu'il n'y avait rien a montrer.
        harness = Harness()
        harness.regenerator.refuse[IMAGE["path"]] = "extension non rendue par la forge"
        with_visuals(harness, IMAGE)
        harness.step(); harness.step()

        checked = harness.events("visual_checked")
        self.assertEqual(len(checked), 1)
        self.assertFalse(checked[0]["ok"])
        self.assertIn("extension", checked[0]["reason"])


class WhenTheMechanismIsAbsent(unittest.TestCase):
    def test_without_a_verifier_nothing_is_attached_and_the_reason_is_given(self) -> None:
        # Degrader la pretention du resultat, jamais la barre : on n'attache pas
        # sans verifier, et on ne fait pas semblant qu'il n'y avait rien.
        from forgeron.engine import Engine
        harness = Harness()
        harness.engine = Engine(harness.config, harness.forge, harness.workspace,
                                harness.agent, harness.store, harness.journal)
        with_visuals(harness, IMAGE)
        harness.step(); harness.step()

        self.assertEqual(harness.forge.attachments, [])
        self.assertIn("aucun verificateur", harness.forge.bodies("pr")[-1])

    def test_an_old_gh_refuses_the_upload_instead_of_failing_mid_run(self) -> None:
        harness = Harness()
        harness.forge.attachments_supported = False
        with_visuals(harness, IMAGE)
        harness.step(); harness.step()

        self.assertEqual(harness.forge.attachments, [])
        self.assertIn("2.99.0", harness.forge.bodies("pr")[-1])
        self.assertEqual(harness.regenerator.calls, [],
                         "inutile de regenerer ce qu'on ne pourra pas televerser")


class TheCeiling(unittest.TestCase):
    def test_beyond_the_ceiling_the_extra_are_refused_with_their_reason(self) -> None:
        from forgeron.engine import MAX_VISUALS
        harness = Harness()
        many = [dict(IMAGE, path=f"rendu{index}.png") for index in range(MAX_VISUALS + 2)]
        with_visuals(harness, *many)
        harness.step(); harness.step()

        self.assertEqual(len(harness.forge.attachments), MAX_VISUALS)
        self.assertEqual(len(harness.regenerator.calls), MAX_VISUALS,
                         "on ne paie pas la regeneration de ce qu'on n'attachera pas")
        body = harness.forge.bodies("pr")[-1]
        self.assertIn("au-dela du plafond", body)


class NoVisualAtAll(unittest.TestCase):
    def test_the_common_case_costs_nothing(self) -> None:
        harness = Harness()
        harness.step(); harness.step()
        self.assertEqual(harness.regenerator.calls, [])
        self.assertEqual(harness.forge.attachments, [])
        self.assertNotIn("#### Visuels", harness.forge.bodies("pr")[-1])


if __name__ == "__main__":
    unittest.main()
