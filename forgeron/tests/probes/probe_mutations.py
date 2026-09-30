#!/usr/bin/env python3
"""Break each rule on purpose and check the suite notices.

A suite that is green on its first run has proved nothing: it may assert on things
that cannot vary. So each mutation below removes exactly one rule, runs the suite,
and the probe FAILS if the suite still passes. Every source file is restored
whatever happens, including on a crash.

Run from the forgeron/ directory:  python3 tests/probes/probe_mutations.py
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

IN_REVIEW_BLOCK = (
    "        conflict = _conflict_decision(record, obs, limits)\n"
    "        if conflict is not None:\n"
    "            return conflict\n"
    "        if obs.merge_state.needs_sync:\n"
    "            return Decision(Action.SYNC_BRANCH, Phase.IN_REVIEW,\n"
    '                            "base moved while in review, updating the branch")'
)

RESOLVED_OK = (
    '        return record.with_(phase=Phase.IMPLEMENTED, checks_since="",\n'
    '                            note=f"conflict resolved by {method.lower()}")'
)
RESOLVED_MUTANT = RESOLVED_OK.replace("Phase.IMPLEMENTED", "Phase.IN_REVIEW")

# (name, file, text to find, replacement) - each one removes a single guarantee.
MUTATIONS = [
    ("an empty rollup means no CI (grace period removed)",
     "forgeron/engine.py",
     "            if waited < self._config.checks_grace_seconds:",
     "            if False:"),

    ("a closed issue is an abandonment, even when merged",
     "forgeron/states.py",
     "    if not obs.issue_open and not obs.merged:",
     "    if not obs.issue_open:"),

    ("the agent's verdict is taken at its word",
     "forgeron/engine.py",
     "        if not self._workspace.is_synced(record.worktree, record.branch):",
     "        if False:"),

    ("remarks already handled are not remembered",
     "forgeron/engine.py",
     "            seen_feedback=record.seen_feedback + tuple(item.ident for item in feedback),",
     "            seen_feedback=record.seen_feedback,"),

    ("CI is not awaited before review",
     "forgeron/states.py",
     "        return Decision(Action.WAIT_CHECKS, Phase.AWAITING_CHECKS, \"work pushed, checking CI\")",
     "        return Decision(Action.REQUEST_REVIEW, Phase.IN_REVIEW, \"work pushed\")"),

    ("the plan's questions are ignored",
     "forgeron/states.py",
     "    return Phase.AWAITING_ANSWER if questions else Phase.DRAFTED",
     "    return Phase.DRAFTED"),

    ("a human no longer outranks red CI",
     "forgeron/states.py",
     """        if obs.new_feedback:
            return Decision(Action.REVISE, Phase.REVISING,
                            f"{len(obs.new_feedback)} item(s) of feedback while waiting for CI")""",
     "        if False:\n            pass"),

    ("the pause label stops nothing",
     "forgeron/states.py",
     "    if obs.held:",
     "    if False:"),

    ("rebasing even under a reviewer's eyes",
     "forgeron/states.py",
     '    already_reviewed = obs.pr is not None and obs.pr.reviewed',
     "    already_reviewed = False"),

    ("the conflict resolution is taken at its word",
     "forgeron/engine.py",
     "        remaining = self._workspace.conflicted(record.worktree)",
     "        remaining = []"),

    ("a human no longer outranks a conflict",
     "forgeron/states.py",
     IN_REVIEW_BLOCK,
     "        pass"),

    ("a conflict resolution does not ask for review again",
     "forgeron/engine.py",
     RESOLVED_OK,
     RESOLVED_MUTANT),

    ("the file is not set aside before running again",
     "forgeron/regenerator.py",
     "        os.replace(target, aside)\n        try:",
     "        import shutil; shutil.copy2(target, aside)\n        try:"),

    ("the verifier's verdict is ignored",
     "forgeron/engine.py",
     "            if outcome.ok:",
     "            if True:"),

    ("a visual can leave the worktree",
     "forgeron/regenerator.py",
     "        if os.path.commonpath([root, target]) != root:",
     "        if False:"),

    ("the visuals ceiling is removed",
     "forgeron/engine.py",
     "        for entry in declared[:MAX_VISUALS]:",
     "        for entry in declared:"),

    ("the attribution check is removed",
     "forgeron/engine.py",
     "        if tainted:",
     "        if False:"),

    ("the filter also takes away a human co-author",
     "forgeron/attribution.py",
     r'    r"^\s*co-authored-by:.*(claude|anthropic)",',
     r'    r"^\s*co-authored-by:",'),

    ("the agent's prose is no longer scrubbed",
     "forgeron/engine.py",
     '        attribution.strip(verdict.get("summary", "")).strip(),\n        "",\n        answers,',
     '        verdict.get("summary", "").strip(),\n        "",\n        answers,'),

    ("the CI fixes ceiling is removed",
     "forgeron/states.py",
     "            if record.check_fixes >= limits.max_check_fixes:",
     "            if False:"),

    ("the agent is no longer passed to claude",
     "forgeron/claude_agent.py",
     '        if self._agent:\n            argv += ["--agent", self._agent]\n',
     '        if False:\n            argv += ["--agent", self._agent]\n'),

    ("the agent comes after the variadic --tools option",
     "forgeron/claude_agent.py",
     '        if self._agent:\n            argv += ["--agent", self._agent]\n\n'
     '        text = contract or self._contract\n'
     '        if text:\n            argv += ["--append-system-prompt", text]\n\n'
     '        if read_only:\n'
     '            argv += ["--tools", "Read", "Grep", "Glob", "Bash", "Skill", "WebFetch"]\n',
     '        text = contract or self._contract\n'
     '        if text:\n            argv += ["--append-system-prompt", text]\n\n'
     '        if read_only:\n'
     '            argv += ["--tools", "Read", "Grep", "Glob", "Bash", "Skill", "WebFetch"]\n'
     '        if self._agent:\n            argv += ["--agent", self._agent]\n'),
]


def run_suite() -> tuple[bool, str]:
    done = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-q"],
        cwd=ROOT, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "."},
    )
    return done.returncode == 0, (done.stderr or done.stdout).strip().splitlines()[-1:][0] \
        if (done.stderr or done.stdout).strip() else ""


def main() -> int:
    baseline_ok, baseline_line = run_suite()
    print(f"baseline           : {'GREEN' if baseline_ok else 'RED'}  {baseline_line}")
    if not baseline_ok:
        print("the suite must be green before it is probed", file=sys.stderr)
        return 1

    undetected: list[str] = []
    for name, relative, needle, replacement in MUTATIONS:
        path = ROOT / relative
        original = path.read_text(encoding="utf-8")
        if needle not in original:
            print(f"IMPOSSIBLE         : {name} — pattern missing from {relative}")
            undetected.append(f"{name} (pattern missing)")
            continue
        try:
            path.write_text(original.replace(needle, replacement, 1), encoding="utf-8")
            caught, line = run_suite()
            caught = not caught
        finally:
            path.write_text(original, encoding="utf-8")
        print(f"{'DETECTED' if caught else 'MISSED   '}          : {name}")
        if not caught:
            undetected.append(name)

    restored_ok, _ = run_suite()
    print(f"\nrestored           : {'GREEN' if restored_ok else 'RED'}")
    if not restored_ok:
        print("the sources were not restored correctly", file=sys.stderr)
        return 1
    if undetected:
        print(f"\n{len(undetected)} mutation(s) not detected — the suite does not cover them:")
        for name in undetected:
            print(f"  - {name}")
        return 1
    print(f"\n{len(MUTATIONS)}/{len(MUTATIONS)} mutations detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
