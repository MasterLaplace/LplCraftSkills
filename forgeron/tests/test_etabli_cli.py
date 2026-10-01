from __future__ import annotations

import dataclasses
import io
import json
import pathlib
import tempfile
import unittest

from forgeron import cli
from forgeron.etabli import Change, ConfigError, Desired, Kind, Label, Observed, ObservedLabel
from forgeron.etabli_projects import DesiredProject, ObservedProject
from forgeron.gh_etabli import GhEtabliError
from forgeron.journal import Journal

BUG = Label("type:bug", "d73a4a", "Something does not do what it promises")

MAIN = {
    "name": "main", "target": "branch", "enforcement": "active",
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "rules": [{"type": "deletion"}],
    "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}],
}


class MemoryForge:
    def __init__(self, state: Observed, sticky: bool = False, refuse: str = "",
                 blind_after: int = 0) -> None:
        self.state = state
        self.sticky = sticky
        self.refuse = refuse
        self.blind_after = blind_after
        self.applied: list[str] = []
        self.observed = 0

    def observe(self, slug: str) -> Observed:
        self.observed += 1
        if self.blind_after and self.observed > self.blind_after:
            raise GhEtabliError("gh: Bad Gateway (HTTP 502)")
        return self.state

    def apply(self, change) -> None:
        if change.name == self.refuse:
            raise GhEtabliError(f"gh: Forbidden (HTTP 403) on {change.name}")
        self.applied.append(f"{change.kind.name} {change.name}")
        if self.sticky:
            return
        if change.domain == "labels" and change.kind in (Kind.CREATE, Kind.UPDATE, Kind.RENAME):
            kept = tuple(label for label in self.state.labels if label.name != change.name)
            added = ObservedLabel(change.after["name"], change.after["color"],
                                  change.after["description"], 0)
            self.state = dataclasses.replace(self.state, labels=kept + (added,))
        elif change.domain == "settings":
            self.state = dataclasses.replace(self.state, settings={**self.state.settings, **change.after})


def run(forge: MemoryForge, write: bool, want: Desired | None = None, as_json: bool = False,
        journal: Journal | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    want = want or Desired(slug="o/r", labels=(BUG,), settings={"allow_squash_merge": False})
    code = cli.run_etabli((want,), forge, write=write, as_json=as_json, journal=journal,
                          out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def fresh() -> Observed:
    return Observed(slug="o/r", admin=True, push=True, settings={"allow_squash_merge": True})


def converged() -> Observed:
    return dataclasses.replace(fresh(), settings={"allow_squash_merge": False},
                               labels=(ObservedLabel(BUG.name, BUG.color, BUG.description, 0),))


BOARD = DesiredProject(key="o/Board", owner="o", title="Board",
                       views=({"name": "Next", "layout": "table", "filter": "is:open"},),
                       workflows=(("Item closed", True),))

NEXT = {"id": "PVTV_next", "name": "Next", "layout": "table", "filter": "is:open", "fields": [],
        "sort_by": [], "group_by": [], "vertical_group_by": []}


def board(**changes) -> ObservedProject:
    base = {"key": "o/Board", "exists": True, "can_update": True, "id": "PVT_1", "number": 1,
            "url": "https://github.com/users/o/projects/1", "views": (NEXT,),
            "workflows": {"Item closed": True}}
    base.update(changes)
    return ObservedProject(**base)


class MemoryProjects:
    def __init__(self, state: ObservedProject, stuck: bool = False) -> None:
        self.state = state
        self.stuck = stuck
        self.applied: list[str] = []
        self.observed = 0

    def observe_project(self, desired: DesiredProject) -> ObservedProject:
        self.observed += 1
        return self.state

    def apply(self, change) -> None:
        self.applied.append(f"{change.kind.name} {change.domain} {change.name}")
        if self.stuck:
            return
        if change.domain == "project" and change.kind is Kind.CREATE:
            self.state = board(views=())
        elif change.domain == "views" and change.kind is Kind.CREATE:
            self.state = dataclasses.replace(self.state, views=self.state.views + (NEXT,))


def run_projects(forge: MemoryProjects, write: bool, as_json: bool = False) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli.run_etabli((), forge, write=write, as_json=as_json, out=out, err=err, projects=(BOARD,))
    return code, out.getvalue(), err.getvalue()


class Projects(unittest.TestCase):
    def test_a_converged_project_exits_zero(self) -> None:
        code, out, _ = run_projects(MemoryProjects(board()), write=False)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("o/Board", out)
        self.assertIn("= nothing to change", out)

    def test_a_missing_view_is_planned_and_left_without_write(self) -> None:
        forge = MemoryProjects(board(views=()))
        code, out, _ = run_projects(forge, write=False)
        self.assertEqual((code, forge.applied), (cli.EXIT_DRIFT, []))
        self.assertIn("+ views     Next", out)

    def test_write_creates_the_view_and_reads_the_project_again(self) -> None:
        forge = MemoryProjects(board(views=()))
        code, _, _ = run_projects(forge, write=True)
        self.assertEqual((code, forge.applied, forge.observed), (cli.EXIT_OK, ["CREATE views Next"], 2))

    def test_a_project_created_by_the_run_gets_its_content_in_the_same_run(self) -> None:
        forge = MemoryProjects(ObservedProject(key="o/Board", exists=False))
        code, out, _ = run_projects(forge, write=True)
        self.assertEqual(forge.applied, ["CREATE project Board", "CREATE views Next"])
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("+ views     Next", out.split("after reading again")[0])

    def test_a_project_the_forge_never_shows_is_created_once_and_reported(self) -> None:
        forge = MemoryProjects(ObservedProject(key="o/Board", exists=False), stuck=True)
        code, _, _ = run_projects(forge, write=True)
        self.assertEqual(forge.applied, ["CREATE project Board"])
        self.assertEqual(code, cli.EXIT_DRIFT)

    def test_the_plan_of_a_missing_project_shows_what_follows_its_creation(self) -> None:
        code, out, _ = run_projects(MemoryProjects(ObservedProject(key="o/Board", exists=False)), write=False)
        self.assertEqual(code, cli.EXIT_DRIFT)
        self.assertIn("+ project   Board", out)
        self.assertIn("+ views     Next", out)

    def test_the_text_output_says_a_project_is_a_project(self) -> None:
        _, out, _ = run_projects(MemoryProjects(board()), write=False)
        self.assertIn("project o/Board", out)

    def test_a_workflow_left_off_exits_blocked_and_says_where_to_switch_it(self) -> None:
        code, out, _ = run_projects(MemoryProjects(board(workflows={"Item closed": False})), write=False)
        self.assertEqual(code, cli.EXIT_BLOCKED)
        self.assertIn("https://github.com/users/o/projects/1/workflows", out)

    def test_a_project_nobody_can_update_is_nothing_checked(self) -> None:
        code, out, _ = run_projects(MemoryProjects(board(can_update=False)), write=False)
        self.assertEqual(code, cli.EXIT_BLOCKED)
        self.assertIn("nothing checked", out)

    def test_an_option_update_shows_what_changes_in_each_option(self) -> None:
        change = Change("o/Board", "fields", Kind.UPDATE, "Priority",
                        before={"id": "f", "options": [
                            {"name": "High", "color": "ORANGE", "description": "Next."},
                            {"name": "Low", "color": "GRAY", "description": "Later."}]},
                        after={"options": [
                            {"name": "High", "color": "RED", "description": "Next.", "id": "a"},
                            {"name": "Urgent", "color": "RED", "description": "Now."}]})
        text = cli._describe(change)
        self.assertIn("High color ORANGE -> RED", text)
        self.assertIn("+ Urgent", text)
        self.assertIn("- Low", text)

    def test_an_option_whose_name_changes_case_says_so(self) -> None:
        change = Change("o/Board", "fields", Kind.UPDATE, "Priority",
                        before={"id": "f", "options": [{"name": "high", "color": "RED", "description": ""}]},
                        after={"options": [{"name": "High", "color": "RED", "description": "", "id": "a"}]})
        self.assertIn("high -> High", cli._describe(change))

    def test_json_lists_projects_apart_from_repositories(self) -> None:
        _, out, _ = run_projects(MemoryProjects(board(views=())), write=False, as_json=True)
        payload = json.loads(out)
        self.assertEqual(payload["repos"], [])
        self.assertEqual(payload["projects"][0]["project"], "o/Board")
        self.assertEqual(payload["projects"][0]["planned"][0]["domain"], "views")
        self.assertEqual(payload["projects"][0]["planned"][0]["project"], "o/Board")
        self.assertNotIn("repo", payload["projects"][0]["planned"][0])


class Plan(unittest.TestCase):
    def test_without_write_nothing_is_applied_and_the_exit_says_changes_are_left(self) -> None:
        forge = MemoryForge(fresh())
        code, out, err = run(forge, write=False)
        self.assertEqual(forge.applied, [])
        self.assertEqual(code, cli.EXIT_DRIFT)
        self.assertIn("+ labels    type:bug", out)
        self.assertIn("allow_squash_merge True -> False", out)
        self.assertIn("--write", err)

    def test_a_converged_repository_exits_zero(self) -> None:
        code, out, _ = run(MemoryForge(converged()), write=False)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("= nothing to change", out)

    def test_a_blocked_point_alone_exits_blocked(self) -> None:
        want = Desired(slug="o/r", security={"dependabot_alerts": True})
        state = dataclasses.replace(fresh(), security={"dependabot_alerts": None})
        code, _, _ = run(MemoryForge(state), write=False, want=want)
        self.assertEqual(code, cli.EXIT_BLOCKED)

    def test_changes_left_win_over_a_blocked_point(self) -> None:
        want = Desired(slug="o/r", labels=(BUG,), security={"dependabot_alerts": True})
        state = dataclasses.replace(fresh(), security={"dependabot_alerts": None})
        code, _, _ = run(MemoryForge(state), write=False, want=want)
        self.assertEqual(code, cli.EXIT_DRIFT)

    def test_a_repository_where_nothing_could_be_checked_does_not_exit_zero(self) -> None:
        want = Desired(slug="o/r", settings={"allow_squash_merge": False})
        state = Observed(slug="o/r", admin=False, push=True)
        code, out, _ = run(MemoryForge(state), write=False, want=want)
        self.assertEqual(code, cli.EXIT_BLOCKED)
        self.assertIn("nothing checked", out)

    def test_no_domain_left_after_only_is_nothing_checked(self) -> None:
        want = Desired(slug="o/r", labels=(BUG,), domains=())
        code, out, _ = run(MemoryForge(fresh()), write=False, want=want)
        self.assertEqual(code, cli.EXIT_BLOCKED)
        self.assertIn("nothing checked", out)

    def test_a_rename_shows_every_field_it_rewrites(self) -> None:
        want = Desired(slug="o/r", labels=(BUG,), renames=(("bug", "type:bug"),))
        state = dataclasses.replace(converged(), labels=(ObservedLabel("bug", "d73a4a",
                                                                       "Something isn't working", 3),))
        _, out, _ = run(MemoryForge(state), write=False, want=want)
        self.assertIn("bug -> type:bug", out)
        self.assertIn("\"Something isn't working\" -> 'Something does not do what it promises'", out)

    def test_a_ruleset_creation_shows_its_enforcement_and_bypass(self) -> None:
        want = Desired(slug="o/r", rulesets=(MAIN,))
        _, out, _ = run(MemoryForge(fresh()), write=False, want=want)
        self.assertIn("enforcement active", out)
        self.assertIn("RepositoryRole 5 pull_request", out)

    def test_json_output_parses_and_carries_the_plan(self) -> None:
        code, out, _ = run(MemoryForge(fresh()), write=False, as_json=True)
        payload = json.loads(out)
        self.assertEqual(payload["exit"], code)
        self.assertEqual([change["kind"] for change in payload["repos"][0]["planned"]],
                         ["create", "update"])


class Write(unittest.TestCase):
    def test_write_applies_then_reads_again_and_converges(self) -> None:
        forge = MemoryForge(fresh())
        code, out, _ = run(forge, write=True)
        self.assertEqual(forge.applied, ["CREATE type:bug", "UPDATE settings"])
        self.assertEqual(forge.observed, 2)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("after reading again", out)

    def test_write_prints_each_change_it_applied(self) -> None:
        _, out, _ = run(MemoryForge(fresh()), write=True)
        applied = out.split("applied:")[1].split("after reading again")[0]
        self.assertIn("+ labels    type:bug", applied)
        self.assertIn("~ settings  allow_squash_merge True -> False", applied)

    def test_a_forge_that_does_not_take_the_change_is_caught_by_the_second_read(self) -> None:
        code, out, _ = run(MemoryForge(fresh(), sticky=True), write=True)
        self.assertEqual(code, cli.EXIT_DRIFT)
        self.assertIn("+ labels    type:bug", out.split("after reading again")[1])

    def test_a_refused_write_is_reported_and_the_others_still_go_through(self) -> None:
        forge = MemoryForge(fresh(), refuse="type:bug")
        code, out, _ = run(forge, write=True)
        self.assertEqual(forge.applied, ["UPDATE settings"])
        self.assertEqual(code, cli.EXIT_ENVIRONMENT)
        self.assertIn("FAILED", out)

    def test_each_write_leaves_a_trace_in_the_journal(self) -> None:
        journal = Journal(None, echo=None)
        run(MemoryForge(fresh(), refuse="type:bug"), write=True, journal=journal)
        self.assertEqual([(event["event"], event["name"]) for event in journal.events],
                         [("etabli_failed", "type:bug"), ("etabli_applied", "settings")])
        self.assertEqual(journal.events[1]["before"], {"allow_squash_merge": True})

    def test_a_failed_second_read_does_not_pass_the_old_plan_off_as_what_is_left(self) -> None:
        code, out, _ = run(MemoryForge(fresh(), blind_after=1), write=True, as_json=True)
        payload = json.loads(out)
        self.assertIsNone(payload["repos"][0]["remaining"])
        self.assertEqual(code, cli.EXIT_ENVIRONMENT)
        _, text, _ = run(MemoryForge(fresh(), blind_after=1), write=True)
        self.assertIn("not read again", text)
        self.assertNotIn("after reading again", text)

    def test_nothing_to_change_means_no_write_and_no_second_read(self) -> None:
        forge = MemoryForge(converged())
        run(forge, write=True)
        self.assertEqual((forge.applied, forge.observed), ([], 1))


class Selection(unittest.TestCase):
    def test_only_restricts_the_domains_and_repo_the_repositories(self) -> None:
        wants = (Desired(slug="o/a"), Desired(slug="o/b"))
        (chosen,) = cli.select_desired(wants, ["o/b"], "labels")
        self.assertEqual((chosen.slug, chosen.domains), ("o/b", ("labels",)))

    def test_an_undeclared_repository_or_domain_is_refused(self) -> None:
        wants = (Desired(slug="o/a"),)
        with self.assertRaises(ConfigError):
            cli.select_desired(wants, ["o/zzz"], "")
        with self.assertRaises(ConfigError):
            cli.select_desired(wants, [], "labels,colour")

    def test_projects_is_a_domain_of_only(self) -> None:
        wants = (Desired(slug="o/a"),)
        self.assertEqual(cli.select_desired(wants, [], "projects"), ())
        self.assertEqual(cli.select_projects((BOARD,), [], [], "projects"), (BOARD,))

    def test_naming_repositories_leaves_projects_out_and_the_reverse(self) -> None:
        wants = (Desired(slug="o/a"),)
        self.assertEqual(cli.select_projects((BOARD,), [], ["o/a"], ""), ())
        self.assertEqual(cli.select_desired(wants, [], "", projects=["o/Board"]), ())
        self.assertEqual(cli.select_projects((BOARD,), ["o/Board"], ["o/a"], ""), (BOARD,))

    def test_a_repository_domain_in_only_leaves_projects_out(self) -> None:
        self.assertEqual(cli.select_projects((BOARD,), [], [], "labels"), ())

    def test_an_undeclared_project_is_refused(self) -> None:
        with self.assertRaises(ConfigError) as caught:
            cli.select_projects((BOARD,), ["o/Other"], [], "")
        self.assertIn("o/Board", str(caught.exception))

    def test_a_selection_that_leaves_nothing_is_a_usage_error(self) -> None:
        declaration = {"repos": {"o/a": {}}, "projects": {"o/Board": {"views": []}}}
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "etabli.json"
            path.write_text(json.dumps(declaration), encoding="utf-8")
            for argv in (["--only", "labels", "--project", "o/Board"],
                         ["--only", "projects", "--repo", "o/a"]):
                self.assertEqual(cli.main(["etabli", "--file", str(path), *argv]), cli.EXIT_USAGE, argv)

    def test_a_missing_configuration_file_is_a_usage_error(self) -> None:
        code = cli.main(["etabli", "--file", "/definitely/missing/etabli.json"])
        self.assertEqual(code, cli.EXIT_USAGE)


if __name__ == "__main__":
    unittest.main()
