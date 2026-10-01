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

    ("etabli: a label items still carry is deleted",
     "forgeron/etabli.py",
     '        if desired.unlisted_labels == "delete-unused" and current.uses == 0 and not observed.discussions:',
     '        if desired.unlisted_labels == "delete-unused" and not observed.discussions:'),

    ("etabli: a rename overwrites a label that already exists",
     "forgeron/etabli.py",
     "        if new.lower() in present:",
     "        if False:"),

    ("etabli: an unreadable security state reads as off",
     "forgeron/etabli.py",
     "        if have is None:",
     "        if False:"),

    ("etabli: removing a protection goes through the tool",
     "forgeron/etabli.py",
     "        elif have and not want:",
     "        elif False:"),

    ("etabli: a ruleset's bypass list no longer counts",
     "forgeron/etabli.py",
     "    if wanted_bypass != present_bypass:",
     "    if False:"),

    ("etabli: labels are attempted without write access",
     "forgeron/etabli.py",
     "    if not observed.push:",
     "    if False:"),

    ("etabli: --write does not read the repository again",
     "forgeron/cli.py",
     "                remaining = observe_and_plan()",
     "                remaining = []"),

    ("etabli: a write leaves no trace",
     "forgeron/cli.py",
     '                    journal.emit("etabli_applied", key=change.repo, **_journal_fields(change))',
     "                    pass"),

    ("etabli: a label name goes into the URL unencoded",
     "forgeron/gh_etabli.py",
     '    return urllib.parse.quote(name, safe="")',
     "    return name"),

    ("etabli: half of a commit message pair goes out alone",
     "forgeron/etabli.py",
     "            differing |= {key for key in pair if key in desired.settings}",
     "            pass"),

    ("etabli: delete-unused ignores that discussions carry labels",
     "forgeron/etabli.py",
     '        if desired.unlisted_labels == "delete-unused" and current.uses == 0 and not observed.discussions:',
     '        if desired.unlisted_labels == "delete-unused" and current.uses == 0:'),

    ("etabli: a ruleset update drops forge-only parameters silently",
     "forgeron/etabli.py",
     '        weaker = ruleset_weakening(want, have) + [f"the PUT would drop {path}" for path in kept]',
     "        weaker = ruleset_weakening(want, have)"),

    ("etabli: the tool weakens a ruleset",
     "forgeron/etabli.py",
     "        if differences and weaker:",
     "        if False:"),

    ("etabli: a gh timeout escapes as a traceback",
     "forgeron/gh_etabli.py",
     "        except subprocess.TimeoutExpired:",
     "        except ZeroDivisionError:"),

    ("etabli: a failed second read passes the old plan off as what is left",
     "forgeron/cli.py",
     "                remaining = None",
     "                pass"),

    ("etabli: nothing checked exits 0",
     "forgeron/cli.py",
     '            or any(not entry["checked"] for entry in report):',
     "            or False:"),

    ("etabli: removing an option clears items through the tool",
     "forgeron/etabli_projects.py",
     "    if removed and items:",
     "    if False:"),

    ("etabli: an option of a project without items cannot be removed",
     "forgeron/etabli_projects.py",
     "    if removed and items:",
     "    if removed:"),

    ("etabli: a field of another type is rewritten",
     "forgeron/etabli_projects.py",
     "        elif have.type != FIELD_TYPES[field.type]:",
     "        elif False:"),

    ("etabli: a workflow wanted off is never checked",
     "forgeron/etabli_projects.py",
     "        elif enabled and not wanted:",
     "        elif False:"),

    ("etabli: a sort change goes in place, which the API cannot do",
     "forgeron/etabli_projects.py",
     '"rebuild": bool(moved)}',
     '"rebuild": False}'),

    ("etabli: a project the viewer cannot update is written to",
     "forgeron/etabli_projects.py",
     "    if not observed.can_update:",
     "    if False:"),

    ("etabli: a project can link a repository of another owner",
     "forgeron/etabli_projects.py",
     "        if other.lower() != owner.lower():",
     "        if False:"),

    ("etabli: a project created by the run is left empty",
     "forgeron/cli.py",
     "            if created and not failed and catch_up and not any(map(_creates_project, remaining)):",
     "            if False:"),

    ("etabli: a half-read project passes as a whole one",
     "forgeron/gh_etabli.py",
     '            if ((node.get(block) or {}).get("pageInfo") or {}).get("hasNextPage"):',
     "            if False:"),

    ("etabli: a project the forge does not show yet gets writes meant for it",
     "forgeron/cli.py",
     "            if created and not failed and catch_up and not any(map(_creates_project, remaining)):",
     "            if created and not failed and catch_up:"),

    ("etabli: a rebuilt view is deleted before its replacement exists",
     "forgeron/gh_etabli.py",
     "            self._create_view(state, _carried(change.before, change.after))\n"
     "            self._mutate(\"deleteProjectV2View\", {\"viewId\": change.before[\"id\"]})",
     "            self._mutate(\"deleteProjectV2View\", {\"viewId\": change.before[\"id\"]})\n"
     "            self._create_view(state, _carried(change.before, change.after))"),

    ("etabli: a rebuilt view forgets what the declaration does not say",
     "forgeron/gh_etabli.py",
     "            self._create_view(state, _carried(change.before, change.after))",
     "            self._create_view(state, change.after)"),

    ("etabli: a README outside the configuration folder is published",
     "forgeron/etabli_projects.py",
     '    if parts.is_absolute() or ".." in parts.parts or re.match(r"^[A-Za-z]:", value):',
     "    if False:"),

    ("etabli: of two projects with the same title, the first one wins",
     "forgeron/gh_etabli.py",
     "        if len(found) > 1:",
     "        if False:"),

    ("etabli: archived items do not count against removing an option",
     "forgeron/gh_etabli.py",
     "items(archivedStates: [ARCHIVED, NOT_ARCHIVED])",
     "items"),

    ("etabli: a selection that leaves nothing exits green",
     "forgeron/cli.py",
     "        if not desired and not projects:",
     "        if False:"),

    ("board: a board that fails stops the work",
     "forgeron/engine.py",
     "        except Exception as failure:\n            self._journal.emit(\"board_failed\"",
     "        except ZeroDivisionError as failure:\n            self._journal.emit(\"board_failed\""),

    ("board: every save writes the option again",
     "forgeron/engine.py",
     "        shown = self._shown.get((record.repo, record.issue)) == option",
     "        shown = False"),

    ("board: a refused write counts as shown",
     "forgeron/engine.py",
     "            return False\n        self._shown[(record.repo, number)] = option",
     "            pass\n        self._shown[(record.repo, number)] = option"),

    ("board: the pull request is left off the board",
     "forgeron/engine.py",
     "        if record.pr and in_review and (record.repo, record.pr) not in self._shown:",
     "        if False:"),

    ("board: a draft pull request goes on the board",
     "forgeron/engine.py",
     "        in_review = option == option_for(Phase.IN_REVIEW)",
     "        in_review = True"),

    ("board: the pull request gets an option of its own",
     "forgeron/engine.py",
     "            if option:\n                self._board.set_option(item, option)",
     "            if True:\n                self._board.set_option(item, option)"),

    ("board: a phase waiting for a human is never caught up",
     "forgeron/engine.py",
     "            self._show(record)\n            return decision",
     "            return decision"),

    ("board: a refused Done is never written",
     "forgeron/engine.py",
     "                if (record.repo, record.issue) in self._owed:",
     "                if False:"),

    ("board: a new process writes every finished issue again",
     "forgeron/engine.py",
     "                if (record.repo, record.issue) in self._owed:",
     "                if True:"),

    ("board: a dry run writes on the board",
     "forgeron/engine.py",
     "        if self._board is None or self._dry_run:",
     "        if self._board is None:"),

    ("board: an option the field lacks is sent anyway",
     "forgeron/board.py",
     "        if option not in options:",
     "        if False:"),

    ("board: a field read once is never read again",
     "forgeron/board.py",
     "        if known is None or option not in known[1]:",
     "        if not self._fields:"),

    ("board: only the first page of projects is read",
     "forgeron/board.py",
     "            if not page.get(\"hasNextPage\"):",
     "            if True:"),

    ("board: of two projects with one title, the first wins",
     "forgeron/board.py",
     "        if len(found) != 1:",
     "        if not found:"),

    ("board: a question to the maintainer reads as work in progress",
     "forgeron/board.py",
     '    Phase.AWAITING_ANSWER: "Awaiting answer",',
     '    Phase.AWAITING_ANSWER: "Working",'),

    ("board: a pull request in review reads as work in progress",
     "forgeron/board.py",
     '    Phase.IN_REVIEW: "In review",',
     '    Phase.IN_REVIEW: "Working",'),

    ("board: a merged issue reads as work in progress",
     "forgeron/board.py",
     '    Phase.DONE: "Done",',
     '    Phase.DONE: "Working",'),

    ("board: an empty field name passes the loader",
     "forgeron/config.py",
     "    if not isinstance(field, str) or not field.strip():",
     "    if not isinstance(field, str):"),

    ("board: the engine is built without its board",
     "forgeron/cli.py",
     "regenerator=ShellRegenerator(), board=_board(configuration))",
     "regenerator=ShellRegenerator(), board=None)"),

    ("board: the configured field is ignored",
     "forgeron/cli.py",
     "    return GhBoard(configuration.board.project, configuration.board.field)",
     "    return GhBoard(configuration.board.project)"),

    ("board: doctor takes read:project for project",
     "forgeron/cli.py",
     "    if \"'project'\" in scopes:",
     "    if \"project\" in scopes:"),

    ("board: doctor accepts a field that lacks options",
     "forgeron/cli.py",
     "    if missing:\n        return False",
     "    if False:\n        return False"),

    ("etabli: a view is created with node ids the REST API refuses",
     "forgeron/gh_etabli.py",
     "        ids = self._field_ids(state, \"database_id\")",
     "        ids = self._field_ids(state, \"id\")"),
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
