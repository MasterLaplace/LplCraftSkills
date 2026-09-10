"""The seams. Everything with a side effect is declared here and nowhere else.

Three ports, split by what fails and how: the forge is a network away, the
workspace is a filesystem and a git index, the agent is a process that costs
money. Folding them into one client would mean a test of the review loop needs a
network, which is exactly how a review loop stops being tested.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .model import (CheckRun, CheckState, Feedback, IssueRef, MergeState,
                    Observation, PullRequestView, Record)


@runtime_checkable
class Forge(Protocol):
    """Issues, pull requests, reviews. GitHub in production, a fake in tests."""

    def list_issues(self, repo: str, labels: tuple[str, ...]) -> list[IssueRef]: ...

    def get_issue(self, repo: str, number: int) -> IssueRef: ...

    def find_pull_request(self, repo: str, head: str) -> PullRequestView | None: ...

    def create_draft_pull_request(
        self, repo: str, head: str, base: str, title: str, body: str
    ) -> PullRequestView: ...

    def mark_ready(self, repo: str, number: int) -> None: ...

    def request_review(self, repo: str, number: int, reviewers: tuple[str, ...]) -> None: ...

    def comment_on_pull_request(self, repo: str, number: int, body: str,
                                attachments: tuple[tuple[str, str], ...] = (),
                                cwd: str | None = None) -> None: ...

    def supports_attachments(self) -> bool: ...

    def comment_on_issue(self, repo: str, number: int, body: str) -> None: ...

    def collect_feedback(self, repo: str, pr: int, issue: int) -> list[Feedback]: ...

    def checks(self, repo: str, pr: int) -> tuple[CheckState, tuple[CheckRun, ...]]: ...

    def failing_logs(self, repo: str, runs: tuple[CheckRun, ...],
                     max_bytes: int = 12000) -> str: ...

    def merge_state(self, repo: str, pr: int) -> MergeState: ...

    def update_branch(self, repo: str, pull: PullRequestView, method: str) -> bool: ...

    def base_commits_since(self, repo: str, base: str, head_sha: str) -> list[str]: ...

    def repo_node_id(self, repo: str) -> str: ...

    def link_branch_to_issue(self, repo: str, issue_node_id: str,
                             repo_node_id: str, branch: str) -> bool: ...


@runtime_checkable
class Workspace(Protocol):
    """Git. One worktree per issue, so the human's own checkout is never touched."""

    def prepare(self, repo_path: str, worktree: str, branch: str, base: str) -> None: ...

    def has_commits_ahead(self, worktree: str, base: str) -> bool: ...

    def is_synced(self, worktree: str, branch: str) -> bool: ...

    def is_dirty(self, worktree: str) -> bool: ...

    def head(self, worktree: str) -> str: ...

    def rename_branch(self, worktree: str, new_branch: str) -> None: ...

    def commit_empty(self, worktree: str, message: str) -> None: ...

    def push(self, worktree: str, branch: str) -> None: ...

    def sync_with_base(self, worktree: str, base: str, method: str) -> tuple[bool, list[str]]: ...

    def commit_messages(self, worktree: str, base: str) -> list[tuple[str, str]]: ...

    def conflicted(self, worktree: str) -> list[str]: ...

    def abort_sync(self, worktree: str) -> None: ...

    def push_forced(self, worktree: str, branch: str) -> None: ...

    def discard(self, worktree: str, repo_path: str) -> None: ...


@runtime_checkable
class Regenerator(Protocol):
    """Prouve qu'une commande reproduit un fichier. Une seule methode, bornee par son nom.

    Un port a part plutot qu'une methode de Workspace : celui-ci possede git, et
    « lancer une commande arbitraire » est une capacite bien plus large que ce
    qu'on veut voir passer par la couture d'un depot.
    """

    def reproduce(self, worktree: str, path: str, command: str): ...


@runtime_checkable
class Agent(Protocol):
    """A claude run. Returns the structured verdict plus what it cost."""

    def run(
        self,
        *,
        cwd: str,
        session_id: str,
        prompt: str,
        schema: dict[str, Any],
        resume: bool,
        read_only: bool,
    ) -> "AgentResult": ...


class AgentResult(Protocol):
    ok: bool
    verdict: dict[str, Any]
    cost_usd: float
    detail: str
