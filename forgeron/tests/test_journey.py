from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest

from forgeron import cli

RUNS = [
    {"ts": "2026-10-15T10:00:00Z", "event": "run", "key": "o__r__7", "phase": "planning", "ok": True,
     "cost_usd": 0.5, "skills": ["cycle-de-dev", "cadrer-et-planifier"], "subagent_skills": [],
     "compactions": 0},
    {"ts": "2026-10-15T10:01:00Z", "event": "drafted", "key": "o__r__7", "pr": 9},
    {"ts": "2026-10-15T10:02:00Z", "event": "run", "key": "o__r__8", "phase": "planning", "ok": True,
     "cost_usd": 4.0, "skills": [], "compactions": 0},
    {"ts": "2026-10-15T10:20:00Z", "event": "run", "key": "o__r__7", "phase": "implementing", "ok": True,
     "cost_usd": 0.75, "skills": None, "subagent_skills": None, "compactions": None},
    {"ts": "2026-10-15T11:00:00Z", "event": "run", "key": "o__r__7", "phase": "revising", "ok": True,
     "cost_usd": 0.25, "skills": ["trouver-la-cause"], "subagent_skills": ["relire-une-pr"],
     "compactions": 1, "remarks": 2},
]

FAILED_RUN = {"ts": "2026-10-15T12:00:00Z", "event": "run", "key": "o__r__7", "phase": "fixing_checks",
              "ok": False, "detail": "no output (exit 1)", "cost_usd": 0.0, "skills": None,
              "subagent_skills": None, "compactions": None}


class TheJourneyOfAnIssue(unittest.TestCase):
    def setUp(self) -> None:
        self.home = tempfile.mkdtemp()
        self.config = os.path.join(self.home, "config.json")
        with open(self.config, "w", encoding="utf-8") as handle:
            json.dump({"home": self.home}, handle)

    def write_journal(self, events: list[dict]) -> None:
        with open(os.path.join(self.home, "journal.jsonl"), "w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event) + "\n")

    def journey(self, *flags: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--config", self.config, *flags, "journey", "o/r", "7"])
        return code, out.getvalue(), err.getvalue()

    def test_the_runs_of_the_issue_are_printed_in_order_with_their_total(self) -> None:
        self.write_journal(RUNS)
        code, out, _ = self.journey()
        self.assertEqual(code, cli.EXIT_OK)
        lines = out.splitlines()
        self.assertEqual([line.split()[1] for line in lines[:3]], ["planning", "implementing", "revising"])
        self.assertIn("cycle-de-dev, cadrer-et-planifier", lines[0])
        self.assertIn("0.50 USD", lines[0])
        self.assertIn("compactions 0", lines[0])
        self.assertIn("remarks 2", lines[2])
        self.assertIn("0.75 USD", lines[1])
        self.assertIn("subagents relire-une-pr", lines[2])
        self.assertIn("total 1.50 USD over 3 runs", lines[3])

    def test_skills_that_were_not_read_are_said_so_rather_than_shown_empty(self) -> None:
        self.write_journal(RUNS)
        _, out, _ = self.journey()
        self.assertIn("skills not read", out.splitlines()[1])

    def test_a_failed_run_says_it_failed_and_why(self) -> None:
        self.write_journal([*RUNS, FAILED_RUN])
        _, out, _ = self.journey()
        self.assertIn("FAILED: no output (exit 1)", out.splitlines()[3])
        self.assertNotIn("FAILED", out.splitlines()[0])

    def test_the_machine_output_is_the_runs_of_the_issue_and_nothing_else(self) -> None:
        self.write_journal(RUNS)
        code, out, _ = self.journey("--json")
        self.assertEqual(code, cli.EXIT_OK)
        runs = json.loads(out)
        self.assertEqual([run["phase"] for run in runs], ["planning", "implementing", "revising"])
        self.assertEqual({run["key"] for run in runs}, {"o__r__7"})

    def test_a_missing_journal_names_where_it_looked(self) -> None:
        code, _, err = self.journey()
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn(os.path.join(self.home, "journal.jsonl"), err)


if __name__ == "__main__":
    unittest.main()
