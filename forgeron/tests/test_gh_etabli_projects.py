from __future__ import annotations

import json
import pathlib
import re
import unittest

from forgeron.etabli import Change, Kind
from forgeron.etabli_projects import load_projects, plan_project
from forgeron.gh_etabli import PROJECT_QUERY, GhEtabli, GhEtabliError

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
LIST = json.loads((FIXTURES / "project-list.json").read_text(encoding="utf-8"))
PROJECT = json.loads((FIXTURES / "project-laplace.json").read_text(encoding="utf-8"))
KEY = "MasterLaplace/Laplace"


class Forge:
    def __init__(self, project: dict | None = None, listing: dict | list | None = None) -> None:
        self.project = project or PROJECT
        self.listing = listing or LIST
        self.calls: list[tuple[list[str], dict | None]] = []
        self.fail_on = ""
        self.rest_fails = False

    def __call__(self, argv: list[str], stdin: str | None) -> tuple[int, str, str]:
        body = json.loads(stdin) if stdin else None
        self.calls.append((argv, body))
        if argv[:2] == ["api", "graphql"]:
            query = body["query"]
            if self.fail_on and self.fail_on in query:
                return 0, json.dumps({"errors": [{"message": "Resource not accessible"}]}), ""
            if "repositoryOwner" in query:
                pages = self.listing if isinstance(self.listing, list) else [self.listing]
                page = 1 if body["variables"].get("cursor") else 0
                return 0, json.dumps(pages[page]), ""
            if "node(id:" in query:
                return 0, json.dumps(self.project), ""
            if "repository(owner:" in query:
                return 0, json.dumps({"data": {"repository": {"id": "R_plugin"}}}), ""
            if "createProjectV2(" in query:
                created = {"createProjectV2": {"projectV2": {"id": "PVT_new", "number": 8}}}
                return 0, json.dumps({"data": created}), ""
            return 0, json.dumps({"data": {"ok": True}}), ""
        if self.rest_fails:
            return 1, "", "gh: Validation Failed (HTTP 422)"
        return 0, json.dumps({"id": 1, "number": 9}), ""

    def mutations(self) -> list[tuple[str, dict]]:
        return [(re.search(r"\{\s*(\w+)\s*\(", body["query"]).group(1), body["variables"])
                for argv, body in self.calls
                if argv[:2] == ["api", "graphql"] and "mutation" in body["query"]]

    def rest(self) -> list[tuple[list[str], dict | None]]:
        return [(argv, body) for argv, body in self.calls if argv[:2] != ["api", "graphql"]]


def declared():
    return load_projects(str(FIXTURES / "etabli-project-laplace.json"))[0]


def observed(forge: Forge | None = None):
    forge = forge or Forge()
    adapter = GhEtabli(runner=forge)
    return adapter, adapter.observe_project(declared()), forge


def with_project(**changes) -> dict:
    project = json.loads(json.dumps(PROJECT))
    project["data"]["node"].update(changes)
    return project


def listing_with(nodes: list[dict], typename: str = "User", cursor: str = "") -> dict:
    page = json.loads(json.dumps(LIST))
    owner = page["data"]["repositoryOwner"]
    owner["__typename"] = typename
    owner["projectsV2"]["nodes"] = nodes
    owner["projectsV2"]["pageInfo"] = {"hasNextPage": bool(cursor), "endCursor": cursor or None}
    return page


LAPLACE = {"id": PROJECT["data"]["node"]["id"], "number": 7, "title": "Laplace"}


class Observing(unittest.TestCase):
    def test_the_recorded_project_is_read_with_its_fields_views_and_workflows(self) -> None:
        _, state, _ = observed()
        self.assertTrue(state.exists and state.can_update)
        self.assertEqual((state.number, state.owner_type), (7, "User"))
        self.assertGreater(state.items, 0)
        status = next(field for field in state.fields if field.name == "Status")
        self.assertEqual(status.options[0].name, "Ready")
        self.assertEqual(len(status.option_ids), len(status.options))
        nxt = next(view for view in state.views if view["name"] == "Next")
        self.assertEqual((nxt["layout"], nxt["group_by"], nxt["sort_by"]),
                         ("table", ["Repository"], [["Priority", "asc"]]))
        self.assertTrue(state.workflows["Item added to project"])

    def test_the_declared_laplace_project_matches_the_recorded_one(self) -> None:
        _, state, _ = observed()
        self.assertEqual(plan_project(declared(), state), [])

    def test_a_title_the_owner_does_not_have_is_a_project_to_create(self) -> None:
        listing = json.loads(json.dumps(LIST))
        listing["data"]["repositoryOwner"]["projectsV2"]["nodes"] = []
        _, state, _ = observed(Forge(listing=listing))
        self.assertFalse(state.exists)

    def test_an_unknown_owner_is_an_error_not_a_project_to_create(self) -> None:
        with self.assertRaises(GhEtabliError) as caught:
            observed(Forge(listing={"data": {"repositoryOwner": None}}))
        self.assertIn("MasterLaplace", str(caught.exception))

    def test_more_than_one_page_of_views_is_refused_rather_than_half_read(self) -> None:
        project = json.loads(json.dumps(PROJECT))
        project["data"]["node"]["views"]["pageInfo"]["hasNextPage"] = True
        with self.assertRaises(GhEtabliError) as caught:
            observed(Forge(project=project))
        self.assertIn("views", str(caught.exception))

    def test_the_item_count_includes_archived_items(self) -> None:
        self.assertIn("archivedStates: [ARCHIVED, NOT_ARCHIVED]", PROJECT_QUERY)

    def test_the_project_is_found_on_a_later_page(self) -> None:
        pages = [listing_with([{"id": "P_other", "number": 1, "title": "Other"}], cursor="c1"),
                 listing_with([LAPLACE])]
        _, state, _ = observed(Forge(listing=pages))
        self.assertTrue(state.exists)

    def test_two_projects_with_the_same_title_are_refused(self) -> None:
        twins = listing_with([LAPLACE, dict(LAPLACE, id="P_twin", number=9)])
        with self.assertRaises(GhEtabliError) as caught:
            observed(Forge(listing=twins))
        self.assertIn("Laplace", str(caught.exception))

    def test_a_project_the_forge_does_not_return_is_an_error(self) -> None:
        with self.assertRaises(GhEtabliError):
            observed(Forge(project={"data": {"node": None}}))

    def test_a_graphql_error_is_raised_with_its_message(self) -> None:
        forge = Forge()
        forge.fail_on = "node(id:"
        with self.assertRaises(GhEtabliError) as caught:
            observed(forge)
        self.assertIn("Resource not accessible", str(caught.exception))


class Applying(unittest.TestCase):
    def apply(self, change: Change) -> Forge:
        adapter, _, forge = observed()
        forge.calls.clear()
        adapter.apply(change)
        return forge

    def test_a_missing_project_is_created_under_its_owner(self) -> None:
        listing = json.loads(json.dumps(LIST))
        listing["data"]["repositoryOwner"]["projectsV2"]["nodes"] = []
        forge = Forge(listing=listing)
        adapter = GhEtabli(runner=forge)
        adapter.observe_project(declared())
        adapter.apply(Change(KEY, "project", Kind.CREATE, "Laplace", after={"owner": "MasterLaplace",
                                                                            "title": "Laplace"}))
        self.assertEqual(forge.mutations()[-1], ("createProjectV2", {"input": {
            "ownerId": LIST["data"]["repositoryOwner"]["id"], "title": "Laplace"}}))

    def test_settings_send_only_the_changed_keys_under_their_api_names(self) -> None:
        forge = self.apply(Change(KEY, "project", Kind.UPDATE, "settings", before={"public": False},
                                  after={"public": True, "short_description": "d"}))
        name, variables = forge.mutations()[-1]
        self.assertEqual(name, "updateProjectV2")
        self.assertEqual(variables["input"], {"projectId": PROJECT["data"]["node"]["id"], "public": True,
                                              "shortDescription": "d"})

    def test_a_link_finds_the_repository_then_links_it(self) -> None:
        forge = self.apply(Change(KEY, "links", Kind.CREATE, "MasterLaplace/LplPlugin"))
        name, variables = forge.mutations()[-1]
        self.assertEqual((name, variables["input"]["repositoryId"]),
                         ("linkProjectV2ToRepository", "R_plugin"))

    def test_a_single_select_is_created_with_its_options(self) -> None:
        forge = self.apply(Change(KEY, "fields", Kind.CREATE, "Size", after={
            "name": "Size", "type": "single_select",
            "options": [{"name": "S", "color": "GREEN", "description": "small"}]}))
        name, variables = forge.mutations()[-1]
        self.assertEqual(name, "createProjectV2Field")
        self.assertEqual(variables["input"]["dataType"], "SINGLE_SELECT")
        self.assertEqual(variables["input"]["singleSelectOptions"],
                         [{"name": "S", "color": "GREEN", "description": "small"}])

    def test_a_date_field_is_created_without_options(self) -> None:
        forge = self.apply(Change(KEY, "fields", Kind.CREATE, "Due", after={"name": "Due", "type": "date",
                                                                           "options": []}))
        self.assertNotIn("singleSelectOptions", forge.mutations()[-1][1]["input"])

    def test_options_are_updated_on_the_field_id_with_their_own_ids(self) -> None:
        options = [{"name": "Ready", "color": "BLUE", "description": "d", "id": "opt0"},
                   {"name": "New", "color": "GRAY", "description": "n"}]
        forge = self.apply(Change(KEY, "fields", Kind.UPDATE, "Status",
                                  before={"id": "PVTSSF_s", "options": []}, after={"options": options}))
        name, variables = forge.mutations()[-1]
        self.assertEqual((name, variables["input"]["fieldId"]), ("updateProjectV2Field", "PVTSSF_s"))
        self.assertEqual(variables["input"]["singleSelectOptions"], options)

    def test_a_view_is_created_with_the_api_version_it_was_measured_on(self) -> None:
        forge = self.apply(Change(KEY, "views", Kind.CREATE, "Next",
                                  after={"name": "Next", "layout": "table"}))
        argv, _ = forge.rest()[-1]
        self.assertIn("X-GitHub-Api-Version: 2026-03-10", argv)

    def test_a_view_of_an_organization_project_goes_under_orgs(self) -> None:
        forge = Forge(listing=listing_with([LAPLACE], typename="Organization"))
        adapter = GhEtabli(runner=forge)
        adapter.observe_project(declared())
        adapter.apply(Change(KEY, "views", Kind.CREATE, "Next", after={"name": "Next", "layout": "table"}))
        self.assertEqual(forge.rest()[-1][0][3], "orgs/MasterLaplace/projectsV2/7/views")

    def test_view_fields_are_found_whatever_their_case(self) -> None:
        forge = self.apply(Change(KEY, "views", Kind.CREATE, "Next", after={
            "name": "Next", "layout": "table", "fields": ["title", "PRIORITY"]}))
        self.assertEqual(forge.rest()[-1][1]["visible_fields"], [419546262, 419546276])

    def test_a_view_naming_a_field_the_project_lacks_is_a_forge_error(self) -> None:
        adapter, _, _ = observed()
        with self.assertRaises(GhEtabliError) as caught:
            adapter.apply(Change(KEY, "views", Kind.CREATE, "Next", after={
                "name": "Next", "layout": "table", "fields": ["Size"]}))
        self.assertIn("Size", str(caught.exception))

    def test_a_rebuilt_view_is_created_before_the_old_one_is_deleted(self) -> None:
        forge = self.apply(Change(KEY, "views", Kind.UPDATE, "Next", before={"id": "PVTV_next"},
                                  after={"name": "Next", "layout": "table", "sort_by": [["Priority", "desc"]],
                                         "rebuild": True}))
        kinds = [("rest" if argv[:2] != ["api", "graphql"] else "graphql") for argv, body in forge.calls
                 if argv[:2] != ["api", "graphql"] or "mutation" in body["query"]]
        self.assertEqual(kinds, ["rest", "graphql"])

    def test_a_rebuild_keeps_what_the_declaration_does_not_say(self) -> None:
        before = {"id": "PVTV_next", "name": "Next", "layout": "table", "filter": "is:open",
                  "fields": ["Title", "Priority", "Updated"], "sort_by": [], "group_by": ["Repository"],
                  "vertical_group_by": []}
        forge = self.apply(Change(KEY, "views", Kind.UPDATE, "Next", before=before,
                                  after={"name": "Next", "layout": "table", "sort_by": [["Priority", "desc"]],
                                         "rebuild": True}))
        body = forge.rest()[-1][1]
        self.assertEqual(body["visible_fields"], [419546262, 419546276])
        self.assertEqual(body["group_by"], [419546268])
        self.assertEqual(body["sort_by"], [[419546276, "desc"]])

    def test_a_rebuild_whose_creation_fails_keeps_the_old_view(self) -> None:
        adapter, _, forge = observed()
        forge.rest_fails = True
        forge.calls.clear()
        with self.assertRaises(GhEtabliError):
            adapter.apply(Change(KEY, "views", Kind.UPDATE, "Next", before={"id": "PVTV_next"},
                                 after={"name": "Next", "layout": "table", "sort_by": [["Priority", "desc"]],
                                        "rebuild": True}))
        self.assertEqual(forge.mutations(), [])

    def test_a_view_is_created_through_rest_with_field_database_ids(self) -> None:
        forge = self.apply(Change(KEY, "views", Kind.CREATE, "Next", after={
            "name": "Next", "layout": "table", "filter": "is:open", "fields": ["Title", "Priority"],
            "sort_by": [["Priority", "asc"]], "group_by": ["Repository"]}))
        argv, body = forge.rest()[-1]
        self.assertEqual(argv[:4], ["api", "-X", "POST", "users/MasterLaplace/projectsV2/7/views"])
        self.assertEqual(body, {"name": "Next", "layout": "table", "filter": "is:open",
                                "visible_fields": [419546262, 419546276], "sort_by": [[419546276, "asc"]],
                                "group_by": [419546268]})

    def test_a_board_gets_its_columns(self) -> None:
        forge = self.apply(Change(KEY, "views", Kind.CREATE, "Board", after={
            "name": "Board", "layout": "board", "vertical_group_by": ["Status"]}))
        self.assertEqual(forge.rest()[-1][1]["vertical_group_by"], [419546264])

    def test_a_filter_is_changed_in_place(self) -> None:
        forge = self.apply(Change(KEY, "views", Kind.UPDATE, "Next", before={"id": "PVTV_next"},
                                  after={"name": "Next", "layout": "table", "filter": "is:issue",
                                         "rebuild": False}))
        name, variables = forge.mutations()[-1]
        self.assertEqual(name, "updateProjectV2View")
        self.assertEqual(variables["input"], {"viewId": "PVTV_next", "layout": "TABLE_LAYOUT",
                                              "filter": "is:issue"})
        self.assertEqual(forge.rest(), [])

    def test_visible_fields_are_changed_in_place_by_node_id(self) -> None:
        forge = self.apply(Change(KEY, "views", Kind.UPDATE, "Next", before={"id": "PVTV_next"},
                                  after={"name": "Next", "layout": "table", "fields": ["Title"],
                                         "rebuild": False}))
        title = next(field["id"] for field in PROJECT["data"]["node"]["fields"]["nodes"]
                     if field["name"] == "Title")
        self.assertEqual(forge.mutations()[-1][1]["input"]["configuration"], {"visibleFieldIds": [title]})

    def test_a_new_sort_rebuilds_the_view(self) -> None:
        forge = self.apply(Change(KEY, "views", Kind.UPDATE, "Next", before={"id": "PVTV_next"},
                                  after={"name": "Next", "layout": "table", "sort_by": [["Priority", "desc"]],
                                         "rebuild": True}))
        self.assertEqual(forge.mutations()[-1], ("deleteProjectV2View", {"input": {"viewId": "PVTV_next"}}))
        self.assertEqual(forge.rest()[-1][1]["sort_by"], [[419546276, "desc"]])

    def test_a_blocked_workflow_is_never_written(self) -> None:
        adapter, _, _ = observed()
        with self.assertRaises(GhEtabliError):
            adapter.apply(Change(KEY, "workflows", Kind.BLOCKED, "Item closed"))


if __name__ == "__main__":
    unittest.main()
