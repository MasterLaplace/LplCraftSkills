from __future__ import annotations

import pathlib
import re
import unittest

from forgeron import prompts
from forgeron.model import IssueRef

CYCLE_SKILL = pathlib.Path(__file__).resolve().parents[2] / "skills" / "cycle-de-dev" / "SKILL.md"
SECTION = "## Ce que chaque étape charge"
ISSUE = IssueRef(repo="o/r", number=7, title="t", body="b", url="https://example.invalid/7")


def cycle_table_rows() -> list[str]:
    text = CYCLE_SKILL.read_text(encoding="utf-8")
    if f"\n{SECTION}" not in text:
        raise AssertionError(f"section {SECTION!r} not found in {CYCLE_SKILL}")
    section = text.split(f"\n{SECTION}", 1)[1].split("\n## ", 1)[0]
    rows: list[str] = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        if re.fullmatch(r"\|[\s:|-]+\|", line.strip()):
            rows.pop()
            continue
        rows.append(line.split("|")[1].strip())
    return rows


def row_name(first_cell: str) -> str:
    return re.split(r",| \(", first_cell, maxsplit=1)[0].strip()


def prompt_of_each_phase() -> dict[str, str]:
    return {
        "FRAME": prompts.plan_prompt(ISSUE),
        "IMPLEMENT": prompts.implement_prompt(ISSUE, {"acceptance": []}, ISSUE.url),
        "REVISE": prompts.revise_prompt(ISSUE, (), 1),
        "CLOSE": prompts.wrap_prompt(ISSUE, 7),
    }


class EachPhaseWalksItsRowsOfTheCycle(unittest.TestCase):
    def test_the_tables_of_the_cycle_are_read(self) -> None:
        self.assertTrue(cycle_table_rows(), f"no row read in {CYCLE_SKILL}")

    def test_every_phase_owns_rows_and_every_owner_is_a_phase(self) -> None:
        self.assertEqual(set(prompts.CYCLE_ROWS_BY_PHASE), set(prompt_of_each_phase()))
        for phase, rows in prompts.CYCLE_ROWS_BY_PHASE.items():
            self.assertTrue(rows, f"{phase} owns no row")

    def test_each_cited_row_is_the_name_of_exactly_one_row_of_the_tables(self) -> None:
        names = [row_name(cell) for cell in cycle_table_rows()]
        for phase, rows in prompts.CYCLE_ROWS_BY_PHASE.items():
            for row in rows:
                self.assertEqual(names.count(row), 1, f"{phase} cites {row!r}; the row names are {names}")

    def test_each_phase_prompt_cites_its_own_rows_and_no_other_list(self) -> None:
        prompt_by_phase = prompt_of_each_phase()
        for phase, rows in prompts.CYCLE_ROWS_BY_PHASE.items():
            cited = ", ".join(f'"{row}"' for row in rows)
            self.assertIn(f"this phase owns the rows {cited}:", prompt_by_phase[phase],
                          f"{phase} does not cite exactly its own rows")


if __name__ == "__main__":
    unittest.main()
