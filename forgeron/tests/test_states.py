"""The decision table, asserted case by case. No forge, no agent, no clock.

Ordering is the policy here, so the tests that matter are the ones where two rules
both apply: a closed issue against a merge, a human against red CI, a ceiling
against everything.
"""

from __future__ import annotations

import unittest

from forgeron.model import (Action, CheckRun, CheckState, Feedback, FeedbackKind,
                            Observation, Phase, PullRequestView, Record)
from forgeron.states import Limits, decide, phase_after_plan

PR = PullRequestView(number=1, url="u", head="b", is_draft=False, state="OPEN",
                     review_decision="", merged=False)


def observe(**changes) -> Observation:
    base = {"issue_open": True, "held": False, "pr": PR}
    base.update(changes)
    return Observation(**base)


def feedback(body: str = "rework this", state: str = "CHANGES_REQUESTED") -> tuple[Feedback, ...]:
    return (Feedback(ident="1", kind=FeedbackKind.REVIEW, author="human", body=body,
                     created_at="t", state=state),)


RED = (CheckRun("build", "CI", CheckState.FAILURE, "u", "2"),)


class HappyPath(unittest.TestCase):
    def test_each_phase_advances(self) -> None:
        expected = {
            Phase.QUEUED: Action.PLAN,
            Phase.PLANNING: Action.PLAN,
            Phase.DRAFTED: Action.IMPLEMENT,
            Phase.IMPLEMENTING: Action.IMPLEMENT,
            Phase.IMPLEMENTED: Action.WAIT_CHECKS,
            Phase.REVISED: Action.WAIT_CHECKS,
            Phase.REVISING: Action.REVISE,
            Phase.FIXING_CHECKS: Action.FIX_CHECKS,
        }
        for phase, action in expected.items():
            with self.subTest(phase=phase):
                got = decide(Record(repo="o/r", issue=1, phase=phase), observe())
                self.assertEqual(got.action, action)

    def test_terminal_phases_do_nothing(self) -> None:
        for phase in (Phase.DONE, Phase.ABANDONED):
            with self.subTest(phase=phase):
                self.assertEqual(
                    decide(Record(repo="o/r", issue=1, phase=phase), observe()).action,
                    Action.NOTHING)


class ContinuousIntegrationGate(unittest.TestCase):
    def setUp(self) -> None:
        self.record = Record(repo="o/r", issue=1, phase=Phase.AWAITING_CHECKS)

    def test_green_asks_for_review(self) -> None:
        got = decide(self.record, observe(checks=CheckState.SUCCESS))
        self.assertEqual(got.action, Action.REQUEST_REVIEW)

    def test_no_checks_at_all_also_asks_for_review(self) -> None:
        # A repository without CI must not stall forever. The grace period that
        # separates this from "not started yet" lives in the engine, not here.
        got = decide(self.record, observe(checks=CheckState.NONE))
        self.assertEqual(got.action, Action.REQUEST_REVIEW)
        self.assertIn("no CI", got.reason)

    def test_pending_waits(self) -> None:
        got = decide(self.record, observe(checks=CheckState.PENDING, checks_waited_minutes=3))
        self.assertEqual(got.action, Action.NOTHING)
        self.assertEqual(got.phase, Phase.AWAITING_CHECKS)

    def test_pending_forever_blocks_rather_than_waiting_forever(self) -> None:
        got = decide(self.record, observe(checks=CheckState.PENDING, checks_waited_minutes=90),
                     Limits(checks_timeout_minutes=45))
        self.assertEqual(got.action, Action.BLOCK)

    def test_red_is_fixed(self) -> None:
        got = decide(self.record, observe(checks=CheckState.FAILURE, failing_checks=RED))
        self.assertEqual(got.action, Action.FIX_CHECKS)

    def test_red_gives_up_after_the_budget_of_attempts(self) -> None:
        got = decide(self.record.with_(check_fixes=3),
                     observe(checks=CheckState.FAILURE, failing_checks=RED),
                     Limits(max_check_fixes=3))
        self.assertEqual(got.action, Action.BLOCK)
        self.assertIn("still red", got.reason)

    def test_a_human_outranks_red_ci(self) -> None:
        # They may be saying the whole branch is wrong, which no amount of green
        # would fix, so their words are read before the build is.
        got = decide(self.record, observe(checks=CheckState.FAILURE, failing_checks=RED,
                                          new_feedback=feedback()))
        self.assertEqual(got.action, Action.REVISE)

    def test_ci_going_red_during_review_is_picked_up(self) -> None:
        got = decide(Record(repo="o/r", issue=1, phase=Phase.IN_REVIEW),
                     observe(checks=CheckState.FAILURE, failing_checks=RED))
        self.assertEqual(got.action, Action.FIX_CHECKS)


class Review(unittest.TestCase):
    def test_feedback_starts_a_round(self) -> None:
        got = decide(Record(repo="o/r", issue=1, phase=Phase.IN_REVIEW),
                     observe(new_feedback=feedback()))
        self.assertEqual(got.action, Action.REVISE)

    def test_approved_but_unmerged_waits_for_a_human(self) -> None:
        approved = PullRequestView(1, "u", "b", False, "OPEN", "APPROVED", False)
        got = decide(Record(repo="o/r", issue=1, phase=Phase.IN_REVIEW), observe(pr=approved))
        self.assertEqual(got.action, Action.NOTHING)
        self.assertIn("merge", got.reason)

    def test_merge_from_any_phase_wraps_up(self) -> None:
        merged = PullRequestView(1, "u", "b", False, "MERGED", "APPROVED", True)
        for phase in (Phase.IN_REVIEW, Phase.AWAITING_CHECKS, Phase.DRAFTED, Phase.BLOCKED):
            with self.subTest(phase=phase):
                got = decide(Record(repo="o/r", issue=1, phase=phase), observe(pr=merged))
                self.assertEqual(got.action, Action.WRAP_UP)


class Precedence(unittest.TestCase):
    def test_a_closed_issue_beats_everything(self) -> None:
        got = decide(Record(repo="o/r", issue=1, phase=Phase.IN_REVIEW),
                     observe(issue_open=False, new_feedback=feedback(),
                             checks=CheckState.FAILURE, failing_checks=RED))
        self.assertEqual(got.action, Action.ABANDON)

    def test_a_closed_issue_with_a_merged_pull_request_is_success_not_abandon(self) -> None:
        # GitHub closes the issue when the pull request says "closes #N", so
        # reading closed-and-merged as abandonment would fail every success.
        merged = PullRequestView(1, "u", "b", False, "MERGED", "APPROVED", True)
        got = decide(Record(repo="o/r", issue=1, phase=Phase.IN_REVIEW),
                     observe(issue_open=False, pr=merged))
        self.assertEqual(got.action, Action.WRAP_UP)

    def test_the_hold_label_stops_work_without_closing_anything(self) -> None:
        got = decide(Record(repo="o/r", issue=1, phase=Phase.IN_REVIEW),
                     observe(held=True, new_feedback=feedback()))
        self.assertEqual(got.action, Action.NOTHING)
        self.assertEqual(got.reason, "held by label")

    def test_ceilings_beat_the_hold_label_so_the_reason_is_still_reported(self) -> None:
        got = decide(Record(repo="o/r", issue=1, phase=Phase.IN_REVIEW, rounds=99),
                     observe(held=True), Limits(max_rounds=6))
        self.assertEqual(got.action, Action.BLOCK)

    def test_spend_ceiling_blocks(self) -> None:
        got = decide(Record(repo="o/r", issue=1, phase=Phase.DRAFTED, spent_usd=99.0),
                     observe(), Limits(max_spend_usd=12.0))
        self.assertEqual(got.action, Action.BLOCK)
        self.assertIn("USD", got.reason)

    def test_a_blocked_issue_only_restarts_when_a_human_speaks(self) -> None:
        blocked = Record(repo="o/r", issue=1, phase=Phase.BLOCKED)
        self.assertEqual(decide(blocked, observe()).action, Action.NOTHING)
        self.assertEqual(decide(blocked, observe(new_feedback=feedback())).action, Action.REVISE)


class Questions(unittest.TestCase):
    def test_a_plan_with_questions_does_not_become_a_branch(self) -> None:
        self.assertIs(phase_after_plan({"questions": ["which format?"]}), Phase.AWAITING_ANSWER)

    def test_a_plan_without_questions_proceeds(self) -> None:
        self.assertIs(phase_after_plan({"questions": []}), Phase.DRAFTED)

    def test_waiting_for_an_answer_replans_when_one_arrives(self) -> None:
        waiting = Record(repo="o/r", issue=1, phase=Phase.AWAITING_ANSWER)
        self.assertEqual(decide(waiting, observe()).action, Action.NOTHING)
        self.assertEqual(decide(waiting, observe(new_feedback=feedback())).action, Action.PLAN)


class Exhaustive(unittest.TestCase):
    def test_every_phase_has_a_rule(self) -> None:
        # The rule table ends in an AssertionError rather than a default, so a phase
        # added without a rule must fail loudly here instead of quietly doing nothing.
        for phase in Phase:
            with self.subTest(phase=phase):
                decide(Record(repo="o/r", issue=1, phase=phase), observe())


if __name__ == "__main__":
    unittest.main()
