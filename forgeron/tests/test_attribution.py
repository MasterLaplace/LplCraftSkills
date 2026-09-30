"""The barrier against AI attribution, on its three layers.

The author of this repository refuses a `Co-Authored-By: Claude` in their history, and the
harness reinjects the instruction on every update. A rule in a prompt does not
hold against that: the line must not be ABLE to arrive, and if it
arrives anyway, nothing moves forward.
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
        # Co-authoring with a person is legitimate and common. A filter that
        # took this line away would break a useful convention to uphold another one.
        message = "feat: x\n\nCo-authored-by: Alice Martin <alice@example.com>"
        self.assertEqual(attribution.offending_lines(message), ())
        self.assertEqual(attribution.strip(message), message)

    def test_a_body_with_blank_lines_in_the_middle_survives_intact(self) -> None:
        # The filter is about the SHAPE of the line, never its position: a
        # blank line in the middle separates paragraphs and must stay.
        message = "feat: x\n\nFirst paragraph.\n\nSecond paragraph."
        self.assertEqual(attribution.strip(message), message)

    def test_the_trailer_goes_and_the_body_stays(self) -> None:
        message = f"feat: a cache\n\nWhy.\n\n{HARNESS_TRAILER}"
        self.assertEqual(attribution.strip(message), "feat: a cache\n\nWhy.")


class TheGeneratedHook(unittest.TestCase):
    """The hook is DERIVED from the patterns, and it is run for real.

    Two lists of patterns would end up disagreeing, so the layer that
    prevents would stop protecting what the layer that checks refuses. The only
    way to know is to execute the script produced.
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
        self.assertEqual(self.run_hook(f"feat: x\n\nBody.\n\n{HARNESS_TRAILER}"),
                         "feat: x\n\nBody.")

    def test_it_strips_the_generated_line_despite_its_emoji_prefix(self) -> None:
        self.assertEqual(self.run_hook(f"fix: y\n\n{GENERATED_LINE}"), "fix: y")

    def test_it_agrees_with_the_python_side(self) -> None:
        message = f"feat: x\n\nA body.\n\nCo-authored-by: Alice <a@b.c>\n{HARNESS_TRAILER}"
        self.assertEqual(self.run_hook(message), attribution.strip(message))


class TheDriverRefusesToAdvance(unittest.TestCase):
    """The third layer: neither preventive nor bypassable, it looks at the result.

    `git commit --no-verify` skips the hook and a fresh container has none, so
    prevention has two known holes. This one covers them.
    """

    def branch_with(self, message: str) -> Harness:
        harness = Harness()
        harness.step()                                   # plan
        harness.workspace.branch_commits = [("abc1234", message)]
        harness.step()                                   # implement
        return harness

    def test_a_tainted_commit_blocks_the_round(self) -> None:
        harness = self.branch_with(f"feat: a cache\n\n{HARNESS_TRAILER}")
        self.assertEqual(harness.record.phase, Phase.BLOCKED)
        self.assertIn("AI attribution", harness.record.note)

    def test_the_pull_request_names_the_commit_and_the_line(self) -> None:
        harness = self.branch_with(f"feat: a cache\n\n{HARNESS_TRAILER}")
        body = harness.forge.bodies("pr")[-1]
        self.assertIn("abc1234", body)
        self.assertIn("Co-Authored-By", body)
        self.assertTrue(harness.events("attribution_found"))

    def test_a_clean_branch_advances_normally(self) -> None:
        harness = self.branch_with("feat: a cache\n\nAn honest body.")
        self.assertEqual(harness.record.phase, Phase.IMPLEMENTED)

    def test_a_human_co_author_does_not_block(self) -> None:
        harness = self.branch_with("feat: x\n\nCo-authored-by: Alice <a@b.c>")
        self.assertEqual(harness.record.phase, Phase.IMPLEMENTED)


class TheDriverNeverPublishesIt(unittest.TestCase):
    """The hook covers commit messages. It does not cover PR bodies.

    The agent's `summary` and `answers` go verbatim into a comment,
    so this is a fourth path, and it is scrubbed rather than blocked: this text
    belongs to the driver at the moment it publishes it.
    """

    def test_the_agent_summary_is_scrubbed_before_publication(self) -> None:
        harness = Harness()
        harness.agent.work = dict(harness.agent.work,
                                  summary=f"Cache added.\n\n{GENERATED_LINE}")
        harness.step(); harness.step()

        published = "\n".join(harness.forge.bodies())
        self.assertIn("Cache added.", published)
        self.assertNotIn("Generated with", published)

    def test_nothing_published_ever_carries_an_attribution(self) -> None:
        # The assertion is on the OUTPUT and not on the place where the scrubbing is
        # called: a publication path added later without scrubbing must
        # make this test fail.
        harness = Harness()
        harness.agent.work = dict(harness.agent.work,
                                  summary=f"Done.\n{HARNESS_TRAILER}",
                                  answers=[f"Renamed.\n{GENERATED_LINE}"])
        harness.forge.ci_green()
        for _ in range(4):
            harness.step()
        harness.forge.human_says("This name is vague.")
        for _ in range(3):
            harness.step()

        for body in harness.forge.bodies():
            self.assertEqual(attribution.offending_lines(body), (),
                             f"attribution published in: {body[:120]}")


if __name__ == "__main__":
    unittest.main()
