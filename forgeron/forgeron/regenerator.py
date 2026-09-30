"""Checks that a command really reproduces the file it claims to produce.

A port with a single method, and its name says what it does rather than what it
uses. "Run a command" would be a much broader capability to hand to an agent;
"check that this command reproduces this file" is bounded by its own signature.

The move that matters is setting the file aside: the file is moved away BEFORE
the command runs again, and it has to come back. Without that, a command that
does nothing at all passes the check, since the file was already there. That is
the trap this repository paid for five times, a check unable to fail.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import subprocess

# GitHub renders only these in a comment. An extension outside the list is refused
# rather than sent: a file that does not display is a dead link in the middle of
# a review, and the author will not see it since they do not reread their own PR.
RENDERABLE = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm", ".mov")


@dataclasses.dataclass(frozen=True, slots=True)
class Reproduction:
    ok: bool
    reason: str = ""
    identical: bool = False   # are the bytes the same, so is the render deterministic


class ShellRegenerator:
    def __init__(self, timeout_seconds: int = 120, max_bytes: int = 10 * 1024 * 1024) -> None:
        self._timeout = timeout_seconds
        self._max_bytes = max_bytes

    def reproduce(self, worktree: str, path: str, command: str) -> Reproduction:
        """Set the file aside, run the command again, require that it comes back.

        Restores the original whatever happens: a check that destroys the artifact
        it examines turns a refusal into lost work.
        """
        root = os.path.realpath(worktree)
        target = os.path.realpath(os.path.join(root, path))

        # The path comes from the agent and the file goes to a forge. A path that
        # leaves the worktree would publish what nobody offered to publish.
        if os.path.commonpath([root, target]) != root:
            return Reproduction(False, f"path outside the worktree: {path}")
        if os.path.splitext(target)[1].lower() not in RENDERABLE:
            return Reproduction(False, f"extension not rendered by the forge: {path}")
        if not os.path.isfile(target):
            return Reproduction(False, f"file missing: {path}")

        size = os.path.getsize(target)
        if size > self._max_bytes:
            return Reproduction(False, f"{size} bytes, above the ceiling of {self._max_bytes}")

        before = _digest(target)
        aside = target + ".forgeron-aside"
        os.replace(target, aside)
        try:
            done = subprocess.run(command, shell=True, cwd=root, capture_output=True,
                                  text=True, timeout=self._timeout)
        except subprocess.TimeoutExpired:
            os.replace(aside, target)
            return Reproduction(False, f"the command exceeded {self._timeout} s")
        except Exception as failure:
            os.replace(aside, target)
            return Reproduction(False, f"{type(failure).__name__}: {failure}")

        if done.returncode != 0:
            os.replace(aside, target)
            detail = (done.stderr or done.stdout).strip().splitlines()
            return Reproduction(False, f"the command exits with {done.returncode}: "
                                       f"{detail[-1][:160] if detail else 'no output'}")

        if not os.path.isfile(target):
            os.replace(aside, target)
            return Reproduction(False, "the command succeeded without reproducing the file")

        # The file came back: the command does produce it. Identical bytes are
        # EXTRA information, not the condition - an encoder that timestamps its
        # images is still a legitimate producer.
        identical = _digest(target) == before
        os.remove(aside)
        return Reproduction(True, "reproduced" + ("" if identical else " (different bytes)"),
                            identical)


def _digest(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()
