from __future__ import annotations

import dataclasses
import io
import json
import unittest

from forgeron import cli
from forgeron.etabli import ConfigError, Desired, Kind, Label, Observed, ObservedLabel
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

    def test_a_missing_configuration_file_is_a_usage_error(self) -> None:
        code = cli.main(["etabli", "--file", "/definitely/missing/etabli.json"])
        self.assertEqual(code, cli.EXIT_USAGE)


if __name__ == "__main__":
    unittest.main()
