"""What the driver does with the verifier's verdict.

`test-regenerator` proves the verdict against a real disk; here we prove the
decision around it, with doubles: what is attached, what
is set aside, and what the reviewer learns from it.
"""

from __future__ import annotations

import unittest

from tests.test_engine import Harness

IMAGE = {"path": "render.png", "caption": "before and after the fix",
         "command": "xmake run test-terrain-render --dump render.png"}


def with_visuals(harness: Harness, *visuals) -> None:
    harness.agent.work = dict(harness.agent.work, visuals=list(visuals))


class AcceptedVisual(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = Harness()
        with_visuals(self.harness, IMAGE)
        self.harness.step()          # plan
        self.harness.step()          # implement, with the visual

    def test_the_command_is_run_before_anything_is_uploaded(self) -> None:
        self.assertEqual(self.harness.regenerator.calls,
                         [(IMAGE["path"], IMAGE["command"])])

    def test_it_is_attached_with_its_caption(self) -> None:
        self.assertEqual(self.harness.forge.attachments,
                         [(IMAGE["path"], IMAGE["caption"])])

    def test_the_comment_publishes_the_command_that_regenerates_it(self) -> None:
        # The rule of `rendre-l-etat-visible` must be visible to the READER:
        # without this line they cannot know whether the image still describes the code.
        body = self.harness.forge.bodies("pr")[-1]
        self.assertIn("#### Visuals", body)
        self.assertIn(IMAGE["command"], body)

    def test_the_body_references_the_local_path_so_the_forge_rewrites_it(self) -> None:
        # gh replaces a reference already present with the uploaded URL, and appends
        # at the end the ones it does not find. Referencing therefore places the image where
        # it makes sense rather than dumped at the bottom.
        body = self.harness.forge.bodies("pr")[-1]
        self.assertIn(f"![{IMAGE['caption']}]({IMAGE['path']})", body)


class RefusedVisual(unittest.TestCase):
    def test_a_visual_whose_command_does_not_reproduce_it_is_never_uploaded(self) -> None:
        harness = Harness()
        harness.regenerator.refuse[IMAGE["path"]] = "the command succeeded without reproducing the file"
        with_visuals(harness, IMAGE)
        harness.step()
        harness.step()

        self.assertEqual(harness.forge.attachments, [])
        body = harness.forge.bodies("pr")[-1]
        self.assertIn("set aside", body)
        self.assertIn("without reproducing", body)

    def test_the_refusal_is_said_rather_than_silent(self) -> None:
        # A reviewer must know that something is missing, rather than believe
        # there was nothing to show.
        harness = Harness()
        harness.regenerator.refuse[IMAGE["path"]] = "extension not rendered by the forge"
        with_visuals(harness, IMAGE)
        harness.step(); harness.step()

        checked = harness.events("visual_checked")
        self.assertEqual(len(checked), 1)
        self.assertFalse(checked[0]["ok"])
        self.assertIn("extension", checked[0]["reason"])


class WhenTheMechanismIsAbsent(unittest.TestCase):
    def test_without_a_verifier_nothing_is_attached_and_the_reason_is_given(self) -> None:
        # Lower the claim of the result, never the bar: nothing is attached
        # without checking, and nobody pretends there was nothing.
        from forgeron.engine import Engine
        harness = Harness()
        harness.engine = Engine(harness.config, harness.forge, harness.workspace,
                                harness.agent, harness.store, harness.journal)
        with_visuals(harness, IMAGE)
        harness.step(); harness.step()

        self.assertEqual(harness.forge.attachments, [])
        self.assertIn("no regeneration verifier", harness.forge.bodies("pr")[-1])

    def test_an_old_gh_refuses_the_upload_instead_of_failing_mid_run(self) -> None:
        harness = Harness()
        harness.forge.attachments_supported = False
        with_visuals(harness, IMAGE)
        harness.step(); harness.step()

        self.assertEqual(harness.forge.attachments, [])
        self.assertIn("2.99.0", harness.forge.bodies("pr")[-1])
        self.assertEqual(harness.regenerator.calls, [],
                         "no point regenerating what cannot be uploaded")


class TheCeiling(unittest.TestCase):
    def test_beyond_the_ceiling_the_extra_are_refused_with_their_reason(self) -> None:
        from forgeron.engine import MAX_VISUALS
        harness = Harness()
        many = [dict(IMAGE, path=f"render{index}.png") for index in range(MAX_VISUALS + 2)]
        with_visuals(harness, *many)
        harness.step(); harness.step()

        self.assertEqual(len(harness.forge.attachments), MAX_VISUALS)
        self.assertEqual(len(harness.regenerator.calls), MAX_VISUALS,
                         "regeneration is not paid for what will not be attached")
        body = harness.forge.bodies("pr")[-1]
        self.assertIn("beyond the ceiling", body)


class NoVisualAtAll(unittest.TestCase):
    def test_the_common_case_costs_nothing(self) -> None:
        harness = Harness()
        harness.step(); harness.step()
        self.assertEqual(harness.regenerator.calls, [])
        self.assertEqual(harness.forge.attachments, [])
        self.assertNotIn("#### Visuals", harness.forge.bodies("pr")[-1])


if __name__ == "__main__":
    unittest.main()
