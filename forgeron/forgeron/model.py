"""Value types crossing the ports. All frozen: a record is replaced, never mutated.

Mutation in place would let a failed action leave a half-updated record on disk,
which is the one state the reconciler cannot recover from because it looks valid.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any


class Phase(str, enum.Enum):
    """Where an issue stands in the loop.

    Phases ending in -ING are transient: a process holds a lease and is running an
    agent. A crash there is recovered by re-entering the same action, so every
    action must be idempotent.
    """

    QUEUED = "queued"
    PLANNING = "planning"
    AWAITING_ANSWER = "awaiting_answer"
    DRAFTED = "drafted"
    IMPLEMENTING = "implementing"
    IMPLEMENTED = "implemented"
    AWAITING_CHECKS = "awaiting_checks"
    FIXING_CHECKS = "fixing_checks"
    RESOLVING = "resolving"
    IN_REVIEW = "in_review"
    REVISING = "revising"
    REVISED = "revised"
    MERGED = "merged"
    DONE = "done"
    BLOCKED = "blocked"
    ABANDONED = "abandoned"

    @property
    def is_transient(self) -> bool:
        return self in (Phase.PLANNING, Phase.IMPLEMENTING, Phase.REVISING,
                        Phase.FIXING_CHECKS, Phase.RESOLVING)

    @property
    def is_terminal(self) -> bool:
        return self in (Phase.DONE, Phase.ABANDONED)


class Action(str, enum.Enum):
    """What the driver should do next. One action per pass, at most."""

    NOTHING = "nothing"
    PLAN = "plan"
    IMPLEMENT = "implement"
    WAIT_CHECKS = "wait_checks"
    FIX_CHECKS = "fix_checks"
    SYNC_BRANCH = "sync_branch"
    RESOLVE_CONFLICT = "resolve_conflict"
    REQUEST_REVIEW = "request_review"
    REVISE = "revise"
    WRAP_UP = "wrap_up"
    BLOCK = "block"
    ABANDON = "abandon"


class CheckState(str, enum.Enum):
    """What continuous integration says about the head commit.

    NONE and PENDING are kept apart on purpose. An empty rollup means either "this
    repository has no CI" or "GitHub has not created the check runs yet", and those
    two need opposite answers: ask for review, or keep waiting. The engine tells
    them apart with a grace period, never the forge.
    """

    NONE = "none"
    PENDING = "pending"
    SUCCESS = "success"
    FAILURE = "failure"


@dataclasses.dataclass(frozen=True, slots=True)
class CheckRun:
    name: str
    workflow: str
    state: CheckState
    url: str
    job_id: str = ""     # parsed out of the details URL, needed to fetch the log


class MergeState(str, enum.Enum):
    """Where the branch stands against its base, in GitHub's own words.

    The values are GitHub's, not ours, and their descriptions come from the
    GraphQL schema itself (introspected 2026-08-28):

      CLEAN     mergeable and passing commit status
      BEHIND    the head ref is out of date
      DIRTY     the merge commit cannot be cleanly created  (a conflict)
      BLOCKED   the merge is blocked                        (a rule, not us)
      UNSTABLE  mergeable with non-passing commit status
      HAS_HOOKS mergeable, passing, with pre-receive hooks
      UNKNOWN   the state cannot currently be determined

    UNKNOWN is the one that matters and the one that is misread: GitHub computes
    mergeability LAZILY, so the first read after a push is almost always UNKNOWN.
    It means "ask again in a moment", never "nothing to do" - and a driver that
    treats it as CLEAN will merrily ask for a review on a conflicted branch.
    """

    CLEAN = "CLEAN"
    BEHIND = "BEHIND"
    DIRTY = "DIRTY"
    BLOCKED = "BLOCKED"
    UNSTABLE = "UNSTABLE"
    HAS_HOOKS = "HAS_HOOKS"
    UNKNOWN = "UNKNOWN"

    @property
    def needs_sync(self) -> bool:
        return self is MergeState.BEHIND

    @property
    def has_conflict(self) -> bool:
        return self is MergeState.DIRTY


class FeedbackKind(str, enum.Enum):
    REVIEW = "review"          # a submitted review (approve / request changes / comment)
    INLINE = "inline"          # a comment anchored to a file and line
    CONVERSATION = "conversation"  # a plain PR comment
    ISSUE = "issue"            # a comment on the issue itself


@dataclasses.dataclass(frozen=True, slots=True)
class Feedback:
    """One thing a human said. `ident` is the forge's own id, used for the cursor.

    A timestamp cursor alone loses items written in the same second, and a
    duplicated round costs a full agent run, so identity is what we track.
    """

    ident: str
    kind: FeedbackKind
    author: str
    body: str
    created_at: str
    state: str = ""      # for REVIEW: APPROVED / CHANGES_REQUESTED / COMMENTED
    path: str = ""       # for INLINE
    line: int = 0        # for INLINE


@dataclasses.dataclass(frozen=True, slots=True)
class IssueRef:
    repo: str            # "owner/name"
    number: int
    title: str
    body: str
    url: str
    labels: tuple[str, ...] = ()
    state: str = "OPEN"
    node_id: str = ""      # GraphQL id, needed to link a branch to the issue


@dataclasses.dataclass(frozen=True, slots=True)
class PullRequestView:
    number: int
    url: str
    head: str
    is_draft: bool
    state: str            # OPEN / MERGED / CLOSED
    review_decision: str  # APPROVED / CHANGES_REQUESTED / REVIEW_REQUIRED / ""
    merged: bool
    head_sha: str = ""
    node_id: str = ""          # GraphQL id, needed to ask GitHub to update the branch
    reviewed: bool = False     # a human has already submitted a review on it


@dataclasses.dataclass(frozen=True, slots=True)
class Observation:
    """Everything the forge says right now. Built once per pass, per issue.

    Observing and deciding are separate so that a decision is reproducible from a
    recorded observation: every bug report is a fixture.
    """

    issue_open: bool
    held: bool                       # the pause label is on
    pr: PullRequestView | None = None
    new_feedback: tuple[Feedback, ...] = ()
    checks: CheckState = CheckState.NONE
    failing_checks: tuple[CheckRun, ...] = ()
    checks_waited_minutes: float = 0.0
    merge_state: MergeState = MergeState.UNKNOWN

    @property
    def merged(self) -> bool:
        return self.pr is not None and self.pr.merged

    @property
    def approved(self) -> bool:
        return self.pr is not None and self.pr.review_decision == "APPROVED"


@dataclasses.dataclass(frozen=True, slots=True)
class Record:
    """The persisted state of one issue's session. This is the only durable state.

    `session_id` is minted by us, not by claude, so a resume never has to guess
    which conversation belongs to which issue.
    """

    repo: str
    issue: int
    phase: Phase = Phase.QUEUED
    session_id: str = ""
    branch: str = ""
    worktree: str = ""
    pr: int = 0
    rounds: int = 0
    check_fixes: int = 0
    syncs: int = 0              # branch updates asked of GitHub, cheap
    conflicts: int = 0          # conflicts an agent had to resolve, expensive
    checks_since: str = ""      # when this head commit started waiting for CI
    spent_usd: float = 0.0
    seen_feedback: tuple[str, ...] = ()
    plan: dict[str, Any] = dataclasses.field(default_factory=dict)
    last_verdict: dict[str, Any] = dataclasses.field(default_factory=dict)
    note: str = ""
    updated_at: str = ""

    @property
    def key(self) -> str:
        return f"{self.repo.replace('/', '__')}__{self.issue}"

    def with_(self, **changes: Any) -> "Record":
        return dataclasses.replace(self, **changes)


@dataclasses.dataclass(frozen=True, slots=True)
class Decision:
    action: Action
    phase: Phase          # phase to persist once the action succeeds
    reason: str           # why, in one line - this goes straight to the journal
