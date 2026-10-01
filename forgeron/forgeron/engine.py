"""The driver: observe, decide, act, persist. One issue at a time, one action per pass.

It is a reconciler, not a script. Nothing here remembers what happened last pass;
the record on disk and the forge are the whole truth, so a driver that is killed
at any point resumes by looking rather than by replaying. That is also what makes
the same code runnable as a long-lived daemon, as a one-shot `--once`, or as one
pod per issue.
"""

from __future__ import annotations

import datetime
import subprocess
import uuid

from . import attribution, prompts
from .board import option_for
from .config import Config, RepoConfig
from .journal import Journal
from .model import (Action, CheckState, Decision, Feedback, IssueRef, MergeState,
                    Observation, Phase, PullRequestView, Record, Visual)
from .states import Limits, decide, phase_after_plan, sync_method
from .store import Store


class Engine:
    def __init__(
        self,
        config: Config,
        forge,
        workspace,
        agent,
        store: Store,
        journal: Journal,
        dry_run: bool = False,
        regenerator=None,
        board=None,
    ) -> None:
        self._config = config
        self._forge = forge
        self._workspace = workspace
        self._agent = agent
        self._store = store
        self._journal = journal
        self._dry_run = dry_run
        self._regenerator = regenerator
        self._board = board
        self._shown: dict[tuple[str, int], str] = {}
        self._owed: set[tuple[str, int]] = set()

    # -- one pass -----------------------------------------------------------

    def pass_once(self) -> list[Decision]:
        """Discover, then advance every record at most one step. Returns what it did."""
        for repo in self._config.repos:
            self._discover(repo)

        taken: list[Decision] = []
        acted = 0
        for record in self._store.all():
            if record.phase.is_terminal:
                if (record.repo, record.issue) in self._owed:
                    self._show(record)
                continue
            if acted >= self._config.max_concurrent:
                self._journal.debug("concurrency_hold", key=record.key)
                break
            with self._store.lease(record) as held:
                if not held:
                    self._journal.emit("lease_busy", key=record.key)
                    continue
                decision = self._advance(record)
            taken.append(decision)
            if decision.action is not Action.NOTHING:
                acted += 1
        return taken

    def _discover(self, repo: RepoConfig) -> None:
        for issue in self._forge.list_issues(repo.slug, repo.labels):
            if repo.hold_label in issue.labels:
                continue
            if self._store.load(repo.slug, issue.number) is not None:
                continue
            if self._dry_run:
                self._journal.emit("would_adopt", key=f"{repo.slug}#{issue.number}",
                                   title=issue.title)
                continue
            record = Record(
                repo=repo.slug,
                issue=issue.number,
                phase=Phase.QUEUED,
                session_id=str(uuid.uuid4()),
                branch=f"forgeron/issue-{issue.number}",
                worktree=f"{self._config.worktree_dir}/{repo.slug.replace('/', '__')}/issue-{issue.number}",
            )
            self._save(record)
            self._journal.emit("adopted", key=record.key, title=issue.title,
                               session=record.session_id)

    def _advance(self, record: Record) -> Decision:
        repo = self._config.repo(record.repo)
        observation = self.observe(record, repo)
        decision = decide(record, observation, self._config.limits)
        self._journal.emit("decided", key=record.key, phase=record.phase.value,
                           action=decision.action.value, reason=decision.reason)
        if decision.action is Action.NOTHING:
            self._show(record)
            return decision

        if self._dry_run:
            self._journal.emit("would_act", key=record.key, action=decision.action.value,
                               from_phase=record.phase.value, to_phase=decision.phase.value)
            return decision

        handler = getattr(self, f"_do_{decision.action.value}")
        try:
            record = handler(record, repo, observation, decision)
        except Exception as failure:  # a failed action must not lose the record
            record = record.with_(phase=Phase.BLOCKED, note=f"{type(failure).__name__}: {failure}")
            self._save(record)
            self._journal.emit("action_failed", key=record.key,
                               action=decision.action.value, error=str(failure)[:300])
            return Decision(Action.BLOCK, Phase.BLOCKED, str(failure)[:200])
        self._save(record)
        self._journal.emit("advanced", key=record.key, phase=record.phase.value,
                           spent=round(record.spent_usd, 4))
        return decision

    def _save(self, record: Record) -> None:
        self._store.save(record)
        self._show(record)

    def _show(self, record: Record) -> None:
        if self._board is None or self._dry_run:
            return
        option = option_for(record.phase)
        shown = self._shown.get((record.repo, record.issue)) == option
        if not shown:
            shown = self._reflect(record, record.issue, option)
        in_review = option == option_for(Phase.IN_REVIEW)
        if record.pr and in_review and (record.repo, record.pr) not in self._shown:
            shown = self._reflect(record, record.pr, "") and shown
        if shown:
            self._owed.discard((record.repo, record.issue))
        else:
            self._owed.add((record.repo, record.issue))

    def _reflect(self, record: Record, number: int, option: str) -> bool:
        try:
            item = self._board.place(record.repo, number)
            if option:
                self._board.set_option(item, option)
        except Exception as failure:
            self._journal.emit("board_failed", key=record.key, number=number, option=option,
                               error=str(failure)[:300])
            return False
        self._shown[(record.repo, number)] = option
        self._journal.emit("board_set", key=record.key, number=number, option=option)
        return True

    # -- observation --------------------------------------------------------

    def observe(self, record: Record, repo: RepoConfig) -> Observation:
        """Ask the forge everything, filter feedback down to what is new.

        Kept separate from `decide` so a decision is reproducible from a recorded
        observation: any misbehaviour becomes a fixture instead of an argument.
        """
        issue = self._forge.get_issue(record.repo, record.issue)
        pull: PullRequestView | None = None
        if record.branch:
            pull = self._forge.find_pull_request(record.repo, record.branch)

        seen = set(record.seen_feedback)
        fresh: tuple[Feedback, ...] = ()
        if record.phase not in (Phase.QUEUED, Phase.PLANNING):
            everything = self._forge.collect_feedback(
                record.repo, pull.number if pull else 0, record.issue
            )
            fresh = tuple(item for item in everything if item.ident not in seen)

        checks, failing = self._observe_checks(record, pull)
        return Observation(
            issue_open=issue.state.upper() == "OPEN",
            held=repo.hold_label in issue.labels,
            pr=pull,
            new_feedback=fresh,
            checks=checks,
            failing_checks=failing,
            checks_waited_minutes=_minutes_since(record.checks_since),
            merge_state=self._observe_merge_state(record, pull),
        )

    def _observe_merge_state(self, record: Record, pull: PullRequestView | None) -> MergeState:
        """Whether the branch still merges, asked ONCE per pass.

        GitHub computes mergeability lazily and answers UNKNOWN until it has, and
        the obvious fix - retry in a loop with a sleep - is the wrong one here: this
        driver already comes back every interval, so the POLL IS THE RETRY. Sleeping
        inside a pass would pay for a wait the loop performs for free, on every
        tracked issue, forever.
        """
        if pull is None or pull.merged:
            return MergeState.UNKNOWN
        if record.phase not in (Phase.AWAITING_CHECKS, Phase.IN_REVIEW,
                                Phase.RESOLVING, Phase.IMPLEMENTED, Phase.REVISED):
            return MergeState.UNKNOWN
        return self._forge.merge_state(record.repo, pull.number, attempts=1)

    def _observe_checks(self, record: Record, pull: PullRequestView | None):
        """Ask CI, and turn "nothing reported" into the right one of two answers.

        An empty rollup right after a push is GitHub not having created the check
        runs yet; the same empty rollup ten minutes later is a repository with no
        CI. Reading the first as the second asks a human to review a branch whose
        build has not started - which is the failure this grace period exists for,
        and it is a clock question, so it cannot live in the forge adapter.
        """
        if pull is None or record.phase in (Phase.QUEUED, Phase.PLANNING, Phase.DRAFTED):
            return CheckState.NONE, ()

        checks, failing = self._forge.checks(record.repo, pull.number)
        if checks is CheckState.NONE and record.checks_since:
            waited = _minutes_since(record.checks_since) * 60.0
            if waited < self._config.checks_grace_seconds:
                self._journal.debug("checks_grace", key=record.key, waited_s=round(waited))
                return CheckState.PENDING, ()
        return checks, failing

    # -- actions ------------------------------------------------------------

    def _do_plan(self, record: Record, repo: RepoConfig, obs: Observation,
                 decision: Decision) -> Record:
        issue = self._forge.get_issue(record.repo, record.issue)

        # Idempotency probe: a crash between "pushed" and "pull request created"
        # must not buy a second planning run.
        if obs.pr is not None:
            self._journal.emit("plan_skipped", key=record.key, pr=obs.pr.number)
            return record.with_(phase=Phase.DRAFTED, pr=obs.pr.number)

        self._workspace.prepare(repo.path, record.worktree, record.branch, repo.base)
        record = record.with_(phase=Phase.PLANNING)
        self._save(record)

        answers = obs.new_feedback
        result = self._agent.run(
            cwd=record.worktree,
            session_id=record.session_id,
            prompt=prompts.plan_prompt(issue, answers),
            schema=prompts.PLAN_SCHEMA,
            resume=self._resume(record),
            read_only=True,
            contract=prompts.contract(record, repo.base),
        )
        record = record.with_(spent_usd=record.spent_usd + result.cost_usd,
                              seen_feedback=record.seen_feedback + tuple(f.ident for f in answers))
        if not result.ok:
            self._forge.comment_on_issue(record.repo, record.issue, _failure_note("planning", result))
            return record.with_(phase=Phase.BLOCKED, note=f"plan: {result.detail}")

        plan = result.verdict
        record = record.with_(plan=plan)

        if phase_after_plan(plan) is Phase.AWAITING_ANSWER:
            self._forge.comment_on_issue(record.repo, record.issue, _questions_note(plan))
            self._journal.emit("asked_human", key=record.key, questions=len(plan["questions"]))
            return record.with_(phase=Phase.AWAITING_ANSWER,
                                note="questions asked, waiting for an answer")

        # <type>/<number>-<slug>, exactly what tracer-le-travail prescribes. The
        # number is not decoration: it is what lets anyone holding a branch name
        # find the discussion that justifies it, without searching.
        branch = f"{plan.get('kind', repo.branch_prefix)}/{record.issue}-{plan['branch_slug']}"
        if branch != record.branch:
            self._workspace.rename_branch(record.worktree, branch)
            record = record.with_(branch=branch)

        # An empty commit is what lets the draft pull request exist before the
        # first line of code: the human sees the plan, and can stop it, while the
        # implementation phase is still running.
        if not self._workspace.has_commits_ahead(record.worktree, repo.base):
            self._workspace.commit_empty(
                record.worktree,
                f"chore({plan['branch_slug']}): bootstrap for #{record.issue}",
            )
        self._workspace.push(record.worktree, branch)
        pull = self._forge.create_draft_pull_request(
            record.repo, branch, repo.base, plan["pr_title"],
            _pr_body(plan, record, self._config),
        )
        self._link_branch(record, issue, branch)
        self._journal.emit("drafted", key=record.key, pr=pull.number, branch=branch)
        return record.with_(phase=Phase.DRAFTED, pr=pull.number)

    def _link_branch(self, record: Record, issue: IssueRef, branch: str) -> None:
        """Fill the issue's "Development" section, the way GitHub's own button does.

        The web button creates that link AND imposes its own name
        (`42-title-of-the-issue`). The mutation behind it takes a name, so the link
        and the convention stop being an either/or: the branch is named the way the
        pack prescribes, and the issue still shows it.

        Never fatal: a missing link costs a click, and refusing to work over it
        would trade a real pull request for a convenience.
        """
        if not self._config.link_branch_to_issue:
            return
        try:
            linked = self._forge.link_branch_to_issue(
                record.repo, issue.node_id, self._forge.repo_node_id(record.repo), branch)
        except Exception as failure:
            self._journal.emit("link_failed", key=record.key, error=str(failure)[:150])
            return
        self._journal.emit("branch_linked" if linked else "link_refused",
                           key=record.key, branch=branch)

    def _do_implement(self, record: Record, repo: RepoConfig, obs: Observation,
                      decision: Decision) -> Record:
        issue = self._forge.get_issue(record.repo, record.issue)
        self._workspace.prepare(repo.path, record.worktree, record.branch, repo.base)
        record = record.with_(phase=Phase.IMPLEMENTING)
        self._save(record)

        pr_url = obs.pr.url if obs.pr else ""
        result = self._agent.run(
            cwd=record.worktree,
            session_id=record.session_id,
            prompt=prompts.implement_prompt(issue, record.plan, pr_url),
            schema=prompts.WORK_SCHEMA,
            resume=self._resume(record),
            read_only=False,
            contract=prompts.contract(record, repo.base),
        )
        record = record.with_(spent_usd=record.spent_usd + result.cost_usd,
                              last_verdict=result.verdict, rounds=record.rounds + 1,
                              checks_since="")
        return self._settle_work(record, repo, result, phase_ok=Phase.IMPLEMENTED)

    def _do_revise(self, record: Record, repo: RepoConfig, obs: Observation,
                   decision: Decision) -> Record:
        issue = self._forge.get_issue(record.repo, record.issue)
        self._workspace.prepare(repo.path, record.worktree, record.branch, repo.base)

        feedback = obs.new_feedback
        # Marked seen BEFORE the run: a crash mid-revision must not buy the same
        # round twice. The cost is that a lost round is silent to us but visible
        # to the human, whose comment simply got no answer - the cheaper failure.
        # A human round resets the CI-fix budget: the branch is about to change for
        # a different reason, so the three attempts spent on the previous head say
        # nothing about the next one.
        record = record.with_(
            phase=Phase.REVISING,
            rounds=record.rounds + 1,
            check_fixes=0,
            checks_since="",
            seen_feedback=record.seen_feedback + tuple(item.ident for item in feedback),
        )
        self._save(record)

        result = self._agent.run(
            cwd=record.worktree,
            session_id=record.session_id,
            prompt=prompts.revise_prompt(issue, feedback, record.rounds),
            schema=prompts.WORK_SCHEMA,
            resume=self._resume(record),
            read_only=False,
            contract=prompts.contract(record, repo.base),
        )
        record = record.with_(spent_usd=record.spent_usd + result.cost_usd,
                              last_verdict=result.verdict)
        # One comment per round, not two. The answers and the evidence are the same
        # act of reporting, and splitting them doubles the notifications a reviewer
        # gets while making them read half the story twice.
        return self._settle_work(record, repo, result, phase_ok=Phase.REVISED,
                                 answered=feedback)

    def _do_wait_checks(self, record: Record, repo: RepoConfig, obs: Observation,
                        decision: Decision) -> Record:
        """Enter the CI gate. Stamps when the wait started; that stamp IS the timeout.

        A separate action rather than a phase set in passing, so the journal shows
        the moment the branch stopped being our problem and started being CI's.
        """
        stamp = record.checks_since or _now_iso()
        self._journal.emit("checks_gate", key=record.key, since=stamp,
                           state=obs.checks.value,
                           head=obs.pr.head_sha if obs.pr else "-")
        return record.with_(phase=Phase.AWAITING_CHECKS, checks_since=stamp,
                            note="waiting for continuous integration")

    def _do_fix_checks(self, record: Record, repo: RepoConfig, obs: Observation,
                       decision: Decision) -> Record:
        issue = self._forge.get_issue(record.repo, record.issue)
        self._workspace.prepare(repo.path, record.worktree, record.branch, repo.base)

        failing = obs.failing_checks
        logs = self._forge.failing_logs(record.repo, failing, self._config.checks_log_bytes)
        attempt = record.check_fixes + 1
        record = record.with_(phase=Phase.FIXING_CHECKS, check_fixes=attempt)
        self._save(record)
        self._journal.emit("checks_red", key=record.key, attempt=attempt,
                           jobs=",".join(run.name for run in failing),
                           log_bytes=len(logs))

        result = self._agent.run(
            cwd=record.worktree,
            session_id=record.session_id,
            prompt=prompts.fix_checks_prompt(issue, failing, logs, attempt,
                                             self._config.limits.max_check_fixes),
            schema=prompts.WORK_SCHEMA,
            resume=self._resume(record),
            read_only=False,
            contract=prompts.contract(record, repo.base),
        )
        record = record.with_(spent_usd=record.spent_usd + result.cost_usd,
                              last_verdict=result.verdict)
        settled = self._settle_work(record, repo, result, phase_ok=Phase.AWAITING_CHECKS)
        if settled.phase is Phase.AWAITING_CHECKS:
            # A new head commit means a new wait: keeping the old stamp would let
            # the timeout of the previous attempt expire the new one.
            settled = settled.with_(checks_since=_now_iso())
        return settled

    def _do_sync_branch(self, record: Record, repo: RepoConfig, obs: Observation,
                        decision: Decision) -> Record:
        """Bring the branch up to date WITHOUT a checkout and without the agent.

        GitHub rebases or merges server-side, so the no-conflict case - which is
        almost every case - costs one API call and zero tokens. The branch does not
        even have to exist on this machine.
        """
        if obs.pr is None:
            return record.with_(phase=Phase.BLOCKED, note="nothing to update")

        method = sync_method(obs, self._config.limits)
        updated = self._forge.update_branch(record.repo, obs.pr, method)
        self._journal.emit("branch_synced" if updated else "sync_refused",
                           key=record.key, method=method, pr=obs.pr.number,
                           reviewed=obs.pr.reviewed)
        if not updated:
            # Either a conflict appeared between the observation and the call, or
            # the head moved and the lease refused. Both are answered by looking
            # again next pass rather than by forcing anything.
            return record.with_(note="update refused, observing again on the next pass")

        # A new head means CI has to run again, so the wait restarts. Forgetting this
        # would let the previous head's timeout expire the new one.
        return record.with_(phase=decision.phase, syncs=record.syncs + 1,
                            checks_since="", note=f"branch updated by {method.lower()}")

    def _do_resolve_conflict(self, record: Record, repo: RepoConfig, obs: Observation,
                             decision: Decision) -> Record:
        issue = self._forge.get_issue(record.repo, record.issue)
        self._workspace.prepare(repo.path, record.worktree, record.branch, repo.base)
        method = sync_method(obs, self._config.limits)

        attempt = record.conflicts + 1
        record = record.with_(phase=Phase.RESOLVING, conflicts=attempt,
                              rounds=record.rounds + 1)
        self._save(record)

        clean, conflicted = self._workspace.sync_with_base(record.worktree, repo.base, method)
        self._journal.emit("conflict", key=record.key, method=method, attempt=attempt,
                           files=",".join(conflicted) or "-", clean=clean)

        if clean:
            # git managed what GitHub said it could not. Happens: GitHub judges a
            # merge commit, git replays commits one at a time. No agent needed.
            self._push_after_sync(record, method)
            return record.with_(phase=Phase.IMPLEMENTED, checks_since="",
                                note=f"updated by {method.lower()}, no real conflict")

        landed = tuple(self._forge.base_commits_since(
            record.repo, repo.base, obs.pr.head_sha if obs.pr else ""))
        result = self._agent.run(
            cwd=record.worktree,
            session_id=record.session_id,
            prompt=prompts.resolve_conflict_prompt(
                issue, repo.base, method, tuple(conflicted), landed,
                attempt, self._config.limits.max_conflicts),
            schema=prompts.WORK_SCHEMA,
            resume=self._resume(record),
            read_only=False,
            contract=prompts.contract(record, repo.base, prompts.CONFLICT_EXCEPTION),
        )
        record = record.with_(spent_usd=record.spent_usd + result.cost_usd,
                              last_verdict=result.verdict)

        # "I resolved it" is a claim; an empty unmerged index is the fact. Checked
        # before anything is pushed, because a half-finished rebase pushed with a
        # lease is a branch nobody can reason about afterwards.
        remaining = self._workspace.conflicted(record.worktree)
        if remaining or not result.ok or result.verdict.get("verdict") == "blocked":
            self._workspace.abort_sync(record.worktree)
            reason = (f"unresolved conflicts: {', '.join(remaining)}" if remaining
                      else result.verdict.get("blocked_reason") or result.detail)
            if record.pr:
                self._forge.comment_on_pull_request(record.repo, record.pr, "\n".join([
                    f"**forgeron could not resolve the conflict with `{repo.base}`.**",
                    "", reason, "",
                    "The operation was aborted: the branch is as it was before the "
                    "attempt, nothing was pushed. A comment starts a new round.",
                ]))
            return record.with_(phase=Phase.BLOCKED, note=f"conflict: {reason[:200]}")

        self._push_after_sync(record, method)
        if record.pr:
            self._forge.comment_on_pull_request(record.repo, record.pr, "\n".join([
                f"### forgeron · conflict with `{repo.base}` resolved ({method.lower()})",
                "",
                attribution.strip(result.verdict.get("summary", "")).strip(),
                "",
                "⚠ **Nobody has reviewed this resolution.** Merging two changes "
                "can produce something that compiles and is wrong, so review is "
                "requested again even if the pull request was already approved.",
            ]))
        # Back to the CI gate, and therefore back through a review request. A merge
        # of two changes is new code, and it has never been read by anyone.
        return record.with_(phase=Phase.IMPLEMENTED, checks_since="",
                            note=f"conflict resolved by {method.lower()}")

    def _push_after_sync(self, record: Record, method: str) -> None:
        """A rebase rewrote the branch, so the push has to overwrite. A merge did not."""
        if method.upper() == "REBASE":
            self._workspace.push_forced(record.worktree, record.branch)
        else:
            self._workspace.push(record.worktree, record.branch)

    def _do_request_review(self, record: Record, repo: RepoConfig, obs: Observation,
                           decision: Decision) -> Record:
        if obs.pr is None:
            return record.with_(phase=Phase.BLOCKED, note="no pull request to submit")
        if obs.pr.is_draft:
            self._forge.mark_ready(record.repo, obs.pr.number)
        self._forge.request_review(record.repo, obs.pr.number, repo.reviewers)
        self._forge.comment_on_pull_request(record.repo, obs.pr.number, "\n".join([
            "**Ready for review.**",
            "",
            {
                CheckState.SUCCESS: "Continuous integration: green.",
                CheckState.NONE: "Continuous integration: no check on this repository, "
                                 "so nothing was verified automatically.",
            }.get(obs.checks, f"Continuous integration: {obs.checks.value}."),
            "",
            f"Work rounds: {record.rounds} · CI fixes: {record.check_fixes} · "
            f"spent: {record.spent_usd:.2f} USD.",
            "",
            "Review as usual. Every comment, *request changes* or reply starts a round; "
            "an approval leaves the merge to a human.",
        ]))
        self._notify(f"review requested: {record.repo}#{record.issue}", obs.pr.url)
        self._journal.emit("review_requested", key=record.key, pr=obs.pr.number,
                           reviewers=",".join(repo.reviewers) or "-")
        return record.with_(phase=Phase.IN_REVIEW, note="")

    def _do_wrap_up(self, record: Record, repo: RepoConfig, obs: Observation,
                    decision: Decision) -> Record:
        issue = self._forge.get_issue(record.repo, record.issue)
        result = self._agent.run(
            cwd=record.worktree,
            session_id=record.session_id,
            prompt=prompts.wrap_prompt(issue, record.pr),
            schema=prompts.WRAP_SCHEMA,
            resume=self._resume(record),
            read_only=True,
            contract=prompts.contract(record, repo.base),
        )
        record = record.with_(spent_usd=record.spent_usd + result.cost_usd)
        if result.ok:
            self._forge.comment_on_issue(record.repo, record.issue,
                                         _wrap_note(result.verdict, record))
        self._workspace.discard(record.worktree, repo.path)
        self._notify(f"merged: {record.repo}#{record.issue}",
                     obs.pr.url if obs.pr else "")
        self._journal.emit("closed", key=record.key, rounds=record.rounds,
                           spent=round(record.spent_usd, 4))
        return record.with_(phase=Phase.DONE, note="merged and closed")

    def _do_block(self, record: Record, repo: RepoConfig, obs: Observation,
                  decision: Decision) -> Record:
        target = record.pr or record.issue
        note = "\n".join([
            "**forgeron stops and hands back control.**",
            "",
            f"Reason: {decision.reason}",
            f"Rounds done: {record.rounds} · spent: {record.spent_usd:.2f} USD",
            "",
            f"The branch `{record.branch}` stays in place, as it is. Removing the label "
            f"`{repo.hold_label}` and commenting starts the next round.",
        ])
        if record.pr:
            self._forge.comment_on_pull_request(record.repo, record.pr, note)
        else:
            self._forge.comment_on_issue(record.repo, record.issue, note)
        self._notify(f"blocked: {record.repo}#{record.issue}", decision.reason)
        return record.with_(phase=Phase.BLOCKED, note=decision.reason)

    def _do_abandon(self, record: Record, repo: RepoConfig, obs: Observation,
                    decision: Decision) -> Record:
        self._workspace.discard(record.worktree, repo.path)
        self._journal.emit("abandoned", key=record.key, reason=decision.reason)
        return record.with_(phase=Phase.ABANDONED, note=decision.reason)

    # -- shared tails -------------------------------------------------------

    def _settle_work(self, record: Record, repo: RepoConfig, result,
                     phase_ok: Phase, answered: tuple[Feedback, ...] = ()) -> Record:
        """Turn one work run into a phase, checking the verdict against git.

        `pushed` is the agent's word for it; `is_synced` is the fact. When they
        disagree the driver pushes and says so, because a branch that never left
        the machine looks finished from inside the prompt.
        """
        if not result.ok:
            if record.pr:
                self._forge.comment_on_pull_request(record.repo, record.pr,
                                                    _failure_note("work", result))
            return record.with_(phase=Phase.BLOCKED, note=f"run: {result.detail}")

        if getattr(result, "denials", ()):
            # A refused tool means the run worked around a wall instead of doing what
            # it was asked. Never silent: it is the likeliest reason a verdict is
            # confident and wrong.
            self._journal.emit("permission_denied", key=record.key,
                               tools=",".join(result.denials))

        verdict = result.verdict
        if verdict.get("verdict") == "blocked":
            reason = verdict.get("blocked_reason") or verdict.get("summary", "")
            if record.pr:
                self._forge.comment_on_pull_request(
                    record.repo, record.pr,
                    f"**forgeron is blocked.**\n\n{reason}\n\n"
                    f"A comment from you starts the next round.",
                )
            return record.with_(phase=Phase.BLOCKED, note=f"agent blocked: {reason[:200]}")

        # Uncommitted files are about to be destroyed with the worktree, and the
        # agent is the only one who knew they mattered. Reported rather than
        # committed for it: guessing a commit message for work we did not do would
        # put something in the history nobody can review.
        if self._workspace.is_dirty(record.worktree):
            self._journal.emit("worktree_dirty", key=record.key,
                               detail="uncommitted files will be lost at cleanup")

        tainted = self._attributed_commits(record, repo)
        if tainted:
            if record.pr:
                self._forge.comment_on_pull_request(record.repo, record.pr, _tainted_note(tainted))
            return record.with_(phase=Phase.BLOCKED,
                                note=f"AI attribution in {len(tainted)} commit(s)")

        if not self._workspace.is_synced(record.worktree, record.branch):
            self._journal.emit("verdict_overstated", key=record.key,
                               claimed_pushed=bool(verdict.get("pushed")))
            self._workspace.push(record.worktree, record.branch)

        self._journal.emit("head", key=record.key, sha=self._workspace.head(record.worktree),
                           branch=record.branch)

        accepted, refused = self._verify_visuals(record, verdict)
        if record.pr:
            self._forge.comment_on_pull_request(
                record.repo, record.pr,
                _work_note(verdict, record, answered, accepted, refused),
                attachments=tuple((visual.path, visual.caption) for visual in accepted),
                cwd=record.worktree,
            )
        return record.with_(phase=phase_ok, note="")

    def _verify_visuals(self, record: Record, verdict: dict):
        """Keep only the visuals whose command really reproduces the file.

        The refusal is REPORTED, not silent: an agent that produced an image
        and sees it set aside must be able to read why, and a reviewer must
        know that something is missing rather than believe there was
        nothing to show.
        """
        declared = verdict.get("visuals") or []
        if not declared:
            return (), ()
        if self._regenerator is None:
            return (), (("(all)", "no regeneration verifier is wired"),)
        if not self._forge.supports_attachments():
            return (), (("(all)", "gh is too old for --attach, 2.99.0 is required"),)

        accepted: list[Visual] = []
        refused: list[tuple[str, str]] = []
        for entry in declared[:MAX_VISUALS]:
            visual = Visual(path=entry.get("path", ""), caption=entry.get("caption", ""),
                            command=entry.get("command", ""))
            outcome = self._regenerator.reproduce(record.worktree, visual.path, visual.command)
            self._journal.emit("visual_checked", key=record.key, path=visual.path,
                               ok=outcome.ok, reason=outcome.reason)
            if outcome.ok:
                accepted.append(visual)
            else:
                refused.append((visual.path, outcome.reason))

        for entry in declared[MAX_VISUALS:]:
            refused.append((entry.get("path", "?"), f"beyond the ceiling of {MAX_VISUALS}"))
        return tuple(accepted), tuple(refused)

    def _attributed_commits(self, record: Record, repo: RepoConfig):
        """The branch's commits that carry an AI attribution.

        A third layer behind the setting and the hook, and it exists because
        the first two each have a hole: `git commit --no-verify` skips the
        hook, and a fresh container has none. This one prevents nothing and
        cannot be bypassed by anything, since it looks at the result.
        """
        tainted = []
        for sha, message in self._workspace.commit_messages(record.worktree, repo.base):
            lines = attribution.offending_lines(message)
            if lines:
                tainted.append((sha, lines[0]))
                self._journal.emit("attribution_found", key=record.key, commit=sha,
                                   line=lines[0][:80])
        return tuple(tainted)

    def _resume(self, record: Record) -> bool:
        """Resume the conversation, or restate the context from scratch.

        "rebuild" exists because a claude session is stored under a slug of its
        working directory: a pod that recreates the worktree at a different path
        cannot resume, so the cluster answer is to carry no conversation at all
        and pay in tokens what a shared volume would cost in coupling.
        """
        if self._config.continuity == "rebuild":
            return False
        return record.phase not in (Phase.QUEUED,) and record.rounds + bool(record.plan) > 0

    def _notify(self, title: str, url: str) -> None:
        command = self._config.notify_command
        if not command:
            return
        try:
            subprocess.run(command.format(title=title, url=url), shell=True, timeout=10, check=False)
        except Exception as failure:  # a notifier must never break the loop
            self._journal.emit("notify_failed", error=str(failure)[:200])


# -- comment bodies ---------------------------------------------------------
# They are the human-facing surface of the whole system, so they are written
# here rather than in the prompts: what the bot SAYS about its work must not be
# something the model can improvise.

def _pr_body(plan: dict, record: Record, config: Config) -> str:
    criteria = "\n".join(f"- [ ] {item}" for item in plan.get("acceptance", ())) or "- [ ] (none)"
    files = "\n".join(f"- `{item}`" for item in plan.get("files_expected", ())) or "- (to be discovered)"
    return "\n".join([
        plan.get("pr_body", "").strip(),
        "",
        "---",
        "",
        f"Closes #{record.issue}.",
        "",
        "## Acceptance criteria",
        "",
        criteria,
        "",
        "## Expected files",
        "",
        files,
        "",
        "## How this pull request runs",
        "",
        f"Opened as a draft by **forgeron** before the first line of code: the plan is "
        f"readable now, while the implementation runs. Estimated risk: "
        f"`{plan.get('risk', '?')}`.",
        "",
        f"Review as usual: inline comments, *request changes*, *approve*. Every piece of feedback "
        f"triggers a revision round (ceiling: {config.limits.max_rounds} rounds, "
        f"{config.limits.max_spend_usd:.0f} USD). The merge stays manual.",
    ])


MAX_VISUALS = 4


def _work_note(verdict: dict, record: Record, answered: tuple[Feedback, ...] = (),
               visuals: tuple[Visual, ...] = (),
               refused: tuple[tuple[str, str], ...] = ()) -> str:
    rows = "\n".join(
        f"| {'yes' if item.get('met') else 'NO'} | {item.get('criterion', '')} | "
        f"{_cell(item.get('evidence', ''))} |"
        for item in verdict.get("acceptance", ())
    ) or "| - | (no criterion) | - |"
    commands = "\n".join(f"    {command}" for command in verdict.get("commands_run", ())) or "    (none)"
    answers = _answers_note(verdict, answered) if answered else ""
    return "\n".join([
        f"### forgeron · round {record.rounds}",
        "",
        attribution.strip(verdict.get("summary", "")).strip(),
        "",
        answers,
        "",
        "| met | criterion | evidence |",
        "|---|---|---|",
        rows,
        "",
        "<details><summary>Commands run</summary>",
        "",
        "```",
        commands,
        "```",
        "",
        "</details>",
        _visual_block(visuals, refused),
    ])


def _visual_block(visuals: tuple[Visual, ...],
                  refused: tuple[tuple[str, str], ...]) -> str:
    """Every published image with, right below it, the command that regenerates it.

    It is the rule of `rendre-l-etat-visible` made visible to the reader:
    without this line, what they see is a screenshot, and they have no way
    to know whether it still describes the code they are reviewing.
    """
    if not visuals and not refused:
        return ""
    lines = ["", "#### Visuals", ""]
    for visual in visuals:
        lines += [f"![{visual.caption}]({visual.path})", "",
                  f"Regenerate: `{visual.command}`", ""]
    for path, reason in refused:
        lines.append(f"- `{path}` **set aside**: {reason}")
    return "\n".join(lines)


def _answers_note(verdict: dict, feedback: tuple[Feedback, ...]) -> str:
    """One line per remark received, in the order received.

    Positional rather than keyed on the remark, because the agent answers a list
    and a mis-keyed answer would be attached to the wrong remark - worse than an
    unanswered one, which at least looks unanswered.
    """
    lines = ["**Answers to the remarks:**", ""]
    answers = verdict.get("answers") or []
    for index, item in enumerate(feedback):
        answer = attribution.strip(answers[index]) if index < len(answers) \
            else "_(no explicit answer)_"
        head = f"**@{item.author}"
        head += f" · {item.path}:{item.line}**" if item.path else "**"
        lines += [f"{index + 1}. {head} — {answer}"]
    return "\n".join(lines)


def _questions_note(plan: dict) -> str:
    questions = "\n".join(f"{index}. {text}" for index, text in enumerate(plan["questions"], 1))
    return "\n".join([
        "**forgeron framed the subject and stops before coding.**",
        "",
        f"Estimated risk: `{plan.get('risk', '?')}`. What follows would change what gets built, "
        "so nothing is built before an answer:",
        "",
        questions,
        "",
        "Answering in a comment restarts the framing. No branch was pushed.",
    ])


def _wrap_note(verdict: dict, record: Record) -> str:
    followups = "\n".join(f"- {item}" for item in verdict.get("followups", ())) or "- (none)"
    return "\n".join([
        f"### forgeron · session closed",
        "",
        attribution.strip(verdict.get("summary", "")).strip(),
        "",
        f"Pull request #{record.pr} merged in {record.rounds} round(s), "
        f"{record.spent_usd:.2f} USD. Worktree deleted, branch kept.",
        "",
        "**Follow-ups spotted, to open as issues if they are worth it:**",
        "",
        followups,
    ])


def _tainted_note(tainted: tuple[tuple[str, str], ...]) -> str:
    listing = "\n".join(f"- `{sha}` — `{line.strip()}`" for sha, line in tainted)
    return "\n".join([
        "**forgeron refuses to proceed: a commit carries an AI attribution.**",
        "",
        listing,
        "",
        "The author of this repository does not want this line in their history, and the refusal is "
        "mechanical rather than left to the agent's vigilance. Three layers were meant to prevent it: "
        "the `attribution` setting, the `commit-msg` hook, and this check. The first two were "
        "bypassed, by `--no-verify` or by being absent.",
        "",
        "Rewrite the message or messages without the line, then publish the branch again.",
    ])


def _failure_note(phase: str, result) -> str:
    return "\n".join([
        f"**forgeron failed in the {phase} phase.**",
        "",
        f"    {result.detail}",
        "",
        f"Spent on this run: {result.cost_usd:.2f} USD. Nothing was pushed by this attempt.",
    ])


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _minutes_since(stamp: str) -> float:
    """Minutes elapsed, or zero when nothing was stamped.

    Zero rather than infinity: an unstamped wait has not started, and reading it
    as an infinite one would make the very first pass time out.
    """
    if not stamp:
        return 0.0
    try:
        then = datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc)
    except ValueError:
        return 0.0
    delta = datetime.datetime.now(datetime.timezone.utc) - then
    return max(0.0, delta.total_seconds() / 60.0)


def _cell(text: str) -> str:
    flat = " ".join(text.split())
    return (flat[:117] + "...") if len(flat) > 120 else flat
