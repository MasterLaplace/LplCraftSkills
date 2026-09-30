"""The verifier, against a real disk. No fake here, and that is deliberate.

What it promises is that a command reproduces a file. Proving it against a
double would amount to asking the double to confirm, and the failure we want to
catch is precisely the one that looks fine: a command that does
nothing, in front of a file already present.
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
        self.write("render.png", b"PIXELS")

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

    # -- the case that must pass ---------------------------------------------

    def test_a_command_that_rebuilds_the_file_is_accepted(self) -> None:
        outcome = self.reproduce("render.png", "printf 'PIXELS' > render.png")
        self.assertTrue(outcome.ok, outcome.reason)
        self.assertTrue(outcome.identical, "same bytes, so a deterministic render")
        self.assertEqual(self.read("render.png"), b"PIXELS")

    def test_a_producer_that_is_not_byte_stable_is_still_accepted(self) -> None:
        # An encoder that timestamps its images is still a legitimate producer: what is
        # required is reproducibility, not determinism. The difference is
        # reported rather than refused.
        outcome = self.reproduce("render.png", "printf 'PIXELS-%s' $$ > render.png")
        self.assertTrue(outcome.ok, outcome.reason)
        self.assertFalse(outcome.identical)
        self.assertIn("different bytes", outcome.reason)

    # -- the cases that must fail, and the original must survive ------------

    def test_a_command_that_does_nothing_is_refused(self) -> None:
        # THE test. Without setting the file aside, the file is already there and the
        # most useless command in the world passes the check.
        outcome = self.reproduce("render.png", "true")
        self.assertFalse(outcome.ok)
        self.assertIn("without reproducing", outcome.reason)
        self.assertEqual(self.read("render.png"), b"PIXELS", "the original is restored")

    def test_a_failing_command_is_refused_and_the_file_survives(self) -> None:
        outcome = self.reproduce("render.png", "rm render.png; echo 'boom' >&2; exit 3")
        self.assertFalse(outcome.ok)
        self.assertIn("exits with 3", outcome.reason)
        self.assertIn("boom", outcome.reason)
        self.assertEqual(self.read("render.png"), b"PIXELS")

    def test_a_command_that_hangs_is_refused_and_the_file_survives(self) -> None:
        outcome = self.reproduce("render.png", "sleep 30")
        self.assertFalse(outcome.ok)
        self.assertIn("exceeded", outcome.reason)
        self.assertEqual(self.read("render.png"), b"PIXELS")

    # -- what must not even be attempted ----------------------------------

    def test_a_path_leaving_the_worktree_is_refused(self) -> None:
        # The path comes from the agent and the file goes to a forge: publishing
        # outside the worktree would publish what nobody offered to publish.
        outcome = self.reproduce("../../secret.png", "true")
        self.assertFalse(outcome.ok)
        self.assertIn("outside the worktree", outcome.reason)

    def test_an_extension_the_forge_does_not_render_is_refused(self) -> None:
        self.write("notes.txt", b"x")
        outcome = self.reproduce("notes.txt", "true")
        self.assertFalse(outcome.ok)
        self.assertIn("not rendered", outcome.reason)

    def test_a_missing_file_is_refused(self) -> None:
        outcome = self.reproduce("never-written.png", "true")
        self.assertFalse(outcome.ok)
        self.assertIn("missing", outcome.reason)

    def test_a_file_above_the_ceiling_is_refused(self) -> None:
        small = ShellRegenerator(timeout_seconds=2, max_bytes=4)
        outcome = small.reproduce(self.root, "render.png", "true")
        self.assertFalse(outcome.ok)
        self.assertIn("ceiling", outcome.reason)
        self.assertEqual(self.read("render.png"), b"PIXELS")


if __name__ == "__main__":
    unittest.main()
