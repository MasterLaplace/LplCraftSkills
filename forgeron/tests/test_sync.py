"""Ce qui se passe quand la base bouge sous une branche en cours.

Le sujet est une question de politique avant d'etre une question de git : rebaser
reecrit l'historique, donc GitHub perd la base sur laquelle il calculait « ce qui a
change depuis ta derniere relecture ». Un relecteur qui a laisse dix commentaires
hier revient sur une pull request qui a oublie ce qu'il avait deja lu. Ce cout est
paye par un humain, donc il l'emporte sur la proprete de l'historique - et c'est
exactement ce que ces tests fixent.
"""

from __future__ import annotations

import unittest

from forgeron.model import CheckState, FeedbackKind, MergeState, Phase
from forgeron.states import Limits, sync_method
from tests.test_engine import Harness

BRANCH = "feat/42-cache-lru"


def at_gate(**limits) -> Harness:
    """Un harnais amene jusqu'a la porte de CI, la ou l'etat de merge commence a compter.

    Trois passes et pas deux : le pilote entre TOUJOURS dans la porte de CI en
    sortant de l'implementation, avant de regarder l'etat de merge. Une passe de
    plus, qui ne coute rien puisqu'elle ne fait qu'horodater l'attente.
    """
    harness = Harness(**limits)
    harness.step()          # plan      -> drafted
    harness.step()          # implement -> implemented
    harness.step()          # porte CI  -> awaiting_checks
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
                         "une branche en retard ne coute pas un run d'agent")
        self.assertEqual(self.harness.workspace.syncs, [],
                         "elle ne coute meme pas un checkout")
        self.assertEqual(self.harness.record.syncs, 1)

    def test_a_reviewed_branch_is_merged_and_never_rebased(self) -> None:
        self.at_review()
        self.harness.forge.mark_reviewed(BRANCH)
        self.harness.forge.merge_state_value = MergeState.BEHIND
        self.harness.step()

        self.assertEqual(self.harness.forge.updates, [(101, "MERGE")],
                         "rebaser sous les yeux d'un relecteur annule sa revue")

    def test_the_policy_is_readable_on_its_own(self) -> None:
        from forgeron.model import Observation, PullRequestView

        def observation(reviewed: bool) -> Observation:
            return Observation(issue_open=True, held=False,
                               pr=PullRequestView(1, "u", "b", False, "OPEN", "", False,
                                                  reviewed=reviewed))
        self.assertEqual(sync_method(observation(False), Limits()), "REBASE")
        self.assertEqual(sync_method(observation(True), Limits()), "MERGE")
        self.assertEqual(sync_method(observation(False), Limits(rebase_before_review=False)),
                         "MERGE", "le depot peut refuser tout rebase")

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
                            "la porte de CI a bien horodate l'attente")
        self.harness.forge.merge_state_value = MergeState.BEHIND
        self.harness.step()
        self.assertEqual(self.harness.record.checks_since, "")


class Conflicts(Harnessed):
    def setUp(self) -> None:
        super().setUp()
        self.harness.forge.merge_state_value = MergeState.DIRTY
        self.harness.workspace.conflicts_on_sync = ["src/cache.py"]

    def test_the_agent_is_given_both_intentions_not_just_the_markers(self) -> None:
        self.harness.forge.landed = ["abc1234 feat(cache): cache partage entre requetes"]
        self.harness.step()

        prompt = self.harness.agent.prompts[-1]
        self.assertIn("src/cache.py", prompt)
        self.assertIn("cache partage entre requetes", prompt,
                      "il faut savoir ce que l'AUTRE changement voulait faire")
        self.assertIn("--ours", prompt, "le piege doit etre nomme explicitement")

    def test_a_resolution_goes_back_through_ci_and_a_new_review(self) -> None:
        self.harness.forge.approve(BRANCH)          # deja approuvee !
        self.harness.step()
        self.assertEqual(self.harness.record.phase, Phase.IMPLEMENTED)

        self.harness.forge.merge_state_value = MergeState.CLEAN
        self.harness.forge.ci_green()
        self.assertEqual(self.harness.step(), Phase.AWAITING_CHECKS.value)
        self.assertEqual(self.harness.step(), Phase.IN_REVIEW.value)
        self.assertTrue(self.harness.forge.review_requests,
                        "une resolution n'a ete relue par personne, meme sur une PR approuvee")
        said = "\n".join(self.harness.forge.bodies("pr"))
        self.assertIn("n'a ete relue par personne", said)

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
                         "l'operation doit etre annulee, pas laissee a moitie faite")
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
        harness.step()                                  # tentative 1 -> implemented
        harness.forge.merge_state_value = MergeState.DIRTY
        harness.step()                                  # porte CI -> awaiting_checks
        harness.step()                                  # doit renoncer
        self.assertEqual(harness.record.phase, Phase.BLOCKED)
        self.assertIn("still conflicting", harness.record.note)

    def test_a_human_outranks_a_conflict(self) -> None:
        # They may be saying the branch is wrong, in which case resolving the
        # conflict is work spent on something about to be thrown away.
        self.harness.forge.merge_state_value = MergeState.CLEAN   # sinon on n'atteint pas la revue
        self.at_review()
        self.harness.forge.merge_state_value = MergeState.DIRTY
        self.harness.forge.human_says("En fait laisse tomber cette approche.",
                                      kind=FeedbackKind.CONVERSATION, state="")
        self.harness.step()
        self.assertIn("laisse tomber cette approche", self.harness.agent.prompts[-1])
        self.assertEqual(self.harness.workspace.syncs, [])


class Naming(unittest.TestCase):
    def test_the_branch_carries_the_issue_number_and_the_issue_carries_the_branch(self) -> None:
        harness = Harness()
        harness.step()
        # <type>/<numero>-<slug> : le numero est ce qui permet de retrouver la
        # discussion a partir du seul nom de branche.
        self.assertEqual(harness.record.branch, "feat/42-cache-lru")
        # et le lien cote GitHub, celui que le bouton "create a branch" fabrique
        self.assertEqual(harness.forge.links, [("", "feat/42-cache-lru")])
        self.assertTrue(harness.events("branch_linked"))


if __name__ == "__main__":
    unittest.main()
