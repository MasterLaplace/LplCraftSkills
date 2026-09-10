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
    ) -> None:
        self._config = config
        self._forge = forge
        self._workspace = workspace
        self._agent = agent
        self._store = store
        self._journal = journal
        self._dry_run = dry_run
        self._regenerator = regenerator

    # -- one pass -----------------------------------------------------------

    def pass_once(self) -> list[Decision]:
        """Discover, then advance every record at most one step. Returns what it did."""
        for repo in self._config.repos:
            self._discover(repo)

        taken: list[Decision] = []
        acted = 0
        for record in self._store.all():
            if record.phase.is_terminal:
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
            self._store.save(record)
            self._journal.emit("adopted", key=record.key, title=issue.title,
                               session=record.session_id)

    def _advance(self, record: Record) -> Decision:
        repo = self._config.repo(record.repo)
        observation = self.observe(record, repo)
        decision = decide(record, observation, self._config.limits)
        self._journal.emit("decided", key=record.key, phase=record.phase.value,
                           action=decision.action.value, reason=decision.reason)
        if decision.action is Action.NOTHING:
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
            self._store.save(record)
            self._journal.emit("action_failed", key=record.key,
                               action=decision.action.value, error=str(failure)[:300])
            return Decision(Action.BLOCK, Phase.BLOCKED, str(failure)[:200])
        self._store.save(record)
        self._journal.emit("advanced", key=record.key, phase=record.phase.value,
                           spent=round(record.spent_usd, 4))
        return decision

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
        self._store.save(record)

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
            self._forge.comment_on_issue(record.repo, record.issue, _failure_note("cadrage", result))
            return record.with_(phase=Phase.BLOCKED, note=f"plan: {result.detail}")

        plan = result.verdict
        record = record.with_(plan=plan)

        if phase_after_plan(plan) is Phase.AWAITING_ANSWER:
            self._forge.comment_on_issue(record.repo, record.issue, _questions_note(plan))
            self._journal.emit("asked_human", key=record.key, questions=len(plan["questions"]))
            return record.with_(phase=Phase.AWAITING_ANSWER,
                                note="questions posees, en attente de reponse")

        # <type>/<numero>-<slug>, exactly what tracer-le-travail prescribes. The
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
                f"chore({plan['branch_slug']}): amorce pour #{record.issue}",
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
        (`42-titre-de-l-issue`). The mutation behind it takes a name, so the link
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
        self._store.save(record)

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
        self._store.save(record)

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
                            note="en attente de l'integration continue")

    def _do_fix_checks(self, record: Record, repo: RepoConfig, obs: Observation,
                       decision: Decision) -> Record:
        issue = self._forge.get_issue(record.repo, record.issue)
        self._workspace.prepare(repo.path, record.worktree, record.branch, repo.base)

        failing = obs.failing_checks
        logs = self._forge.failing_logs(record.repo, failing, self._config.checks_log_bytes)
        attempt = record.check_fixes + 1
        record = record.with_(phase=Phase.FIXING_CHECKS, check_fixes=attempt)
        self._store.save(record)
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
            return record.with_(phase=Phase.BLOCKED, note="rien a mettre a jour")

        method = sync_method(obs, self._config.limits)
        updated = self._forge.update_branch(record.repo, obs.pr, method)
        self._journal.emit("branch_synced" if updated else "sync_refused",
                           key=record.key, method=method, pr=obs.pr.number,
                           reviewed=obs.pr.reviewed)
        if not updated:
            # Either a conflict appeared between the observation and the call, or
            # the head moved and the lease refused. Both are answered by looking
            # again next pass rather than by forcing anything.
            return record.with_(note="mise a jour refusee, nouvelle observation au tour suivant")

        # A new head means CI has to run again, so the wait restarts. Forgetting this
        # would let the previous head's timeout expire the new one.
        return record.with_(phase=decision.phase, syncs=record.syncs + 1,
                            checks_since="", note=f"branche mise a jour par {method.lower()}")

    def _do_resolve_conflict(self, record: Record, repo: RepoConfig, obs: Observation,
                             decision: Decision) -> Record:
        issue = self._forge.get_issue(record.repo, record.issue)
        self._workspace.prepare(repo.path, record.worktree, record.branch, repo.base)
        method = sync_method(obs, self._config.limits)

        attempt = record.conflicts + 1
        record = record.with_(phase=Phase.RESOLVING, conflicts=attempt,
                              rounds=record.rounds + 1)
        self._store.save(record)

        clean, conflicted = self._workspace.sync_with_base(record.worktree, repo.base, method)
        self._journal.emit("conflict", key=record.key, method=method, attempt=attempt,
                           files=",".join(conflicted) or "-", clean=clean)

        if clean:
            # git managed what GitHub said it could not. Happens: GitHub judges a
            # merge commit, git replays commits one at a time. No agent needed.
            self._push_after_sync(record, method)
            return record.with_(phase=Phase.IMPLEMENTED, checks_since="",
                                note=f"mis a jour par {method.lower()}, sans conflit reel")

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
            reason = (f"conflits non resolus : {', '.join(remaining)}" if remaining
                      else result.verdict.get("blocked_reason") or result.detail)
            if record.pr:
                self._forge.comment_on_pull_request(record.repo, record.pr, "\n".join([
                    f"**forgeron n'a pas su resoudre le conflit avec `{repo.base}`.**",
                    "", reason, "",
                    "L'operation a ete annulee : la branche est telle qu'elle etait avant la "
                    "tentative, rien n'a ete pousse. Un commentaire relance un tour.",
                ]))
            return record.with_(phase=Phase.BLOCKED, note=f"conflit: {reason[:200]}")

        self._push_after_sync(record, method)
        if record.pr:
            self._forge.comment_on_pull_request(record.repo, record.pr, "\n".join([
                f"### forgeron · conflit avec `{repo.base}` resolu ({method.lower()})",
                "",
                attribution.strip(result.verdict.get("summary", "")).strip(),
                "",
                "⚠ **Cette resolution n'a ete relue par personne.** Fusionner deux changements "
                "peut produire quelque chose qui compile et qui est faux, donc la revue est "
                "redemandee meme si la pull request etait deja approuvee.",
            ]))
        # Back to the CI gate, and therefore back through a review request. A merge
        # of two changes is new code, and it has never been read by anyone.
        return record.with_(phase=Phase.IMPLEMENTED, checks_since="",
                            note=f"conflit resolu par {method.lower()}")

    def _push_after_sync(self, record: Record, method: str) -> None:
        """A rebase rewrote the branch, so the push has to overwrite. A merge did not."""
        if method.upper() == "REBASE":
            self._workspace.push_forced(record.worktree, record.branch)
        else:
            self._workspace.push(record.worktree, record.branch)

    def _do_request_review(self, record: Record, repo: RepoConfig, obs: Observation,
                           decision: Decision) -> Record:
        if obs.pr is None:
            return record.with_(phase=Phase.BLOCKED, note="pas de pull request a soumettre")
        if obs.pr.is_draft:
            self._forge.mark_ready(record.repo, obs.pr.number)
        self._forge.request_review(record.repo, obs.pr.number, repo.reviewers)
        self._forge.comment_on_pull_request(record.repo, obs.pr.number, "\n".join([
            "**Prete pour relecture.**",
            "",
            {
                CheckState.SUCCESS: "Integration continue : verte.",
                CheckState.NONE: "Integration continue : aucun check sur ce depot, "
                                 "rien n'a donc ete verifie automatiquement.",
            }.get(obs.checks, f"Integration continue : {obs.checks.value}."),
            "",
            f"Tours de travail : {record.rounds} · correctifs de CI : {record.check_fixes} · "
            f"depense : {record.spent_usd:.2f} USD.",
            "",
            "Relire normalement. Chaque commentaire, *request changes* ou reponse relance un tour ; "
            "une approbation laisse la fusion a un humain.",
        ]))
        self._notify(f"revue demandee : {record.repo}#{record.issue}", obs.pr.url)
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
        self._notify(f"fusionnee : {record.repo}#{record.issue}",
                     obs.pr.url if obs.pr else "")
        self._journal.emit("closed", key=record.key, rounds=record.rounds,
                           spent=round(record.spent_usd, 4))
        return record.with_(phase=Phase.DONE, note="fusionnee et cloturee")

    def _do_block(self, record: Record, repo: RepoConfig, obs: Observation,
                  decision: Decision) -> Record:
        target = record.pr or record.issue
        note = "\n".join([
            "**forgeron s'arrete et rend la main.**",
            "",
            f"Raison : {decision.reason}",
            f"Tours effectues : {record.rounds} · depense : {record.spent_usd:.2f} USD",
            "",
            f"La branche `{record.branch}` reste en place, telle quelle. Retirer l'etiquette "
            f"`{repo.hold_label}` et commenter relance le tour suivant.",
        ])
        if record.pr:
            self._forge.comment_on_pull_request(record.repo, record.pr, note)
        else:
            self._forge.comment_on_issue(record.repo, record.issue, note)
        self._notify(f"bloquee : {record.repo}#{record.issue}", decision.reason)
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
                                                    _failure_note("travail", result))
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
                    f"**forgeron est bloque.**\n\n{reason}\n\n"
                    f"Un commentaire de ta part relance le tour suivant.",
                )
            return record.with_(phase=Phase.BLOCKED, note=f"agent bloque: {reason[:200]}")

        # Uncommitted files are about to be destroyed with the worktree, and the
        # agent is the only one who knew they mattered. Reported rather than
        # committed for it: guessing a commit message for work we did not do would
        # put something in the history nobody can review.
        if self._workspace.is_dirty(record.worktree):
            self._journal.emit("worktree_dirty", key=record.key,
                               detail="des fichiers non commites seront perdus au nettoyage")

        tainted = self._attributed_commits(record, repo)
        if tainted:
            if record.pr:
                self._forge.comment_on_pull_request(record.repo, record.pr, _tainted_note(tainted))
            return record.with_(phase=Phase.BLOCKED,
                                note=f"attribution IA dans {len(tainted)} commit(s)")

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
        """Ne garde que les visuels dont la commande reproduit reellement le fichier.

        Le refus est RAPPORTE et non silencieux : un agent qui a produit une image
        et se la voit ecarter doit pouvoir lire pourquoi, et un relecteur doit
        savoir qu'il manque quelque chose plutot que de croire qu'il n'y avait
        rien a montrer.
        """
        declared = verdict.get("visuals") or []
        if not declared:
            return (), ()
        if self._regenerator is None:
            return (), (("(tous)", "aucun verificateur de regeneration n'est cable"),)
        if not self._forge.supports_attachments():
            return (), (("(tous)", "gh est trop ancien pour --attach, il faut 2.99.0"),)

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
            refused.append((entry.get("path", "?"), f"au-dela du plafond de {MAX_VISUALS}"))
        return tuple(accepted), tuple(refused)

    def _attributed_commits(self, record: Record, repo: RepoConfig):
        """Les commits de la branche qui portent une attribution IA.

        Une troisième couche derrière le réglage et le hook, et elle existe parce
        que les deux premières ont chacune un trou : `git commit --no-verify`
        saute le hook, et un conteneur neuf n'en a aucun. Celle-ci ne prévient
        rien et n'est contournable par rien, puisqu'elle regarde le résultat.
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
    criteria = "\n".join(f"- [ ] {item}" for item in plan.get("acceptance", ())) or "- [ ] (aucun)"
    files = "\n".join(f"- `{item}`" for item in plan.get("files_expected", ())) or "- (a decouvrir)"
    return "\n".join([
        plan.get("pr_body", "").strip(),
        "",
        "---",
        "",
        f"Referme #{record.issue}.",
        "",
        "## Criteres d'acceptation",
        "",
        criteria,
        "",
        "## Fichiers attendus",
        "",
        files,
        "",
        "## Conduite de cette pull request",
        "",
        f"Ouverte en brouillon par **forgeron** avant la premiere ligne de code : le plan est "
        f"lisible maintenant, pendant que l'implementation tourne. Risque estime : "
        f"`{plan.get('risk', '?')}`.",
        "",
        f"Relire normalement : commentaires en ligne, *request changes*, *approve*. Chaque retour "
        f"declenche un tour de revision (plafond : {config.limits.max_rounds} tours, "
        f"{config.limits.max_spend_usd:.0f} USD). La fusion reste manuelle.",
    ])


MAX_VISUALS = 4


def _work_note(verdict: dict, record: Record, answered: tuple[Feedback, ...] = (),
               visuals: tuple[Visual, ...] = (),
               refused: tuple[tuple[str, str], ...] = ()) -> str:
    rows = "\n".join(
        f"| {'oui' if item.get('met') else 'NON'} | {item.get('criterion', '')} | "
        f"{_cell(item.get('evidence', ''))} |"
        for item in verdict.get("acceptance", ())
    ) or "| - | (aucun critere) | - |"
    commands = "\n".join(f"    {command}" for command in verdict.get("commands_run", ())) or "    (aucune)"
    answers = _answers_note(verdict, answered) if answered else ""
    return "\n".join([
        f"### forgeron · tour {record.rounds}",
        "",
        attribution.strip(verdict.get("summary", "")).strip(),
        "",
        answers,
        "",
        "| tenu | critere | preuve |",
        "|---|---|---|",
        rows,
        "",
        "<details><summary>Commandes lancees</summary>",
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
    """Chaque image publiee avec, juste dessous, la commande qui la regenere.

    C'est la regle de `rendre-l-etat-visible` rendue visible pour le lecteur :
    sans cette ligne, ce qu'il voit est une capture d'ecran, et il n'a aucun moyen
    de savoir si elle decrit encore le code qu'il relit.
    """
    if not visuals and not refused:
        return ""
    lines = ["", "#### Visuels", ""]
    for visual in visuals:
        lines += [f"![{visual.caption}]({visual.path})", "",
                  f"Regenerer : `{visual.command}`", ""]
    for path, reason in refused:
        lines.append(f"- `{path}` **ecarte** : {reason}")
    return "\n".join(lines)


def _answers_note(verdict: dict, feedback: tuple[Feedback, ...]) -> str:
    """One line per remark received, in the order received.

    Positional rather than keyed on the remark, because the agent answers a list
    and a mis-keyed answer would be attached to the wrong remark - worse than an
    unanswered one, which at least looks unanswered.
    """
    lines = ["**Reponses aux remarques :**", ""]
    answers = verdict.get("answers") or []
    for index, item in enumerate(feedback):
        answer = attribution.strip(answers[index]) if index < len(answers) \
            else "_(sans reponse explicite)_"
        head = f"**@{item.author}"
        head += f" · {item.path}:{item.line}**" if item.path else "**"
        lines += [f"{index + 1}. {head} — {answer}"]
    return "\n".join(lines)


def _questions_note(plan: dict) -> str:
    questions = "\n".join(f"{index}. {text}" for index, text in enumerate(plan["questions"], 1))
    return "\n".join([
        "**forgeron a cadre le sujet et s'arrete avant de coder.**",
        "",
        f"Risque estime : `{plan.get('risk', '?')}`. Ce qui suit changerait ce qui est construit, "
        "donc rien n'est construit avant reponse :",
        "",
        questions,
        "",
        "Repondre en commentaire relance le cadrage. Aucune branche n'a ete poussee.",
    ])


def _wrap_note(verdict: dict, record: Record) -> str:
    followups = "\n".join(f"- {item}" for item in verdict.get("followups", ())) or "- (aucune)"
    return "\n".join([
        f"### forgeron · session close",
        "",
        attribution.strip(verdict.get("summary", "")).strip(),
        "",
        f"Pull request #{record.pr} fusionnee en {record.rounds} tour(s), "
        f"{record.spent_usd:.2f} USD. Worktree supprime, branche conservee.",
        "",
        "**Suites reperees, a ouvrir en issues si elles valent la peine :**",
        "",
        followups,
    ])


def _tainted_note(tainted: tuple[tuple[str, str], ...]) -> str:
    listing = "\n".join(f"- `{sha}` — `{line.strip()}`" for sha, line in tainted)
    return "\n".join([
        "**forgeron refuse d'avancer : un commit porte une attribution IA.**",
        "",
        listing,
        "",
        "L'auteur de ce depot ne veut pas de cette ligne dans son historique, et le refus est "
        "mecanique plutot que confie a la vigilance de l'agent. Trois couches devaient l'empecher : "
        "le reglage `attribution`, le hook `commit-msg`, et ce controle. Les deux premieres ont "
        "ete contournees, par `--no-verify` ou par leur absence.",
        "",
        "Reecrire le ou les messages sans la ligne, puis republier la branche.",
    ])


def _failure_note(phase: str, result) -> str:
    return "\n".join([
        f"**forgeron a echoue en phase de {phase}.**",
        "",
        f"    {result.detail}",
        "",
        f"Depense sur ce run : {result.cost_usd:.2f} USD. Rien n'a ete pousse par cette tentative.",
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
