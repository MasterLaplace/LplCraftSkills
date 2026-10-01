from __future__ import annotations

import dataclasses
import pathlib
import unittest

from forgeron.etabli import ConfigError, Kind, parse
from forgeron.etabli_projects import (DesiredProject, ObservedField, ObservedProject, Option, load_projects,
                                      parse_projects, plan_project)

ROOT = pathlib.Path(__file__).resolve().parents[1]

READMES = {"projects/laplace.md": "# Laplace\n\nThe core of Laplace.\n"}

STATUS = [
    {"name": "Ready", "color": "BLUE", "description": "Triaged: anyone can take it."},
    {"name": "To review", "color": "PURPLE", "description": "The pull request waits for a review."},
    {"name": "Done", "color": "GRAY", "description": "Closed or merged."},
]


def declaration(**changes) -> dict:
    project = {
        "public": True,
        "short_description": "The core of Laplace.",
        "readme": "projects/laplace.md",
        "repositories": ["MasterLaplace/LplKernel", "MasterLaplace/LplPlugin"],
        "fields": {
            "Status": {"type": "single_select", "options": [dict(option) for option in STATUS]},
            "Target date": {"type": "date"},
        },
        "views": [
            {"name": "Next", "layout": "table", "filter": "is:issue status:Ready",
             "fields": ["Title", "Repository", "Status"], "sort_by": [["Status", "asc"]],
             "group_by": "Repository"},
            {"name": "To review", "layout": "board", "filter": "is:pr is:open",
             "vertical_group_by": "Status"},
        ],
        "workflows": {"Item added to project": True, "Auto-archive items": False},
    }
    project.update(changes)
    return {"MasterLaplace/Laplace": project}


def read(path: str) -> str:
    if path == "projects/latin1.md":
        raise UnicodeDecodeError("utf-8", b"\xe9", 0, 1, "invalid continuation byte")
    if path not in READMES:
        raise FileNotFoundError(path)
    return READMES[path]


def desired(**changes) -> DesiredProject:
    return parse_projects(declaration(**changes), source="etabli.projects", read=read)[0]


def refused(test: unittest.TestCase, raw: dict, *fragments: str) -> None:
    with test.assertRaises(ConfigError) as caught:
        parse_projects(raw, source="etabli.projects", read=read)
    for fragment in fragments:
        test.assertIn(fragment, str(caught.exception))


def status_field(options=STATUS) -> ObservedField:
    return ObservedField(id="PVTSSF_status", database_id=1, name="Status", type="SINGLE_SELECT",
                         options=tuple(Option(o["name"], o["color"], o["description"]) for o in options),
                         option_ids=tuple(f"opt{index}" for index, _ in enumerate(options)))


def builtin(name: str, kind: str) -> ObservedField:
    return ObservedField(id=f"PVTF_{name}", database_id=0, name=name, type=kind)


def converged() -> ObservedProject:
    return ObservedProject(
        key="MasterLaplace/Laplace", exists=True, can_update=True, id="PVT_7", number=7,
        url="https://github.com/users/MasterLaplace/projects/7", owner_type="User", items=21,
        public=True, short_description="The core of Laplace.", readme=READMES["projects/laplace.md"],
        repositories=("MasterLaplace/LplKernel", "MasterLaplace/LplPlugin"),
        fields=(builtin("Title", "TITLE"), builtin("Repository", "REPOSITORY"), status_field(),
                ObservedField(id="PVTF_target", database_id=2, name="Target date", type="DATE"),
                builtin("Updated", "UPDATED")),
        views=(
            {"id": "PVTV_1", "name": "Next", "layout": "table", "filter": "is:issue status:Ready",
             "fields": ["Repository", "Status", "Title"], "sort_by": [["Status", "asc"]],
             "group_by": ["Repository"], "vertical_group_by": []},
            {"id": "PVTV_2", "name": "To review", "layout": "board", "filter": "is:pr is:open",
             "fields": ["Title", "Status"], "sort_by": [], "group_by": [],
             "vertical_group_by": ["Status"]},
        ),
        workflows={"Item added to project": True, "Item closed": True},
    )


def kinds(changes) -> list[tuple[str, Kind, str]]:
    return [(change.domain, change.kind, change.name) for change in changes]


class Parsing(unittest.TestCase):
    def test_the_declaration_is_read_with_its_readme_from_a_file(self) -> None:
        project = desired()
        self.assertEqual((project.owner, project.title), ("MasterLaplace", "Laplace"))
        self.assertEqual(project.readme, READMES["projects/laplace.md"])
        self.assertEqual([field.name for field in project.fields], ["Status", "Target date"])
        self.assertEqual(project.workflows, (("Item added to project", True), ("Auto-archive items", False)))

    def test_the_example_shipped_with_forgeron_declares_a_project_with_its_readme(self) -> None:
        (project,) = load_projects(str(ROOT / "etabli.example.json"))
        self.assertTrue(project.readme and project.fields and project.views and project.workflows)

    def test_the_repository_file_accepts_a_projects_section(self) -> None:
        wanted = parse({"repos": {"o/r": {}}, "projects": declaration()})
        self.assertEqual([want.slug for want in wanted], ["o/r"])

    def test_the_key_names_an_owner_and_a_title(self) -> None:
        refused(self, {"Laplace": declaration()["MasterLaplace/Laplace"]}, "Laplace", "OWNER/TITLE")

    def test_an_unknown_key_is_refused_by_name(self) -> None:
        refused(self, declaration(colour="blue"), "colour")

    def test_a_missing_readme_file_is_refused_with_its_path(self) -> None:
        refused(self, declaration(readme="projects/missing.md"), "projects/missing.md")

    def test_a_readme_that_is_not_utf8_is_refused(self) -> None:
        refused(self, declaration(readme="projects/latin1.md"), "projects/latin1.md")

    def test_a_readme_outside_the_configuration_folder_is_refused(self) -> None:
        for path in ("../secrets.md", "/etc/passwd", "C:/Users/me/.ssh/id_ed25519", "projects/../../x.md",
                     "..\\secrets.md"):
            with self.assertRaises(ConfigError, msg=path) as caught:
                parse_projects(declaration(readme=path), source="etabli.projects", read=lambda _: "leaked")
            self.assertIn("folder", str(caught.exception))

    def test_a_repository_of_another_owner_cannot_be_linked(self) -> None:
        refused(self, declaration(repositories=["Christian-guajardo/LplAssistant"]),
                "Christian-guajardo/LplAssistant", "MasterLaplace")

    def test_a_single_select_needs_options_with_a_known_color(self) -> None:
        refused(self, declaration(fields={"Priority": {"type": "single_select", "options": []}}),
                "Priority", "options")
        refused(self, declaration(fields={"Priority": {"type": "single_select", "options": [
            {"name": "High", "color": "TEAL", "description": "Next in line."}]}}), "TEAL", "PURPLE")

    def test_two_options_with_the_same_name_are_refused(self) -> None:
        refused(self, declaration(fields={"Priority": {"type": "single_select", "options": [
            {"name": "High", "color": "RED", "description": "a"},
            {"name": "high", "color": "RED", "description": "b"}]}}), "High", "high")

    def test_a_built_in_field_cannot_be_declared_except_status(self) -> None:
        refused(self, declaration(fields={"Title": {"type": "text"}}), "Title", "built-in")
        refused(self, declaration(fields={"Status": {"type": "date"}}), "Status", "single_select")

    def test_a_built_in_name_is_recognised_whatever_its_case(self) -> None:
        refused(self, declaration(fields={"title": {"type": "text"}}), "title", "built-in")
        refused(self, declaration(fields={"status": {"type": "date"}}), "status", "single_select")
        refused(self, declaration(fields={"updated": {"type": "date"}}), "updated", "built-in")

    def test_a_date_field_carries_no_options(self) -> None:
        refused(self, declaration(fields={"Start date": {"type": "date", "options": []}}), "Start date")

    def test_a_view_names_only_declared_or_built_in_fields(self) -> None:
        refused(self, declaration(views=[{"name": "Next", "layout": "table", "fields": ["Priority"]}]),
                "Next", "Priority")

    def test_a_view_cannot_use_the_dates_the_api_refuses(self) -> None:
        refused(self, declaration(views=[{"name": "Stale", "layout": "table",
                                          "sort_by": [["Updated", "asc"]]}]),
                "Stale", "Updated", "interface")

    def test_a_roadmap_takes_no_visible_fields(self) -> None:
        refused(self, declaration(views=[{"name": "Roadmap", "layout": "roadmap", "fields": ["Title"]}]),
                "Roadmap", "roadmap")

    def test_columns_are_for_a_board_only(self) -> None:
        refused(self, declaration(views=[{"name": "Next", "layout": "table",
                                          "vertical_group_by": "Status"}]), "Next", "board")

    def test_a_view_layout_and_a_sort_direction_are_closed_lists(self) -> None:
        refused(self, declaration(views=[{"name": "Next", "layout": "kanban"}]), "kanban", "roadmap")
        refused(self, declaration(views=[{"name": "Next", "layout": "table",
                                          "sort_by": [["Status", "up"]]}]), "up", "asc")

    def test_two_views_with_the_same_name_are_refused(self) -> None:
        refused(self, declaration(views=[{"name": "Next", "layout": "table"},
                                         {"name": "Next", "layout": "board"}]), "Next")

    def test_a_workflow_is_declared_on_or_off(self) -> None:
        refused(self, declaration(workflows={"Item closed": "yes"}), "Item closed", "true or false")


class Planning(unittest.TestCase):
    def test_a_converged_project_plans_nothing(self) -> None:
        self.assertEqual(plan_project(desired(), converged()), [])

    def test_a_missing_project_is_created_first_then_shows_what_follows(self) -> None:
        missing = ObservedProject(key="MasterLaplace/Laplace", exists=False)
        planned = kinds(plan_project(desired(), missing))
        self.assertEqual(planned[0], ("project", Kind.CREATE, "Laplace"))
        for expected in [("project", Kind.UPDATE, "settings"),
                         ("links", Kind.CREATE, "MasterLaplace/LplKernel"),
                         ("fields", Kind.UPDATE, "Status"), ("fields", Kind.CREATE, "Target date"),
                         ("views", Kind.CREATE, "Next"), ("views", Kind.UNLISTED, "View 1"),
                         ("workflows", Kind.BLOCKED, "Item added to project")]:
            self.assertIn(expected, planned[1:])

    def test_what_follows_a_creation_says_where_to_set_the_workflows(self) -> None:
        missing = ObservedProject(key="MasterLaplace/Laplace", exists=False)
        workflow = next(change for change in plan_project(desired(), missing) if change.domain == "workflows")
        self.assertIn("Workflows page", workflow.note)
        self.assertNotIn("/workflows", workflow.note)

    def test_a_project_the_viewer_cannot_update_is_skipped(self) -> None:
        locked = dataclasses.replace(converged(), can_update=False)
        self.assertEqual(kinds(plan_project(desired(), locked)), [("project", Kind.SKIPPED, "*")])

    def test_settings_that_differ_are_one_update_with_only_those_keys(self) -> None:
        drifted = dataclasses.replace(converged(), public=False, short_description="old")
        changes = plan_project(desired(), drifted)
        self.assertEqual(kinds(changes), [("project", Kind.UPDATE, "settings")])
        self.assertEqual(changes[0].after, {"public": True, "short_description": "The core of Laplace."})

    def test_a_readme_differing_only_by_line_endings_is_the_same(self) -> None:
        windows = READMES["projects/laplace.md"].replace("\n", "\r\n").rstrip()
        crlf = dataclasses.replace(converged(), readme=windows)
        self.assertEqual(plan_project(desired(), crlf), [])

    def test_a_missing_link_is_created_and_an_extra_one_reported(self) -> None:
        linked = dataclasses.replace(converged(),
                                     repositories=("MasterLaplace/LplKernel", "MasterLaplace/Old"))
        self.assertEqual(kinds(plan_project(desired(), linked)), [
            ("links", Kind.CREATE, "MasterLaplace/LplPlugin"), ("links", Kind.UNLISTED, "MasterLaplace/Old")])

    def test_a_missing_field_is_created_with_its_options(self) -> None:
        bare = dataclasses.replace(converged(), fields=tuple(field for field in converged().fields
                                                             if field.name != "Target date"))
        changes = plan_project(desired(), bare)
        self.assertEqual(kinds(changes), [("fields", Kind.CREATE, "Target date")])
        self.assertEqual(changes[0].after, {"name": "Target date", "type": "date", "options": []})

    def test_a_changed_option_updates_the_field_and_keeps_option_ids(self) -> None:
        recolored = [dict(STATUS[0], color="GREEN")] + STATUS[1:]
        drifted = dataclasses.replace(converged(), fields=tuple(
            status_field(recolored) if field.name == "Status" else field for field in converged().fields))
        changes = plan_project(desired(), drifted)
        self.assertEqual(kinds(changes), [("fields", Kind.UPDATE, "Status")])
        self.assertEqual([option["id"] for option in changes[0].after["options"]], ["opt0", "opt1", "opt2"])
        self.assertEqual(changes[0].after["options"][0]["color"], "BLUE")

    def test_a_new_option_is_added_without_an_id(self) -> None:
        shorter = dataclasses.replace(converged(), fields=tuple(
            status_field(STATUS[:2]) if field.name == "Status" else field for field in converged().fields))
        changes = plan_project(desired(), shorter)
        self.assertEqual(kinds(changes), [("fields", Kind.UPDATE, "Status")])
        self.assertEqual([option.get("id") for option in changes[0].after["options"]], ["opt0", "opt1", None])

    def test_removing_an_option_is_blocked_because_items_lose_their_value(self) -> None:
        extra = STATUS + [{"name": "Inbox", "color": "GRAY", "description": "Not triaged."}]
        wider = dataclasses.replace(converged(), fields=tuple(
            status_field(extra) if field.name == "Status" else field for field in converged().fields))
        changes = plan_project(desired(), wider)
        self.assertEqual(kinds(changes), [("fields", Kind.BLOCKED, "Status")])
        self.assertIn("Inbox", changes[0].note)

    def test_an_option_of_a_project_without_items_is_removed_freely(self) -> None:
        extra = STATUS + [{"name": "Todo", "color": "GRAY", "description": ""}]
        fresh = dataclasses.replace(converged(), items=0, fields=tuple(
            status_field(extra) if field.name == "Status" else field for field in converged().fields))
        changes = plan_project(desired(), fresh)
        self.assertEqual(kinds(changes), [("fields", Kind.UPDATE, "Status")])
        self.assertEqual([option["name"] for option in changes[0].after["options"]],
                         ["Ready", "To review", "Done"])

    def test_a_field_of_another_type_is_blocked(self) -> None:
        retyped = dataclasses.replace(converged(), fields=tuple(
            dataclasses.replace(field, type="TEXT") if field.name == "Target date" else field
            for field in converged().fields))
        self.assertEqual(kinds(plan_project(desired(), retyped)), [("fields", Kind.BLOCKED, "Target date")])

    def test_an_undeclared_custom_field_is_reported_and_kept(self) -> None:
        extra = dataclasses.replace(converged(), fields=converged().fields + (
            ObservedField(id="PVTF_size", database_id=3, name="Size", type="SINGLE_SELECT"),))
        self.assertEqual(kinds(plan_project(desired(), extra)), [("fields", Kind.UNLISTED, "Size")])

    def test_a_missing_view_is_created(self) -> None:
        one = dataclasses.replace(converged(), views=converged().views[1:])
        changes = plan_project(desired(), one)
        self.assertEqual(kinds(changes), [("views", Kind.CREATE, "Next")])
        self.assertEqual(changes[0].after["group_by"], ["Repository"])

    def test_a_changed_filter_updates_the_view_in_place(self) -> None:
        views = list(converged().views)
        views[0] = dict(views[0], filter="is:issue")
        changes = plan_project(desired(), dataclasses.replace(converged(), views=tuple(views)))
        self.assertEqual(kinds(changes), [("views", Kind.UPDATE, "Next")])
        self.assertFalse(changes[0].after["rebuild"])

    def test_a_changed_sort_rebuilds_the_view(self) -> None:
        views = list(converged().views)
        views[0] = dict(views[0], sort_by=[["Status", "desc"]])
        changes = plan_project(desired(), dataclasses.replace(converged(), views=tuple(views)))
        self.assertEqual(kinds(changes), [("views", Kind.UPDATE, "Next")])
        self.assertTrue(changes[0].after["rebuild"])
        self.assertIn("created anew, then the old one deleted", changes[0].note)

    def test_what_a_view_does_not_declare_is_left_as_the_interface_set_it(self) -> None:
        views = list(converged().views)
        views[1] = dict(views[1], sort_by=[["Updated", "desc"]], fields=["Title"])
        self.assertEqual(plan_project(desired(), dataclasses.replace(converged(), views=tuple(views))), [])

    def test_an_undeclared_view_is_reported(self) -> None:
        extra = dataclasses.replace(converged(), views=converged().views + (
            {"id": "PVTV_3", "name": "View 1", "layout": "table", "filter": "", "fields": [], "sort_by": [],
             "group_by": [], "vertical_group_by": []},))
        self.assertEqual(kinds(plan_project(desired(), extra)), [("views", Kind.UNLISTED, "View 1")])

    def test_a_workflow_wanted_on_but_off_is_blocked_with_where_to_fix_it(self) -> None:
        off = dataclasses.replace(converged(), workflows={"Item added to project": False})
        changes = plan_project(desired(), off)
        self.assertEqual(kinds(changes), [("workflows", Kind.BLOCKED, "Item added to project")])
        self.assertIn("https://github.com/users/MasterLaplace/projects/7/workflows", changes[0].note)

    def test_a_workflow_wanted_off_but_on_is_blocked(self) -> None:
        on = dataclasses.replace(converged(), workflows={"Item added to project": True,
                                                         "Auto-archive items": True})
        self.assertEqual(kinds(plan_project(desired(), on)),
                         [("workflows", Kind.BLOCKED, "Auto-archive items")])

    def test_a_workflow_never_configured_counts_as_off(self) -> None:
        self.assertNotIn("Auto-archive items", converged().workflows)
        self.assertEqual(plan_project(desired(), converged()), [])


if __name__ == "__main__":
    unittest.main()
