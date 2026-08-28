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
    '                            note=f"conflit resolu par {method.lower()}")'
)
RESOLVED_MUTANT = RESOLVED_OK.replace("Phase.IMPLEMENTED", "Phase.IN_REVIEW")

# (name, file, text to find, replacement) - each one removes a single guarantee.
MUTATIONS = [
    ("un rollup vide vaut absence de CI (grace supprimee)",
     "forgeron/engine.py",
     "            if waited < self._config.checks_grace_seconds:",
     "            if False:"),

    ("une issue fermee est un abandon, meme fusionnee",
     "forgeron/states.py",
     "    if not obs.issue_open and not obs.merged:",
     "    if not obs.issue_open:"),

    ("le verdict de l'agent est cru sur parole",
     "forgeron/engine.py",
     "        if not self._workspace.is_synced(record.worktree, record.branch):",
     "        if False:"),

    ("les remarques deja traitees ne sont pas memorisees",
     "forgeron/engine.py",
     "            seen_feedback=record.seen_feedback + tuple(item.ident for item in feedback),",
     "            seen_feedback=record.seen_feedback,"),

    ("la CI n'est pas attendue avant la revue",
     "forgeron/states.py",
     "        return Decision(Action.WAIT_CHECKS, Phase.AWAITING_CHECKS, \"work pushed, checking CI\")",
     "        return Decision(Action.REQUEST_REVIEW, Phase.IN_REVIEW, \"work pushed\")"),

    ("les questions du plan sont ignorees",
     "forgeron/states.py",
     "    return Phase.AWAITING_ANSWER if questions else Phase.DRAFTED",
     "    return Phase.DRAFTED"),

    ("un humain ne passe plus avant la CI rouge",
     "forgeron/states.py",
     """        if obs.new_feedback:
            return Decision(Action.REVISE, Phase.REVISING,
                            f"{len(obs.new_feedback)} item(s) of feedback while waiting for CI")""",
     "        if False:\n            pass"),

    ("l'etiquette de pause n'arrete rien",
     "forgeron/states.py",
     "    if obs.held:",
     "    if False:"),

    ("on rebase meme sous les yeux d'un relecteur",
     "forgeron/states.py",
     '    already_reviewed = obs.pr is not None and obs.pr.reviewed',
     "    already_reviewed = False"),

    ("la resolution de conflit est crue sur parole",
     "forgeron/engine.py",
     "        remaining = self._workspace.conflicted(record.worktree)",
     "        remaining = []"),

    ("un humain ne passe plus avant un conflit",
     "forgeron/states.py",
     IN_REVIEW_BLOCK,
     "        pass"),

    ("une resolution de conflit ne redemande pas de revue",
     "forgeron/engine.py",
     RESOLVED_OK,
     RESOLVED_MUTANT),

    ("le plafond de correctifs CI est retire",
     "forgeron/states.py",
     "            if record.check_fixes >= limits.max_check_fixes:",
     "            if False:"),
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
    print(f"baseline           : {'VERTE' if baseline_ok else 'ROUGE'}  {baseline_line}")
    if not baseline_ok:
        print("la suite doit etre verte avant de la sonder", file=sys.stderr)
        return 1

    undetected: list[str] = []
    for name, relative, needle, replacement in MUTATIONS:
        path = ROOT / relative
        original = path.read_text(encoding="utf-8")
        if needle not in original:
            print(f"IMPOSSIBLE         : {name} — motif absent de {relative}")
            undetected.append(f"{name} (motif absent)")
            continue
        try:
            path.write_text(original.replace(needle, replacement, 1), encoding="utf-8")
            caught, line = run_suite()
            caught = not caught
        finally:
            path.write_text(original, encoding="utf-8")
        print(f"{'DETECTEE' if caught else 'PASSEE   '}          : {name}")
        if not caught:
            undetected.append(name)

    restored_ok, _ = run_suite()
    print(f"\nrestauree          : {'VERTE' if restored_ok else 'ROUGE'}")
    if not restored_ok:
        print("les sources n'ont pas ete restaurees correctement", file=sys.stderr)
        return 1
    if undetected:
        print(f"\n{len(undetected)} mutation(s) non detectee(s) — la suite ne les couvre pas :")
        for name in undetected:
            print(f"  - {name}")
        return 1
    print(f"\n{len(MUTATIONS)}/{len(MUTATIONS)} mutations detectees")
    return 0


if __name__ == "__main__":
    sys.exit(main())
