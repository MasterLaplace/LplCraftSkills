"""Configuration as data, read from one JSON file, with every default written here.

A default buried in code is a default nobody can audit before letting a bot push,
so the dataclass is the documentation and `forgeron config --json` prints it.
"""

from __future__ import annotations

import dataclasses
import json
import os
from typing import Any

from .states import Limits

DEFAULT_HOME = os.path.expanduser("~/.forgeron")


@dataclasses.dataclass(frozen=True, slots=True)
class RepoConfig:
    """One repository the bot is allowed to touch.

    An allowlist rather than a scope: the forge token can reach every repository
    the human can, and "which repositories may a bot open pull requests on" is
    not a question a token can answer.
    """

    slug: str                       # "owner/name"
    path: str                       # local clone the worktrees branch from
    base: str = "main"
    labels: tuple[str, ...] = ("claude",)
    hold_label: str = "claude:hold"
    reviewers: tuple[str, ...] = ()
    branch_prefix: str = "feat"


@dataclasses.dataclass(frozen=True, slots=True)
class Config:
    home: str = DEFAULT_HOME
    repos: tuple[RepoConfig, ...] = ()
    limits: Limits = dataclasses.field(default_factory=Limits)
    max_concurrent: int = 1
    poll_seconds: int = 60
    model: str = "sonnet"
    budget_per_run_usd: float = 3.0
    continuity: str = "resume"      # "resume" keeps the conversation, "rebuild" restates context
    link_branch_to_issue: bool = True  # fill the issue's "Development" section
    checks_grace_seconds: int = 150  # how long an empty check rollup still means "not yet"
    checks_log_bytes: int = 12000    # how much failing log the agent is given
    notify_command: str = ""        # optional: shell template, {title} {url} available
    agent: str = "artisan" # "artisan" is the default agent, "claude" is the bare model, "" means no agent

    @property
    def state_dir(self) -> str:
        return os.path.join(self.home, "state")

    @property
    def worktree_dir(self) -> str:
        return os.path.join(self.home, "worktrees")

    @property
    def journal_path(self) -> str:
        return os.path.join(self.home, "journal.jsonl")

    def repo(self, slug: str) -> RepoConfig:
        for candidate in self.repos:
            if candidate.slug == slug:
                return candidate
        raise KeyError(f"repository {slug!r} is not in the allowlist")

    def to_dict(self) -> dict[str, Any]:
        return {
            "home": self.home,
            "repos": [dataclasses.asdict(repo) for repo in self.repos],
            "limits": dataclasses.asdict(self.limits),
            "max_concurrent": self.max_concurrent,
            "poll_seconds": self.poll_seconds,
            "model": self.model,
            "budget_per_run_usd": self.budget_per_run_usd,
            "continuity": self.continuity,
            "link_branch_to_issue": self.link_branch_to_issue,
            "checks_grace_seconds": self.checks_grace_seconds,
            "checks_log_bytes": self.checks_log_bytes,
            "notify_command": self.notify_command,
            "agent": self.agent,
        }


def load(path: str) -> Config:
    """Read a config file. Unknown keys are refused rather than ignored.

    A silently dropped key is how a limit stops applying without anyone noticing.
    """
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)

    known = {field.name for field in dataclasses.fields(Config)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"unknown configuration key(s): {', '.join(sorted(unknown))}")

    repos = tuple(_repo_from(entry) for entry in raw.pop("repos", []))
    limits_raw = raw.pop("limits", {})
    limits_known = {field.name for field in dataclasses.fields(Limits)}
    limits_unknown = set(limits_raw) - limits_known
    if limits_unknown:
        raise ValueError(f"unknown limits key(s): {', '.join(sorted(limits_unknown))}")
    return Config(repos=repos, limits=Limits(**limits_raw), **raw)


def _repo_from(entry: dict[str, Any]) -> RepoConfig:
    known = {field.name for field in dataclasses.fields(RepoConfig)}
    unknown = set(entry) - known
    if unknown:
        raise ValueError(f"unknown repo key(s): {', '.join(sorted(unknown))}")
    entry = dict(entry)
    for key in ("labels", "reviewers"):
        if key in entry:
            entry[key] = tuple(entry[key])
    return RepoConfig(**entry)
