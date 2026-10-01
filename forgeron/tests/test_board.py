from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import unittest
from unittest import mock

from forgeron import cli
from forgeron.board import OPTIONS, BoardError, GhBoard, option_for
from forgeron.config import BoardConfig, load
from forgeron.model import Phase

LISTING = {"data": {"repositoryOwner": {"projectsV2": {
    "nodes": [{"id": "PVT_7", "title": "Laplace"}, {"id": "PVT_3", "title": "TODO"}],
    "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}


def single_select(prefix: str, name: str, options: tuple[str, ...] = OPTIONS) -> dict:
    return {"id": f"PVTSSF_{prefix}", "name": name,
            "options": [{"id": f"{prefix}{index}", "name": option} for index, option in enumerate(options)]}


def fields(*nodes: dict) -> dict:
    return {"data": {"node": {"fields": {"nodes": list(nodes)}}}}


FIELDS = fields(
    single_select("status", "Status", ("Ready",)),
    single_select("forgeron", "Forgeron"),
    single_select("phase", "Phase"),
    {},
)


def page(titles: list[str], cursor: str | None) -> dict:
    return {"data": {"repositoryOwner": {"projectsV2": {
        "nodes": [{"id": f"PVT_{title}_{index}", "title": title} for index, title in enumerate(titles)],
        "pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor}}}}}


class Forge:
    def __init__(self, listing: dict | None = None, pages: dict | None = None,
                 field_reads: list[dict] | None = None) -> None:
        self.listing = listing or LISTING
        self.pages = pages
        self.field_reads = field_reads or [FIELDS]
        self.calls: list[dict] = []

    def __call__(self, argv: list[str], stdin: str | None) -> tuple[int, str, str]:
        body = json.loads(stdin)
        self.calls.append(body)
        query = body["query"]
        if "repositoryOwner" in query:
            if self.pages is not None:
                return 0, json.dumps(self.pages[body["variables"].get("cursor")]), ""
            return 0, json.dumps(self.listing), ""
        if "fields(first" in query:
            answer = self.field_reads[min(self.reads("fields(first") - 1, len(self.field_reads) - 1)]
            return 0, json.dumps(answer), ""
        if "issueOrPullRequest" in query:
            number = body["variables"]["number"]
            return 0, json.dumps({"data": {"repository": {"issueOrPullRequest": {"id": f"I_{number}"}}}}), ""
        if "addProjectV2ItemById" in query:
            return 0, json.dumps({"data": {"addProjectV2ItemById": {"item": {"id": "PVTI_1"}}}}), ""
        return 0, json.dumps({"data": {"ok": True}}), ""

    def reads(self, marker: str) -> int:
        return sum(marker in call["query"] for call in self.calls if not call["query"].startswith("mutation"))

    def mutations(self) -> list[tuple[str, dict]]:
        return [(re.search(r"\{\s*(\w+)\s*\(", call["query"]).group(1), call["variables"]["input"])
                for call in self.calls if call["query"].startswith("mutation")]


class Mapping(unittest.TestCase):
    def test_every_phase_has_an_option(self) -> None:
        for phase in Phase:
            self.assertIn(option_for(phase), OPTIONS, phase)

    def test_every_option_is_reached_by_a_phase(self) -> None:
        self.assertEqual({option_for(phase) for phase in Phase}, set(OPTIONS))

    def test_a_question_to_the_maintainer_has_its_own_option(self) -> None:
        self.assertEqual(option_for(Phase.AWAITING_ANSWER), "Awaiting answer")
        self.assertEqual(option_for(Phase.FIXING_CHECKS), "Working")
        self.assertEqual(option_for(Phase.REVISING), "In review")
        self.assertEqual(option_for(Phase.ABANDONED), "Done")


class Placing(unittest.TestCase):
    def test_an_issue_is_added_by_its_content_id(self) -> None:
        forge = Forge()
        item = GhBoard("MasterLaplace/Laplace", runner=forge).place("MasterLaplace/LplKernel", 42)
        self.assertEqual(item, "PVTI_1")
        self.assertEqual(forge.mutations(),
                         [("addProjectV2ItemById", {"projectId": "PVT_7", "contentId": "I_42"})])

    def test_the_field_is_set_by_the_name_of_its_option(self) -> None:
        forge = Forge()
        GhBoard("MasterLaplace/Laplace", runner=forge).set_option("PVTI_1", "Working")
        self.assertEqual(forge.mutations(), [("updateProjectV2ItemFieldValue", {
            "projectId": "PVT_7", "itemId": "PVTI_1", "fieldId": "PVTSSF_forgeron",
            "value": {"singleSelectOptionId": f"forgeron{OPTIONS.index('Working')}"}})])

    def test_the_configured_field_is_the_one_written(self) -> None:
        forge = Forge()
        GhBoard("MasterLaplace/Laplace", field="Phase", runner=forge).set_option("PVTI_1", "Working")
        self.assertEqual(forge.mutations()[0][1]["fieldId"], "PVTSSF_phase")

    def test_an_option_the_field_lacks_is_an_error_that_names_it(self) -> None:
        with self.assertRaises(BoardError) as caught:
            GhBoard("MasterLaplace/Laplace", field="Status", runner=Forge()).set_option("PVTI_1", "Working")
        self.assertIn("Working", str(caught.exception))
        self.assertIn("Status", str(caught.exception))

    def test_a_field_the_project_lacks_is_an_error(self) -> None:
        forge = Forge()
        with self.assertRaises(BoardError) as caught:
            GhBoard("MasterLaplace/Laplace", field="Size", runner=forge).set_option("PVTI_1", "Working")
        self.assertIn("Size", str(caught.exception))
        self.assertEqual(forge.mutations(), [])

    def test_a_project_the_owner_lacks_is_an_error(self) -> None:
        with self.assertRaises(BoardError) as caught:
            GhBoard("MasterLaplace/Missing", runner=Forge()).place("MasterLaplace/LplKernel", 42)
        self.assertIn("Missing", str(caught.exception))

    def test_an_owner_that_does_not_exist_is_named(self) -> None:
        forge = Forge(listing={"data": {"repositoryOwner": None}})
        with self.assertRaises(BoardError) as caught:
            GhBoard("Nobody/Laplace", runner=forge).place("MasterLaplace/LplKernel", 42)
        self.assertIn("Nobody: no such user or organization", str(caught.exception))

    def test_projects_are_read_past_the_first_page(self) -> None:
        forge = Forge(pages={None: page(["TODO"], "c1"), "c1": page(["Laplace"], None)})
        GhBoard("MasterLaplace/Laplace", runner=forge).place("MasterLaplace/LplKernel", 42)
        self.assertEqual(forge.mutations()[0][1]["projectId"], "PVT_Laplace_0")

    def test_two_projects_with_one_title_are_refused(self) -> None:
        forge = Forge(pages={None: page(["Laplace"], "c1"), "c1": page(["Laplace"], None)})
        with self.assertRaises(BoardError) as caught:
            GhBoard("MasterLaplace/Laplace", runner=forge).place("MasterLaplace/LplKernel", 42)
        self.assertIn("2 projects titled", str(caught.exception))
        self.assertEqual(forge.mutations(), [])

    def test_the_project_and_its_fields_are_read_once(self) -> None:
        forge = Forge()
        board = GhBoard("MasterLaplace/Laplace", runner=forge)
        for option in ("Queued", "Planning", "Working"):
            board.set_option(board.place("MasterLaplace/LplKernel", 42), option)
        self.assertEqual(forge.reads("repositoryOwner"), 1)
        self.assertEqual(forge.reads("fields(first"), 1)

    def test_a_field_created_while_forgeron_runs_is_found_at_the_next_write(self) -> None:
        forge = Forge(field_reads=[fields(single_select("status", "Status", ("Ready",))), FIELDS])
        board = GhBoard("MasterLaplace/Laplace", runner=forge)
        with self.assertRaises(BoardError):
            board.set_option("PVTI_1", "Working")
        board.set_option("PVTI_1", "Working")
        self.assertEqual(forge.reads("fields(first"), 2)
        self.assertEqual(forge.mutations()[0][1]["fieldId"], "PVTSSF_forgeron")

    def test_an_option_added_while_forgeron_runs_is_found_at_the_next_write(self) -> None:
        early = fields(single_select("forgeron", "Forgeron", ("Queued",)))
        forge = Forge(field_reads=[early, FIELDS])
        board = GhBoard("MasterLaplace/Laplace", runner=forge)
        board.set_option("PVTI_1", "Queued")
        board.set_option("PVTI_1", "Done")
        self.assertEqual([change["value"]["singleSelectOptionId"] for _, change in forge.mutations()],
                         ["forgeron0", f"forgeron{OPTIONS.index('Done')}"])

    def test_a_graphql_error_is_a_board_error(self) -> None:
        def refusing(argv, stdin):
            return 0, json.dumps({"errors": [{"message": "Resource not accessible"}]}), ""
        with self.assertRaises(BoardError) as caught:
            GhBoard("MasterLaplace/Laplace", runner=refusing).place("MasterLaplace/LplKernel", 42)
        self.assertIn("Resource not accessible", str(caught.exception))

    def test_the_options_the_field_lacks_are_named(self) -> None:
        partial = fields(single_select("forgeron", "Forgeron", ("Queued", "Working")))
        board = GhBoard("MasterLaplace/Laplace", runner=Forge(field_reads=[partial]))
        self.assertEqual(board.missing_options(),
                         ("Planning", "Awaiting answer", "In review", "Blocked", "Done"))
        self.assertEqual(GhBoard("MasterLaplace/Laplace", runner=Forge()).missing_options(), ())


class Configuration(unittest.TestCase):
    def write(self, raw: dict) -> str:
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(raw, handle)
        handle.close()
        self.addCleanup(os.remove, handle.name)
        return handle.name

    def test_a_board_is_read_with_its_default_field(self) -> None:
        config = load(self.write({"board": {"project": "MasterLaplace/Laplace"}}))
        self.assertEqual(config.board, BoardConfig(project="MasterLaplace/Laplace", field="Forgeron"))

    def test_without_a_board_there_is_none(self) -> None:
        self.assertIsNone(load(self.write({})).board)

    def test_an_unknown_board_key_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            load(self.write({"board": {"project": "MasterLaplace/Laplace", "colour": "red"}}))
        self.assertIn("colour", str(caught.exception))

    def test_a_project_is_named_owner_slash_title(self) -> None:
        with self.assertRaises(ValueError) as caught:
            load(self.write({"board": {"project": "Laplace"}}))
        self.assertIn("OWNER/TITLE", str(caught.exception))

    def test_an_empty_field_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            load(self.write({"board": {"project": "MasterLaplace/Laplace", "field": " "}}))
        self.assertIn("board.field", str(caught.exception))

    def test_the_board_is_printed_with_the_rest_of_the_configuration(self) -> None:
        config = load(self.write({"board": {"project": "MasterLaplace/Laplace"}}))
        self.assertEqual(config.to_dict()["board"], {"project": "MasterLaplace/Laplace", "field": "Forgeron"})


class Wiring(unittest.TestCase):
    def build(self, raw: dict):
        home = tempfile.mkdtemp()
        path = os.path.join(home, "config.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"home": home, **raw}, handle)
        with mock.patch("forgeron.cli.Engine") as engine:
            cli._build(argparse.Namespace(config=path, write=False, verbose=False))
        return engine.call_args.kwargs["board"]

    def test_the_engine_is_built_with_the_configured_board(self) -> None:
        board = self.build({"board": {"project": "MasterLaplace/Laplace", "field": "Phase"}})
        self.assertIsInstance(board, GhBoard)
        self.assertEqual((board.project, board.field), ("MasterLaplace/Laplace", "Phase"))

    def test_without_a_board_the_engine_has_none(self) -> None:
        self.assertIsNone(self.build({}))


class Doctor(unittest.TestCase):
    def test_a_board_needs_the_project_scope(self) -> None:
        board = BoardConfig(project="MasterLaplace/Laplace")
        ok, detail = cli._board_scope(board, "'repo', 'read:org'")
        self.assertFalse(ok)
        self.assertIn("gh auth refresh -s project", detail)
        self.assertTrue(cli._board_scope(board, "'project', 'repo'")[0])

    def test_reading_projects_is_not_writing_them(self) -> None:
        board = BoardConfig(project="MasterLaplace/Laplace")
        self.assertFalse(cli._board_scope(board, "'read:project', 'repo'")[0])

    def test_no_board_needs_no_scope(self) -> None:
        self.assertIsNone(cli._board_scope(None, ""))

    def test_the_field_is_checked_against_the_seven_options(self) -> None:
        partial = fields(single_select("forgeron", "Forgeron", ("Queued",)))
        ok, detail = cli._board_field(GhBoard("MasterLaplace/Laplace", runner=Forge(field_reads=[partial])))
        self.assertFalse(ok)
        self.assertIn("Done", detail)
        self.assertTrue(cli._board_field(GhBoard("MasterLaplace/Laplace", runner=Forge()))[0])

    def test_a_field_the_project_lacks_is_reported(self) -> None:
        ok, detail = cli._board_field(GhBoard("MasterLaplace/Laplace", field="Size", runner=Forge()))
        self.assertFalse(ok)
        self.assertIn("Size", detail)


if __name__ == "__main__":
    unittest.main()
