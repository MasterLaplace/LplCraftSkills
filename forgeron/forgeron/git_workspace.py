"""Git, one worktree per issue.

A worktree rather than a clone: it shares the object store, so a second issue on
a 600 MiB repository costs the working files and not the history. And a worktree
rather than the human's checkout, which is the actual point - an unattended agent
must never be able to leave uncommitted changes in the tree someone is working in.
"""

from __future__ import annotations

import os
import shutil
import subprocess


class GitError(RuntimeError):
    pass


class GitWorkspace:
    def __init__(self, timeout: int = 300) -> None:
        self._timeout = timeout

    def prepare(self, repo_path: str, worktree: str, branch: str, base: str) -> None:
        """Make `worktree` exist, on `branch`, forked from the freshest `base`.

        Idempotent: re-entering after a crash reuses the worktree instead of
        failing, because the driver's transient phases are allowed to repeat.
        """
        self._git(repo_path, ["fetch", "origin", base, "--quiet"])

        if os.path.isdir(os.path.join(worktree, ".git")) or os.path.isfile(os.path.join(worktree, ".git")):
            self._git(worktree, ["checkout", branch, "--quiet"])
            return

        os.makedirs(os.path.dirname(worktree), exist_ok=True)
        remote_exists = self._git(
            repo_path, ["ls-remote", "--heads", "origin", branch], check=False
        ).strip()
        if remote_exists:
            # Resuming a branch the bot already pushed, possibly from another
            # machine. Track the remote rather than restarting from base, which
            # would silently drop work a human may already have reviewed.
            self._git(repo_path, ["fetch", "origin", branch, "--quiet"])
            self._git(repo_path, ["worktree", "add", worktree, "-B", branch,
                                  f"origin/{branch}", "--quiet"])
        else:
            self._git(repo_path, ["worktree", "add", worktree, "-b", branch,
                                  f"origin/{base}", "--quiet"])

    def has_commits_ahead(self, worktree: str, base: str) -> bool:
        count = self._git(worktree, ["rev-list", "--count", f"origin/{base}..HEAD"]).strip()
        return int(count or "0") > 0

    def is_synced(self, worktree: str, branch: str) -> bool:
        """Is what the agent claims to have pushed actually on the remote?

        The verdict is the agent's word; this is the check. A branch that never
        left the machine looks exactly like a finished one from inside the prompt.
        """
        self._git(worktree, ["fetch", "origin", branch, "--quiet"], check=False)
        local = self._git(worktree, ["rev-parse", "HEAD"]).strip()
        remote = self._git(worktree, ["rev-parse", f"origin/{branch}"], check=False).strip()
        return bool(local) and local == remote

    def rename_branch(self, worktree: str, new_branch: str) -> None:
        """Rename a branch that was never pushed.

        The worktree path is keyed by issue number, not by branch, because the
        path is part of the claude session's identity: renaming the branch is free,
        moving the directory would lose the conversation.
        """
        self._git(worktree, ["branch", "-m", new_branch])

    def is_dirty(self, worktree: str) -> bool:
        return bool(self._git(worktree, ["status", "--porcelain"]).strip())

    def commit_empty(self, worktree: str, message: str) -> None:
        self._git(worktree, ["commit", "--allow-empty", "-m", message, "--quiet"])

    def push(self, worktree: str, branch: str) -> None:
        self._git(worktree, ["push", "--set-upstream", "origin", branch, "--quiet"])

    def head(self, worktree: str) -> str:
        return self._git(worktree, ["rev-parse", "--short", "HEAD"]).strip()

    def sync_with_base(self, worktree: str, base: str, method: str) -> tuple[bool, list[str]]:
        """Bring the branch onto the freshest base. Returns (clean, conflicted files).

        Deliberately LEAVES a failed rebase or merge in progress: the conflicted
        files with their markers are the whole material an agent needs, and
        aborting first would hand it a clean tree and a description of a conflict
        it can no longer see.
        """
        self._git(worktree, ["fetch", "origin", base, "--quiet"])
        operation = ["rebase", f"origin/{base}"] if method.upper() == "REBASE" \
            else ["merge", f"origin/{base}", "--no-edit"]
        done = self._git(worktree, operation, check=False, capture_status=True)
        if done == 0:
            return True, []
        conflicted = self._git(
            worktree, ["diff", "--name-only", "--diff-filter=U"], check=False
        ).split()
        return False, conflicted

    def commit_messages(self, worktree: str, base: str) -> list[tuple[str, str]]:
        """Les commits que cette branche ajoute, en (sha court, message complet).

        Separateurs de contrôle plutôt qu'un saut de ligne : un message de commit
        contient des sauts de ligne, donc découper dessus fusionnerait un corps
        avec le commit suivant et le contrôle porterait sur du texte inventé.
        """
        raw = self._git(worktree, ["log", "--format=%h%x1f%B%x1e", f"origin/{base}..HEAD"],
                        check=False)
        commits = []
        for record in raw.split("\x1e"):
            if "\x1f" not in record:
                continue
            sha, _, message = record.partition("\x1f")
            commits.append((sha.strip(), message.strip("\n")))
        return commits

    def conflicted(self, worktree: str) -> list[str]:
        """Files git still considers unresolved. Empty is the only proof of success.

        Asked again AFTER the agent has worked, because "I resolved it" is a claim
        and an unmerged index entry is a fact. An agent that edits the files but
        forgets to stage them leaves markers in a tree that looks finished.
        """
        return self._git(worktree, ["diff", "--name-only", "--diff-filter=U"],
                         check=False).split()

    def abort_sync(self, worktree: str) -> None:
        """Put the tree back the way it was. Both, because only one is in progress."""
        self._git(worktree, ["rebase", "--abort"], check=False)
        self._git(worktree, ["merge", "--abort"], check=False)

    def push_forced(self, worktree: str, branch: str) -> None:
        """The one push that rewrites what is already published, and only after a rebase.

        `--force-with-lease` and never `--force`: the lease refuses if the remote
        moved since we last fetched, so a push somebody else made in the meantime
        stops this rather than disappearing. Plain `--force` would overwrite it
        without a word, and nothing downstream would ever show that it happened.
        """
        self._git(worktree, ["push", "--force-with-lease", "origin", branch, "--quiet"])

    def discard(self, worktree: str, repo_path: str) -> None:
        """Remove the worktree. The branch and its history stay on the forge.

        Deleting the branch here would destroy the record of a merged review, and
        the branch is the only snapshot of the work that outlives the machine.
        """
        if os.path.isdir(worktree):
            self._git(repo_path, ["worktree", "remove", "--force", worktree], check=False)
        if os.path.isdir(worktree):
            shutil.rmtree(worktree, ignore_errors=True)
        self._git(repo_path, ["worktree", "prune"], check=False)

    def _git(self, cwd: str, argv: list[str], check: bool = True,
             capture_status: bool = False):
        done = subprocess.run(
            ["git", "-C", cwd, *argv], capture_output=True, text=True, timeout=self._timeout,
        )
        if check and done.returncode != 0:
            raise GitError(f"git {' '.join(argv)} in {cwd} -> {done.returncode}: "
                           f"{done.stderr.strip()[:400]}")
        return done.returncode if capture_status else done.stdout
