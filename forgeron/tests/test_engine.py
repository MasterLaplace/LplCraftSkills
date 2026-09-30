"""The whole journey, with fakes: issue to merge, including a red build and a review.

This is the test the design exists for. The state machine can be right case by case
and still be wrong as a sequence - a round that forgets to hand the reviewer's words
to the agent, a verdict believed against git, a comment answered twice. Only walking
the journey shows those.
"""

from __future__ import annotations

import tempfile
import unittest

from forgeron.config import Config, RepoConfig
from forgeron.engine import Engine
from forgeron.journal import Journal
from forgeron.model import FeedbackKind, IssueRef, Phase
from forgeron.states import Limits
from forgeron.store import Store
from tests.fakes import FakeAgent, FakeForge, FakeRegenerator, FakeWorkspace

ISSUE = IssueRef(repo="o/r", number=42, title="Add an LRU cache",
                 body="Repeated reads cost too much.", url="https://fake/42",
                 labels=("claude",))


class Harness:
    def __init__(self, **limits) -> None:
        self.home = tempfile.mkdtemp()
        self.config = Config(
            home=self.home,
            repos=(RepoConfig(slug="o/r", path="/nowhere", base="main",
                              labels=("claude",), hold_label="claude:hold",
                              reviewers=("human",)),),
            limits=Limits(**limits) if limits else Limits(),
            max_concurrent=5,
        )
        self.forge = FakeForge([ISSUE])
        self.workspace = FakeWorkspace()
        self.agent = FakeAgent()
        self.regenerator = FakeRegenerator()
        self.store = Store(self.config.state_dir)
        self.journal = Journal(None, echo=None)
        self.engine = Engine(self.config, self.forge, self.workspace, self.agent,
                             self.store, self.journal, regenerator=self.regenerator)

    def dry(self) -> "Engine":
        """The same wiring, previewing only. Same fakes, so the reads are identical."""
        return Engine(self.config, self.forge, self.workspace, self.agent,
                      self.store, self.journal, dry_run=True,
                      regenerator=self.regenerator)

    def step(self) -> str:
        """One pass. Returns the phase afterwards, which is what tests read."""
        self.engine.pass_once()
        record = self.store.load("o/r", 42)
        return record.phase.value if record else "-"

    @property
    def record(self):
        return self.store.load("o/r", 42)

    def events(self, name: str) -> list[dict]:
        return [event for event in self.journal.events if event["event"] == name]


class FullJourney(unittest.TestCase):
    def test_issue_to_merge(self) -> None:
        harness = Harness()
        forge, agent, workspace = harness.forge, harness.agent, harness.workspace

        # 1. the label is the trigger, and planning comes before any code
        self.assertEqual(harness.step(), Phase.DRAFTED.value)
        self.assertEqual(harness.record.branch, "feat/42-cache-lru",
                         "<type>/<number>-<slug>, the pack's convention")
        self.assertEqual(workspace.pushes, ["feat/42-cache-lru"])
        self.assertTrue(agent.calls[0]["read_only"], "the planning phase must be read-only")
        self.assertFalse(agent.calls[0]["resume"], "the first run creates the session, it does not resume it")
        self.assertEqual(harness.record.pr, 101)

        body = forge.bodies("pr-body")[0]
        self.assertIn("Closes #42", body)
        self.assertIn("the suite passes twice in a row", body)

        # 2. implementation, on the same conversation
        self.assertEqual(harness.step(), Phase.IMPLEMENTED.value)
        self.assertTrue(agent.calls[1]["resume"], "the implementation must resume the plan's session")
        self.assertFalse(agent.calls[1]["read_only"])
        self.assertEqual(agent.calls[1]["session_id"], agent.calls[0]["session_id"])

        # 3. the build is asked before the human is
        forge.ci_pending()
        self.assertEqual(harness.step(), Phase.AWAITING_CHECKS.value)
        self.assertEqual(harness.step(), Phase.AWAITING_CHECKS.value)
        self.assertEqual(forge.review_requests, [], "a human is not disturbed before CI")

        # 4. the build is red: the agent is handed the log, not just the name
        forge.ci_red("build")
        self.assertEqual(harness.step(), Phase.AWAITING_CHECKS.value)
        self.assertEqual(harness.record.check_fixes, 1)
        self.assertIn("error: expected 3, got 4", agent.prompts[-1])
        self.assertIn("trouver-la-cause", agent.prompts[-1])

        # 5. green, so now the human is asked - and told the build is green
        forge.ci_green()
        self.assertEqual(harness.step(), Phase.IN_REVIEW.value)
        self.assertEqual(forge.review_requests, [(101, ("human",))])
        self.assertEqual(forge.marked_ready, [101])
        self.assertIn("Continuous integration: green.", forge.bodies("pr")[-1])

        # 6. a real review: an inline comment on a line
        forge.human_says("This name does not say what the function does.",
                         kind=FeedbackKind.INLINE, path="src/cache.py", line=12)
        self.assertEqual(harness.step(), Phase.REVISED.value)
        prompt = agent.prompts[-1]
        self.assertIn("This name does not say what the function does.", prompt)
        self.assertIn("src/cache.py:12", prompt)
        self.assertEqual(harness.record.check_fixes, 0, "a human round resets the CI budget to zero")

        # one comment per round, carrying both the answers and the evidence
        answered = forge.bodies("pr")[-1]
        self.assertIn("Answers to the remarks", answered)
        self.assertIn("Renamed.", answered)
        self.assertIn("src/cache.py:12", answered)
        self.assertIn("| met | criterion | evidence |", answered)
        round_comments = [body for body in forge.bodies("pr") if "round 2" in body]
        self.assertEqual(len(round_comments), 1, "a single comment per round")

        # 7. the same comment must never buy a second round
        self.assertEqual(harness.step(), Phase.AWAITING_CHECKS.value)
        self.assertEqual(harness.step(), Phase.IN_REVIEW.value)
        rounds_before = harness.record.rounds
        self.assertEqual(harness.step(), Phase.IN_REVIEW.value)
        self.assertEqual(harness.record.rounds, rounds_before,
                         "a comment already handled does not start a round")

        # 8. approved, then merged by a human, and only then does the session close
        forge.approve("feat/42-cache-lru")
        self.assertEqual(harness.step(), Phase.IN_REVIEW.value, "approval does not merge")
        forge.merge("feat/42-cache-lru")
        self.assertEqual(harness.step(), Phase.DONE.value)
        self.assertEqual(workspace.discarded, [harness.record.worktree])
        self.assertIn("session closed", forge.bodies("issue")[-1])
        self.assertTrue(agent.calls[-1]["read_only"], "closing must not be able to modify anything")

        # 9. done means done: further passes cost nothing
        calls_before = len(agent.calls)
        harness.step()
        self.assertEqual(len(agent.calls), calls_before)


class Honesty(unittest.TestCase):
    def test_a_verdict_claiming_a_push_is_checked_against_git(self) -> None:
        harness = Harness()
        harness.workspace.synced = False        # git says nothing left the machine
        harness.step()                          # plan
        harness.workspace.pushes.clear()
        harness.step()                          # implement, claiming pushed=True

        self.assertTrue(harness.agent.work["pushed"])
        self.assertEqual(harness.events("verdict_overstated")[0]["claimed_pushed"], True)
        self.assertIn("feat/42-cache-lru", harness.workspace.pushes,
                      "the driver pushes itself rather than believe the verdict")

    def test_a_blocked_agent_stops_the_loop_and_says_so_on_the_pull_request(self) -> None:
        harness = Harness()
        harness.step()
        harness.agent.work = {"verdict": "blocked", "summary": "s",
                              "blocked_reason": "the dependency does not exist",
                              "commands_run": [], "acceptance": [], "pushed": False}
        self.assertEqual(harness.step(), Phase.BLOCKED.value)
        self.assertIn("the dependency does not exist", harness.forge.bodies("pr")[-1])

    def test_a_failed_run_blocks_instead_of_pretending(self) -> None:
        harness = Harness()
        harness.step()
        harness.agent.fail_next = True
        self.assertEqual(harness.step(), Phase.BLOCKED.value)
        self.assertIn("budget exhausted", harness.record.note)

    def test_ci_red_forever_gives_up_and_leaves_the_branch(self) -> None:
        harness = Harness(max_check_fixes=2)
        harness.step()
        harness.step()
        harness.forge.ci_red()
        for _ in range(4):
            harness.step()
        self.assertEqual(harness.record.phase, Phase.BLOCKED)
        self.assertLessEqual(harness.record.check_fixes, 2)
        self.assertIn("still red", harness.record.note)
        self.assertNotIn(harness.record.worktree, harness.workspace.discarded,
                         "a blocked branch is kept: a human is going to take it over")


class WhatTheRunDidNotSay(unittest.TestCase):
    """Two things a verdict never mentions, and both change what it is worth."""

    def test_uncommitted_files_are_reported_not_silently_destroyed(self) -> None:
        harness = Harness()
        harness.step()
        harness.workspace.dirty = True
        harness.step()
        event = harness.events("worktree_dirty")
        self.assertTrue(event, "uncommitted files must be reported")
        self.assertIn("lost", event[0]["detail"])

    def test_a_refused_tool_is_never_silent(self) -> None:
        harness = Harness()
        harness.step()

        from tests.fakes import FakeResult
        original = harness.agent.run

        def denied(**kwargs):
            result = original(**kwargs)
            return FakeResult(result.ok, result.verdict, result.cost_usd, result.detail,
                              denials=("Bash(git push)",))
        harness.agent.run = denied
        harness.step()
        self.assertEqual(harness.events("permission_denied")[0]["tools"], "Bash(git push)")


class AsksBeforeBuilding(unittest.TestCase):
    def test_open_questions_stop_before_any_branch_is_pushed(self) -> None:
        harness = Harness()
        harness.agent.plan = dict(harness.agent.plan,
                                  questions=["Cache per process or shared?"], risk="high")
        self.assertEqual(harness.step(), Phase.AWAITING_ANSWER.value)
        self.assertEqual(harness.workspace.pushes, [], "nothing is pushed before an answer")
        self.assertEqual(harness.record.pr, 0)
        asked = harness.forge.bodies("issue")[-1]
        self.assertIn("Cache per process or shared?", asked)

        # answering restarts the framing, on the same conversation
        harness.forge.human_says("Per process.", kind=FeedbackKind.ISSUE, state="")
        harness.agent.plan = dict(harness.agent.plan, questions=[])
        self.assertEqual(harness.step(), Phase.DRAFTED.value)
        self.assertTrue(harness.agent.calls[-1]["resume"])
        self.assertIn("Per process.", harness.agent.prompts[-1])


class HumanControl(unittest.TestCase):
    def test_the_hold_label_keeps_an_adopted_issue_frozen(self) -> None:
        harness = Harness()
        harness.step()
        harness.forge._issues[("o/r", 42)] = IssueRef(
            repo="o/r", number=42, title=ISSUE.title, body=ISSUE.body, url=ISSUE.url,
            labels=("claude", "claude:hold"))
        calls_before = len(harness.agent.calls)
        self.assertEqual(harness.step(), Phase.DRAFTED.value)
        self.assertEqual(len(harness.agent.calls), calls_before, "nothing runs under hold")

    def test_closing_the_issue_abandons_and_cleans_up(self) -> None:
        harness = Harness()
        harness.step()
        harness.forge.close_issue("o/r", 42)
        self.assertEqual(harness.step(), Phase.ABANDONED.value)
        self.assertEqual(harness.workspace.discarded, [harness.record.worktree])

    def test_an_unlabelled_issue_is_never_adopted(self) -> None:
        harness = Harness()
        harness.forge._issues[("o/r", 43)] = IssueRef(
            repo="o/r", number=43, title="other", body="", url="u", labels=())
        harness.engine.pass_once()
        self.assertIsNone(harness.store.load("o/r", 43))


class ChecksGrace(unittest.TestCase):
    """"No checks reported" means two opposite things, and the clock tells them apart."""

    def _at_checks_gate(self, harness: Harness):
        harness.step()                      # plan
        harness.step()                      # implement
        harness.step()                      # enter the gate
        return harness.record

    def test_an_empty_rollup_right_after_a_push_is_read_as_not_yet(self) -> None:
        harness = Harness()
        from forgeron.model import CheckState
        record = self._at_checks_gate(harness)
        harness.forge.check_state = CheckState.NONE
        harness.forge.failing = ()
        self.assertEqual(harness.step(), Phase.AWAITING_CHECKS.value)
        self.assertEqual(harness.forge.review_requests, [],
                         "an empty rollup right after a push is not an absence of CI")

    def test_the_same_empty_rollup_later_is_read_as_no_ci_at_all(self) -> None:
        harness = Harness()
        from forgeron.model import CheckState
        record = self._at_checks_gate(harness)
        harness.forge.check_state = CheckState.NONE
        harness.store.save(record.with_(checks_since="2020-01-01T00:00:00Z"))
        self.assertEqual(harness.step(), Phase.IN_REVIEW.value)
        self.assertEqual(len(harness.forge.review_requests), 1)


class DryRun(unittest.TestCase):
    """A preview must leave the world exactly as it found it, state included."""

    def test_nothing_is_adopted_and_nothing_runs(self) -> None:
        harness = Harness()
        harness.dry().pass_once()
        self.assertIsNone(harness.store.load("o/r", 42))
        self.assertEqual(harness.agent.calls, [])
        self.assertEqual(harness.forge.comments, [])
        self.assertEqual(harness.workspace.pushes, [])
        self.assertTrue(harness.events("would_adopt"))

    def test_an_issue_already_in_flight_keeps_its_phase(self) -> None:
        harness = Harness()
        harness.step()                       # real: plan, so a record exists
        before = harness.record
        calls_before = len(harness.agent.calls)
        harness.dry().pass_once()
        self.assertEqual(harness.record.phase, before.phase)
        self.assertEqual(harness.record.spent_usd, before.spent_usd)
        self.assertEqual(len(harness.agent.calls), calls_before)
        would = harness.events("would_act")[-1]
        self.assertEqual(would["action"], "implement")


class Crashes(unittest.TestCase):
    def test_a_transient_phase_is_re_entered_rather_than_lost(self) -> None:
        harness = Harness()
        harness.step()
        harness.store.save(harness.record.with_(phase=Phase.IMPLEMENTING))
        self.assertEqual(harness.step(), Phase.IMPLEMENTED.value)

    def test_a_pull_request_that_already_exists_is_not_planned_twice(self) -> None:
        harness = Harness()
        harness.step()
        harness.store.save(harness.record.with_(phase=Phase.PLANNING))
        calls_before = len(harness.agent.calls)
        self.assertEqual(harness.step(), Phase.DRAFTED.value)
        self.assertEqual(len(harness.agent.calls), calls_before,
                         "a pull request already open must short-circuit the planning")

    def test_a_lease_stops_a_second_driver(self) -> None:
        harness = Harness()
        harness.step()
        with harness.store.lease(harness.record.with_(repo="o/r")) as held:
            self.assertTrue(held)
            import os
            from forgeron.store import _write_lease
            import time
            _write_lease(harness.store.path_of(harness.record) + ".lease",
                         {"holder": "other-host:1", "expires": time.time() + 600})
            calls_before = len(harness.agent.calls)
            harness.engine.pass_once()
            self.assertEqual(len(harness.agent.calls), calls_before)
            self.assertTrue(harness.events("lease_busy"))
            os.remove(harness.store.path_of(harness.record) + ".lease")


if __name__ == "__main__":
    unittest.main()
