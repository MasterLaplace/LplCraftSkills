"""One `claude -p` run per phase, answering a schema.

Three facts drive the shape of this module, all three measured rather than assumed
(see tests/probes/):

1. `--tools`, `--allowedTools` and `--add-dir` are VARIADIC, so a prompt passed
   as a positional argument after any of them is eaten as another value and claude
   exits with "Input must be provided". The prompt therefore always goes on stdin.
2. `--session-id <uuid>` lets the caller MINT the identifier, and `--resume <uuid>`
   picks the conversation back up in a new process. That is what makes a review
   round cheap: round 4 still remembers round 1.
3. the session file lives at ~/.claude/projects/<slug-of-cwd>/<uuid>.jsonl, so the
   working directory is part of the session's identity. Moving a worktree breaks
   resume - which is why the cluster story is `continuity="rebuild"`, not a
   shared volume.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
from typing import Any


@dataclasses.dataclass(frozen=True, slots=True)
class Result:
    ok: bool
    verdict: dict[str, Any]
    cost_usd: float
    detail: str
    session_id: str = ""
    turns: int = 0
    denials: tuple[str, ...] = ()


class ClaudeAgent:
    def __init__(
        self,
        executable: str = "claude",
        model: str = "sonnet",
        budget_usd: float = 3.0,
        timeout: int = 3600,
        contract: str = "",
        dry_run: bool = False,
    ) -> None:
        self._claude = executable
        self._model = model
        self._budget = budget_usd
        self._timeout = timeout
        self._contract = contract
        self._dry_run = dry_run

    def run(
        self,
        *,
        cwd: str,
        session_id: str,
        prompt: str,
        schema: dict[str, Any],
        resume: bool,
        read_only: bool,
        contract: str = "",
    ) -> Result:
        argv = [
            self._claude, "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
            "--model", self._model,
            "--max-budget-usd", str(self._budget),
            "--permission-mode", "acceptEdits",
        ]
        argv += ["--resume", session_id] if resume else ["--session-id", session_id]

        text = contract or self._contract
        if text:
            argv += ["--append-system-prompt", text]

        # A read-only phase gets a read-only toolset instead of a promise in the
        # prompt. "Do not modify files" is a request; withholding Edit is a fact.
        # Variadic flag, so it stays last and the prompt goes on stdin.
        if read_only:
            argv += ["--tools", "Read", "Grep", "Glob", "Bash", "Skill", "WebFetch"]

        if self._dry_run:
            return Result(True, {"dry_run": True, "argv": argv[1:]}, 0.0, "dry-run", session_id)

        done = subprocess.run(
            argv, input=prompt, cwd=cwd, capture_output=True, text=True, timeout=self._timeout,
        )
        return _parse(done, session_id)


def _parse(done: subprocess.CompletedProcess[str], session_id: str) -> Result:
    if not done.stdout.strip():
        return Result(False, {}, 0.0, f"no output (exit {done.returncode}): "
                                      f"{done.stderr.strip()[:400]}", session_id)
    try:
        payload = json.loads(done.stdout)
    except json.JSONDecodeError:
        return Result(False, {}, 0.0, f"unparsable output: {done.stdout[:400]}", session_id)

    cost = float(payload.get("total_cost_usd") or 0.0)
    denials = tuple(
        str(entry.get("tool_name", entry)) for entry in payload.get("permission_denials") or ()
    )
    verdict = payload.get("structured_output")

    # An exit code of zero with no structured output means the run ended without
    # answering the schema - budget exhausted, or a refusal. Treating it as a
    # success is how a bot asks for review on an empty branch.
    if payload.get("is_error") or verdict is None:
        detail = payload.get("subtype") or payload.get("terminal_reason") or "no structured output"
        return Result(False, verdict or {}, cost, str(detail), session_id,
                      int(payload.get("num_turns") or 0), denials)

    return Result(True, verdict, cost, payload.get("terminal_reason") or "completed",
                  payload.get("session_id") or session_id,
                  int(payload.get("num_turns") or 0), denials)
