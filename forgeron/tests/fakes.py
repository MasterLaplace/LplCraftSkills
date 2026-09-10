"""Fakes for the three ports, so the whole loop runs with no network and no cost.

Fakes rather than mocks: they hold state and answer consistently, which is what
lets a test walk a real journey (issue to merge) instead of asserting that a call
happened. A mock would prove the driver called `create_draft_pull_request`; a fake
proves the pull request then EXISTS, which is the thing the next pass depends on.
"""

from __future__ import annotations

import dataclasses
import itertools
from typing import Any

from forgeron.model import (CheckRun, CheckState, Feedback, FeedbackKind, IssueRef,
                            MergeState, PullRequestView)


class FakeForge:
    def __init__(self, issues: list[IssueRef], login: str = "bot") -> None:
        self.login = login
        self._issues = {(issue.repo, issue.number): issue for issue in issues}
        self._prs: dict[str, PullRequestView] = {}
        self.feedback: list[Feedback] = []
        self.comments: list[tuple[str, int, str]] = []      # (kind, number, body)
        self.review_requests: list[tuple[int, tuple[str, ...]]] = []
        self.marked_ready: list[int] = []
        # A settable state rather than a queue: `checks` is asked once per pass and
        # the count of passes is an implementation detail of the driver, so a queue
        # would make every test brittle against a refactor it does not care about.
        self.check_state: CheckState = CheckState.SUCCESS
        self.failing: tuple[CheckRun, ...] = ()
        self.logs = "error: expected 3, got 4\n"
        self.merge_state_value: MergeState = MergeState.CLEAN
        self.updates: list[tuple[int, str]] = []
        self.update_succeeds = True
        self.landed = ["abc1234 feat: un changement arrive sur main"]
        self.links: list[tuple[str, str]] = []
        self.attachments: list[tuple[str, str]] = []
        self.attachments_supported = True
        self._numbers = itertools.count(101)

    # -- reads --------------------------------------------------------------

    def list_issues(self, repo: str, labels: tuple[str, ...]) -> list[IssueRef]:
        return [issue for (slug, _), issue in self._issues.items()
                if slug == repo and issue.state == "OPEN"
                and (not labels or set(labels) & set(issue.labels))]

    def get_issue(self, repo: str, number: int) -> IssueRef:
        return self._issues[(repo, number)]

    def find_pull_request(self, repo: str, head: str) -> PullRequestView | None:
        return self._prs.get(head)

    def collect_feedback(self, repo: str, pr: int, issue: int) -> list[Feedback]:
        return list(self.feedback)

    def checks(self, repo: str, pr: int) -> tuple[CheckState, tuple[CheckRun, ...]]:
        return self.check_state, self.failing

    def ci_red(self, name: str = "build") -> None:
        self.check_state = CheckState.FAILURE
        self.failing = (CheckRun(name, "CI", CheckState.FAILURE,
                                 "https://fake/actions/runs/1/job/2", "2"),)

    def ci_green(self) -> None:
        self.check_state = CheckState.SUCCESS
        self.failing = ()

    def ci_pending(self) -> None:
        self.check_state = CheckState.PENDING
        self.failing = ()

    def failing_logs(self, repo: str, runs: tuple[CheckRun, ...], max_bytes: int = 12000) -> str:
        return self.logs

    def merge_state(self, repo: str, pr: int, attempts: int = 1) -> MergeState:
        return self.merge_state_value

    def update_branch(self, repo: str, pull: PullRequestView, method: str) -> bool:
        self.updates.append((pull.number, method))
        if self.update_succeeds:
            self.merge_state_value = MergeState.CLEAN
        return self.update_succeeds

    def base_commits_since(self, repo: str, base: str, head_sha: str) -> list[str]:
        return list(self.landed)

    def repo_node_id(self, repo: str) -> str:
        return "R_repo"

    def link_branch_to_issue(self, repo: str, issue_node_id: str, repo_node_id: str,
                             branch: str) -> bool:
        self.links.append((issue_node_id, branch))
        return True

    # -- writes -------------------------------------------------------------

    def create_draft_pull_request(self, repo: str, head: str, base: str, title: str,
                                  body: str) -> PullRequestView:
        pull = PullRequestView(number=next(self._numbers), url=f"https://fake/{head}",
                               head=head, is_draft=True, state="OPEN",
                               review_decision="", merged=False, head_sha="deadbee")
        self._prs[head] = pull
        self.comments.append(("pr-body", pull.number, body))
        return pull

    def mark_ready(self, repo: str, number: int) -> None:
        self.marked_ready.append(number)
        for head, pull in self._prs.items():
            if pull.number == number:
                self._prs[head] = dataclasses.replace(pull, is_draft=False)

    def request_review(self, repo: str, number: int, reviewers: tuple[str, ...]) -> None:
        self.review_requests.append((number, reviewers))

    def comment_on_pull_request(self, repo: str, number: int, body: str,
                                attachments: tuple[tuple[str, str], ...] = (),
                                cwd: str | None = None) -> None:
        self.comments.append(("pr", number, body))
        self.attachments.extend(attachments)

    def supports_attachments(self) -> bool:
        return self.attachments_supported

    def comment_on_issue(self, repo: str, number: int, body: str) -> None:
        self.comments.append(("issue", number, body))

    # -- test helpers -------------------------------------------------------

    def human_says(self, body: str, state: str = "CHANGES_REQUESTED",
                   kind: FeedbackKind = FeedbackKind.REVIEW, path: str = "", line: int = 0) -> None:
        self.feedback.append(Feedback(
            ident=f"f{len(self.feedback)}", kind=kind, author="human", body=body,
            created_at=f"2026-01-01T00:00:{len(self.feedback):02d}Z",
            state=state, path=path, line=line,
        ))

    def approve(self, head: str) -> None:
        self._prs[head] = dataclasses.replace(self._prs[head], review_decision="APPROVED",
                                              reviewed=True)

    def mark_reviewed(self, head: str) -> None:
        self._prs[head] = dataclasses.replace(self._prs[head], reviewed=True)

    def merge(self, head: str) -> None:
        self._prs[head] = dataclasses.replace(self._prs[head], merged=True, state="MERGED")

    def close_issue(self, repo: str, number: int) -> None:
        issue = self._issues[(repo, number)]
        self._issues[(repo, number)] = dataclasses.replace(issue, state="CLOSED")

    def bodies(self, kind: str = "") -> list[str]:
        return [body for entry_kind, _, body in self.comments if not kind or entry_kind == kind]


class FakeWorkspace:
    """Git that remembers, and that can be told to lie about being pushed."""

    def __init__(self, synced: bool = True) -> None:
        self.prepared: list[tuple[str, str]] = []
        self.pushes: list[str] = []
        self.branch: str = ""
        self.commits: list[str] = []
        self.discarded: list[str] = []
        self.ahead = True
        self.synced = synced
        self.dirty = False
        # A scripted conflict: the files git reports unresolved after a sync, and
        # whether the agent is supposed to have cleared them afterwards.
        self.conflicts_on_sync: list[str] = []
        self.conflicts_remaining: list[str] = []
        self.syncs: list[tuple[str, str]] = []
        self.forced_pushes: list[str] = []
        self.aborts = 0
        # (sha, message) des commits que la branche ajoute. Propres par defaut :
        # le cas courant ne doit rien couter aux tests qui ne parlent pas d'attribution.
        self.branch_commits: list[tuple[str, str]] = []

    def prepare(self, repo_path: str, worktree: str, branch: str, base: str) -> None:
        self.prepared.append((worktree, branch))
        self.branch = branch

    def has_commits_ahead(self, worktree: str, base: str) -> bool:
        return self.ahead

    def is_synced(self, worktree: str, branch: str) -> bool:
        return self.synced

    def rename_branch(self, worktree: str, new_branch: str) -> None:
        self.branch = new_branch

    def commit_empty(self, worktree: str, message: str) -> None:
        self.commits.append(message)

    def is_dirty(self, worktree: str) -> bool:
        return self.dirty

    def head(self, worktree: str) -> str:
        return "cafe123"

    def sync_with_base(self, worktree: str, base: str, method: str) -> tuple[bool, list[str]]:
        self.syncs.append((base, method))
        if self.conflicts_on_sync:
            return False, list(self.conflicts_on_sync)
        return True, []

    def commit_messages(self, worktree: str, base: str) -> list[tuple[str, str]]:
        return list(self.branch_commits)

    def conflicted(self, worktree: str) -> list[str]:
        return list(self.conflicts_remaining)

    def abort_sync(self, worktree: str) -> None:
        self.aborts += 1

    def push_forced(self, worktree: str, branch: str) -> None:
        self.forced_pushes.append(branch)

    def push(self, worktree: str, branch: str) -> None:
        self.pushes.append(branch)

    def discard(self, worktree: str, repo_path: str) -> None:
        self.discarded.append(worktree)


@dataclasses.dataclass
class FakeResult:
    ok: bool
    verdict: dict[str, Any]
    cost_usd: float
    detail: str
    session_id: str = "sid"
    turns: int = 1
    denials: tuple[str, ...] = ()


class FakeAgent:
    """Answers each phase from a script, and records the prompt it was handed.

    The prompt is recorded because half the behaviour under test is what the agent
    is TOLD: a revision round that forgets to include the reviewer's words is a
    silent failure the phases would never reveal.
    """

    def __init__(self, cost: float = 0.5) -> None:
        self.calls: list[dict[str, Any]] = []
        self.cost = cost
        self.plan: dict[str, Any] = {
            "branch_slug": "cache-lru", "kind": "feat", "pr_title": "feat: cache LRU",
            "pr_body": "Un cache LRU borne.", "acceptance": ["la suite passe deux fois d'affilee"],
            "files_expected": ["src/cache.py"], "risk": "low", "questions": [],
        }
        self.work: dict[str, Any] = {
            "verdict": "ready_for_review", "summary": "Cache ajoute.",
            "commands_run": ["pytest -q"],
            "acceptance": [{"criterion": "la suite passe", "met": True, "evidence": "12 passed"}],
            "pushed": True, "answers": ["Renomme."],
        }
        self.wrap: dict[str, Any] = {"summary": "Livre.", "followups": []}
        self.fail_next = False

    def run(self, *, cwd, session_id, prompt, schema, resume, read_only, contract="") -> FakeResult:
        self.calls.append({"prompt": prompt, "resume": resume, "read_only": read_only,
                           "session_id": session_id, "cwd": cwd, "contract": contract})
        if self.fail_next:
            self.fail_next = False
            return FakeResult(False, {}, self.cost, "budget epuise")
        if "branch_slug" in schema.get("properties", {}):
            return FakeResult(True, dict(self.plan), self.cost, "ok")
        if "followups" in schema.get("properties", {}):
            return FakeResult(True, dict(self.wrap), self.cost, "ok")
        return FakeResult(True, dict(self.work), self.cost, "ok")

    @property
    def prompts(self) -> list[str]:
        return [call["prompt"] for call in self.calls]


@dataclasses.dataclass
class FakeReproduction:
    ok: bool
    reason: str = ""
    identical: bool = True


class FakeRegenerator:
    """Rejoue un verdict scripte par chemin, et enregistre ce qu'on lui a demande.

    Le vrai vérificateur écarte le fichier et relance une commande ; le fake ne
    peut pas le simuler honnêtement, donc il ne prétend pas le faire. Ce qu'il
    exerce est la décision du pilote autour du verdict, et c'est
    `test-regenerator` qui exerce le verdict lui-même, contre un vrai disque.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.refuse: dict[str, str] = {}

    def reproduce(self, worktree: str, path: str, command: str) -> FakeReproduction:
        self.calls.append((path, command))
        if path in self.refuse:
            return FakeReproduction(False, self.refuse[path])
        return FakeReproduction(True, "reproduit")
