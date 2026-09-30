"""What happens when the base moves under a branch in progress.

The subject is a policy question before it is a git question: rebasing
rewrites history, so GitHub loses the base it computed "what has changed
since your last review" against. A reviewer who left ten comments yesterday
comes back to a pull request that has forgotten what they had already read.
That cost is paid by a human, so it wins over the tidiness of the history -
and that is exactly what these tests pin down.
"""

from __future__ import annotations

import unittest

from forgeron.model import CheckState, FeedbackKind, MergeState, Phase
from forgeron.states import Limits, sync_method
from tests.test_engine import Harness

BRANCH = "feat/42-cache-lru"


def at_gate(**limits) -> Harness:
    """A harness brought up to the CI gate, where the merge state starts to count.

    Three passes and not two: the driver ALWAYS enters the CI gate when
    leaving the implementation, before looking at the merge state. One more
    pass, which costs nothing since it only timestamps the wait.
    """
    harness = Harness(**limits)
    harness.step()          # plan      -> drafted
    harness.step()          # implement -> implemented
    harness.step()          # CI gate   -> awaiting_checks
    return harness


class Harnessed(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = at_gate()

    def at_review(self) -> None:
        self.harness.forge.ci_green()
        self.harness.step()          # -> in_review


class BehindTheBase(Harnessed):
    def test_it_is_github_that_updates_the_branch_not_us(self) -> None:
        self.harness.forge.merge_state_value = MergeState.BEHIND
        calls_before = len(self.harness.agent.calls)
        self.harness.step()

        self.assertEqual(self.harness.forge.updates, [(101, "REBASE")])
        self.assertEqual(len(self.harness.agent.calls), calls_before,
                         "a branch that is behind does not cost an agent run")
        self.assertEqual(self.harness.workspace.syncs, [],
                         "it does not even cost a checkout")
        self.assertEqual(self.harness.record.syncs, 1)

    def test_a_reviewed_branch_is_merged_and_never_rebased(self) -> None:
        self.at_review()
        self.harness.forge.mark_reviewed(BRANCH)
        self.harness.forge.merge_state_value = MergeState.BEHIND
        self.harness.step()

        self.assertEqual(self.harness.forge.updates, [(101, "MERGE")],
                         "rebasing under a reviewer's eyes cancels their review")

    def test_the_policy_is_readable_on_its_own(self) -> None:
        from forgeron.model import Observation, PullRequestView

        def observation(reviewed: bool) -> Observation:
            return Observation(issue_open=True, held=False,
                               pr=PullRequestView(1, "u", "b", False, "OPEN", "", False,
                                                  reviewed=reviewed))
        self.assertEqual(sync_method(observation(False), Limits()), "REBASE")
        self.assertEqual(sync_method(observation(True), Limits()), "MERGE")
        self.assertEqual(sync_method(observation(False), Limits(rebase_before_review=False)),
                         "MERGE", "the repository can refuse any rebase")

    def test_a_refused_update_changes_nothing_and_waits(self) -> None:
        self.harness.forge.merge_state_value = MergeState.BEHIND
        self.harness.forge.update_succeeds = False
        before = self.harness.record.phase
        self.harness.step()

        self.assertEqual(self.harness.record.phase, before)
        self.assertEqual(self.harness.record.syncs, 0)
        self.assertTrue(self.harness.events("sync_refused"))

    def test_an_update_restarts_the_ci_wait(self) -> None:
        # A new head means CI runs again. Keeping the old stamp would let the
        # previous head's timeout expire the new one.
        self.assertNotEqual(self.harness.record.checks_since, "",
                            "the CI gate did timestamp the wait")
        self.harness.forge.merge_state_value = MergeState.BEHIND
        self.harness.step()
        self.assertEqual(self.harness.record.checks_since, "")


class Conflicts(Harnessed):
    def setUp(self) -> None:
        super().setUp()
        self.harness.forge.merge_state_value = MergeState.DIRTY
        self.harness.workspace.conflicts_on_sync = ["src/cache.py"]

    def test_the_agent_is_given_both_intentions_not_just_the_markers(self) -> None:
        self.harness.forge.landed = ["abc1234 feat(cache): cache shared between requests"]
        self.harness.step()

        prompt = self.harness.agent.prompts[-1]
        self.assertIn("src/cache.py", prompt)
        self.assertIn("cache shared between requests", prompt,
                      "one must know what the OTHER change meant to do")
        self.assertIn("--ours", prompt, "the trap must be named explicitly")

    def test_a_resolution_goes_back_through_ci_and_a_new_review(self) -> None:
        self.harness.forge.approve(BRANCH)          # already approved!
        self.harness.step()
        self.assertEqual(self.harness.record.phase, Phase.IMPLEMENTED)

        self.harness.forge.merge_state_value = MergeState.CLEAN
        self.harness.forge.ci_green()
        self.assertEqual(self.harness.step(), Phase.AWAITING_CHECKS.value)
        self.assertEqual(self.harness.step(), Phase.IN_REVIEW.value)
        self.assertTrue(self.harness.forge.review_requests,
                        "nobody has reviewed a resolution, even on an approved PR")
        said = "\n".join(self.harness.forge.bodies("pr"))
        self.assertIn("Nobody has reviewed this resolution", said)

    def test_a_rebase_force_pushes_with_a_lease_and_a_merge_does_not(self) -> None:
        self.harness.step()
        self.assertEqual(self.harness.workspace.forced_pushes, [BRANCH])

        harness = at_gate()
        harness.forge.merge_state_value = MergeState.DIRTY
        harness.forge.mark_reviewed(BRANCH)
        harness.workspace.conflicts_on_sync = ["src/cache.py"]
        harness.workspace.pushes.clear()
        harness.step()
        self.assertEqual(harness.workspace.forced_pushes, [])
        self.assertIn(BRANCH, harness.workspace.pushes)

    def test_a_claimed_resolution_is_checked_and_nothing_is_pushed_if_it_lied(self) -> None:
        # The agent says it resolved; git still reports an unmerged entry. Pushing
        # a half-finished rebase with a lease leaves a branch nobody can reason about.
        self.harness.workspace.conflicts_remaining = ["src/cache.py"]
        self.harness.workspace.pushes.clear()
        self.harness.workspace.forced_pushes.clear()

        self.assertEqual(self.harness.step(), Phase.BLOCKED.value)
        self.assertEqual(self.harness.workspace.pushes, [])
        self.assertEqual(self.harness.workspace.forced_pushes, [])
        self.assertEqual(self.harness.workspace.aborts, 1,
                         "the operation must be aborted, not left half done")
        self.assertIn("src/cache.py", self.harness.forge.bodies("pr")[-1])

    def test_git_may_succeed_where_github_said_it_could_not(self) -> None:
        # GitHub judges one merge commit; git replays commits one at a time. When
        # git wins, no agent is needed at all.
        self.harness.workspace.conflicts_on_sync = []
        calls_before = len(self.harness.agent.calls)
        self.assertEqual(self.harness.step(), Phase.IMPLEMENTED.value)
        self.assertEqual(len(self.harness.agent.calls), calls_before)
        self.assertEqual(self.harness.workspace.forced_pushes, [BRANCH])

    def test_the_budget_of_attempts_is_bounded(self) -> None:
        harness = at_gate(max_conflicts=1)
        harness.forge.merge_state_value = MergeState.DIRTY
        harness.workspace.conflicts_on_sync = ["src/cache.py"]
        harness.step()                                  # attempt 1 -> implemented
        harness.forge.merge_state_value = MergeState.DIRTY
        harness.step()                                  # CI gate -> awaiting_checks
        harness.step()                                  # must give up
        self.assertEqual(harness.record.phase, Phase.BLOCKED)
        self.assertIn("still conflicting", harness.record.note)

    def test_a_human_outranks_a_conflict(self) -> None:
        # They may be saying the branch is wrong, in which case resolving the
        # conflict is work spent on something about to be thrown away.
        self.harness.forge.merge_state_value = MergeState.CLEAN   # otherwise review is never reached
        self.at_review()
        self.harness.forge.merge_state_value = MergeState.DIRTY
        self.harness.forge.human_says("Actually, drop this approach.",
                                      kind=FeedbackKind.CONVERSATION, state="")
        self.harness.step()
        self.assertIn("drop this approach", self.harness.agent.prompts[-1])
        self.assertEqual(self.harness.workspace.syncs, [])


class Naming(unittest.TestCase):
    def test_the_branch_carries_the_issue_number_and_the_issue_carries_the_branch(self) -> None:
        harness = Harness()
        harness.step()
        # <type>/<number>-<slug>: the number is what lets one find the
        # discussion from the branch name alone.
        self.assertEqual(harness.record.branch, "feat/42-cache-lru")
        # and the link on the GitHub side, the one the "create a branch" button makes
        self.assertEqual(harness.forge.links, [("", "feat/42-cache-lru")])
        self.assertTrue(harness.events("branch_linked"))


if __name__ == "__main__":
    unittest.main()
