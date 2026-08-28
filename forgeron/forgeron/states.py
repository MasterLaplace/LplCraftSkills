"""The only module holding policy, and it performs no I/O.

`decide` is a pure function of (record, observation, limits). That is deliberate:
the loop is a reconciler, so every bug is reproducible from a recorded pair, and
the review round-trip can be exercised end to end without a forge or an agent.

Read the rules top to bottom. Order is the policy: a closed issue wins over new
feedback, a blown budget wins over a merge, and the pause label wins over both.
"""

from __future__ import annotations

import dataclasses

from .model import (Action, CheckState, Decision, MergeState, Observation, Phase,
                    Record)


@dataclasses.dataclass(frozen=True, slots=True)
class Limits:
    """Ceilings that turn an unattended loop into a bounded one.

    Without them the failure mode is not a crash: it is a bot that keeps spending
    on a task it cannot finish, which looks like progress from the outside.
    """

    max_rounds: int = 6
    max_spend_usd: float = 12.0
    auto_merge: bool = False
    checks_timeout_minutes: int = 45
    max_check_fixes: int = 3
    max_conflicts: int = 2
    rebase_before_review: bool = True


def decide(record: Record, obs: Observation, limits: Limits = Limits()) -> Decision:
    """Return the single next action for this issue.

    Never returns an action the current phase cannot recover from: transient
    phases re-enter their own action, so a killed process costs one repeated run
    and never a corrupted branch.
    """
    phase = record.phase

    if phase.is_terminal:
        return Decision(Action.NOTHING, phase, "terminal")

    # A human closing the issue is the strongest signal there is: stop, whatever
    # else the forge says. Checked before the merge rule so that "closed without
    # merging" is not read as success.
    if not obs.issue_open and not obs.merged:
        return Decision(Action.ABANDON, Phase.ABANDONED, "issue closed by a human")

    if obs.merged and phase is not Phase.MERGED:
        return Decision(Action.WRAP_UP, Phase.DONE, "pull request merged")

    if phase is Phase.MERGED:
        return Decision(Action.WRAP_UP, Phase.DONE, "merge acknowledged, wrapping up")

    if record.rounds > limits.max_rounds:
        return Decision(
            Action.BLOCK, Phase.BLOCKED,
            f"round {record.rounds} exceeds max_rounds={limits.max_rounds}",
        )

    if record.spent_usd > limits.max_spend_usd:
        return Decision(
            Action.BLOCK, Phase.BLOCKED,
            f"spent {record.spent_usd:.2f} USD exceeds max_spend_usd={limits.max_spend_usd:.2f}",
        )

    # The pause label is how a human takes the wheel without closing anything.
    # It is checked after the ceilings so a held issue still reports why it stopped.
    if obs.held:
        return Decision(Action.NOTHING, phase, "held by label")

    if phase is Phase.BLOCKED:
        # Feedback is the only thing that unblocks: a human answered.
        if obs.new_feedback:
            return Decision(Action.REVISE, Phase.REVISING, "human answered a blocked issue")
        return Decision(Action.NOTHING, phase, "blocked, waiting for a human")

    if phase is Phase.AWAITING_ANSWER:
        if obs.new_feedback:
            return Decision(Action.PLAN, Phase.PLANNING, "question answered, replanning")
        return Decision(Action.NOTHING, phase, "waiting for an answer to the questions asked")

    if phase in (Phase.QUEUED, Phase.PLANNING):
        return Decision(Action.PLAN, Phase.PLANNING, "no plan yet")

    if phase in (Phase.DRAFTED, Phase.IMPLEMENTING):
        return Decision(Action.IMPLEMENT, Phase.IMPLEMENTING, "draft pull request open, implementing")

    # Continuous integration is a reviewer too, and the cheaper one: asking a human
    # to look at a branch whose own build is red wastes the only reviewer that
    # cannot be re-run for free.
    if phase in (Phase.IMPLEMENTED, Phase.REVISED):
        return Decision(Action.WAIT_CHECKS, Phase.AWAITING_CHECKS, "work pushed, checking CI")

    if phase is Phase.REVISING:
        return Decision(Action.REVISE, Phase.REVISING, "revision interrupted, re-entering")

    if phase is Phase.RESOLVING:
        return Decision(Action.RESOLVE_CONFLICT, Phase.RESOLVING,
                        "conflict resolution interrupted, re-entering")

    if phase is Phase.FIXING_CHECKS:
        return Decision(Action.FIX_CHECKS, Phase.FIXING_CHECKS, "check fix interrupted, re-entering")

    if phase is Phase.AWAITING_CHECKS:
        # A human who spoke while CI was still running outranks CI: they may be
        # telling us the branch is wrong, which no amount of green would fix.
        if obs.new_feedback:
            return Decision(Action.REVISE, Phase.REVISING,
                            f"{len(obs.new_feedback)} item(s) of feedback while waiting for CI")
        conflict = _conflict_decision(record, obs, limits)
        if conflict is not None:
            return conflict
        if obs.checks is CheckState.FAILURE:
            if record.check_fixes >= limits.max_check_fixes:
                return Decision(
                    Action.BLOCK, Phase.BLOCKED,
                    f"CI still red after {record.check_fixes} fix attempt(s)",
                )
            return Decision(Action.FIX_CHECKS, Phase.FIXING_CHECKS,
                            f"{len(obs.failing_checks)} failing check(s)")
        if obs.checks is CheckState.PENDING:
            if obs.checks_waited_minutes > limits.checks_timeout_minutes:
                return Decision(
                    Action.BLOCK, Phase.BLOCKED,
                    f"CI still pending after {obs.checks_waited_minutes:.0f} min "
                    f"(timeout {limits.checks_timeout_minutes} min)",
                )
            return Decision(Action.NOTHING, phase,
                            f"waiting for CI ({obs.checks_waited_minutes:.1f} min)")
        if obs.merge_state.needs_sync:
            return Decision(Action.SYNC_BRANCH, Phase.AWAITING_CHECKS,
                            "branch is behind its base, updating before asking for review")
        return Decision(Action.REQUEST_REVIEW, Phase.IN_REVIEW,
                        "CI green" if obs.checks is CheckState.SUCCESS else "no CI on this repository")

    if phase is Phase.IN_REVIEW:
        if obs.new_feedback:
            return Decision(Action.REVISE, Phase.REVISING, f"{len(obs.new_feedback)} new item(s) of feedback")
        # Someone merged something else while this sat in review. Handled here rather
        # than left to merge time, because a reviewer reading a stale branch is
        # reviewing code that will never exist in that shape.
        conflict = _conflict_decision(record, obs, limits)
        if conflict is not None:
            return conflict
        if obs.merge_state.needs_sync:
            return Decision(Action.SYNC_BRANCH, Phase.IN_REVIEW,
                            "base moved while in review, updating the branch")
        # CI can turn red after review was requested: a merge into the base, a
        # flaky job re-run, a scheduled workflow. Silence there would leave a human
        # reviewing a branch that no longer builds.
        if obs.checks is CheckState.FAILURE and record.check_fixes < limits.max_check_fixes:
            return Decision(Action.FIX_CHECKS, Phase.FIXING_CHECKS, "CI went red during review")
        if obs.approved:
            if limits.auto_merge:
                return Decision(Action.NOTHING, phase, "approved, auto-merge left to the forge")
            return Decision(Action.NOTHING, phase, "approved, waiting for a human to merge")
        return Decision(Action.NOTHING, phase, "waiting for review")

    raise AssertionError(f"no rule for phase {phase!r}")  # unreachable by construction


def _conflict_decision(record: Record, obs: Observation, limits: Limits) -> Decision | None:
    """A conflict, or nothing. Returned as a value so both phases ask the same question.

    Two copies of "is this branch conflicted" would eventually disagree about the
    budget, and the branch that got an extra attempt would be the one nobody was
    watching.
    """
    if not obs.merge_state.has_conflict:
        return None
    if record.conflicts >= limits.max_conflicts:
        return Decision(
            Action.BLOCK, Phase.BLOCKED,
            f"still conflicting after {record.conflicts} resolution(s)",
        )
    return Decision(Action.RESOLVE_CONFLICT, Phase.RESOLVING,
                    "branch conflicts with its base")


def sync_method(obs: Observation, limits: Limits) -> str:
    """REBASE or MERGE, and the review decides - not a preference.

    A rebase rewrites history, so GitHub loses the base it computed "changes since
    your last review" against: a reviewer who left ten comments yesterday comes back
    to a pull request that has forgotten what they already read. That cost is real
    and it is paid by a human, so it wins over tidiness.

    Before anyone has reviewed there is nothing to lose, and a rebase keeps the
    history linear. So: rebase while it is still ours, merge once it is theirs.
    """
    if not limits.rebase_before_review:
        return "MERGE"
    already_reviewed = obs.pr is not None and obs.pr.reviewed
    return "MERGE" if already_reviewed else "REBASE"


def phase_after_plan(plan: dict) -> Phase:
    """A plan with open questions is not a plan: it is a question.

    Building against an unanswered ambiguity is the expensive failure, so the
    loop stops and asks instead of guessing.
    """
    questions = plan.get("questions") or []
    return Phase.AWAITING_ANSWER if questions else Phase.DRAFTED
