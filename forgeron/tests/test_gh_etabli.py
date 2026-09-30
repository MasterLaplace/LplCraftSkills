from __future__ import annotations

import json
import subprocess
import unittest
from unittest import mock

from forgeron.etabli import Change, Kind
from forgeron.gh_etabli import GhEtabli, GhEtabliError

REPO = {
    "permissions": {"admin": True, "push": True},
    "allow_merge_commit": True,
    "allow_squash_merge": True,
    "delete_branch_on_merge": False,
    "description": "not a setting etabli manages",
    "archived": False,
    "has_discussions": True,
    "security_and_analysis": {"secret_scanning": {"status": "enabled"},
                              "secret_scanning_push_protection": {"status": "disabled"}},
}


def labels_page(names: list[str], cursor: str = "") -> dict:
    return {"data": {"repository": {"labels": {
        "nodes": [{"name": name, "color": "D73A4A", "description": None,
                   "issues": {"totalCount": 2}, "pullRequests": {"totalCount": 1}} for name in names],
        "pageInfo": {"hasNextPage": bool(cursor), "endCursor": cursor or None},
    }}}}


class Runner:
    def __init__(self, routes: dict[str, tuple[int, str, str]] | None = None) -> None:
        self.calls: list[tuple[list[str], str | None]] = []
        self.routes = routes or {}
        self.pages = [labels_page(["bug", "wontfix"], cursor="c1"), labels_page(["good first issue"])]

    def __call__(self, argv: list[str], stdin: str | None) -> tuple[int, str, str]:
        self.calls.append((argv, stdin))
        if argv[:2] == ["api", "graphql"]:
            return 0, json.dumps(self.pages.pop(0)), ""
        path = next(arg for arg in argv[1:] if not arg.startswith("-") and arg not in
                    ("GET", "POST", "PATCH", "PUT", "DELETE"))
        if path in self.routes:
            return self.routes[path]
        return 0, "", ""


def observe_with(**routes) -> tuple:
    runner = Runner({"repos/o/r": (0, json.dumps(REPO), ""), **routes})
    return GhEtabli(runner=runner).observe("o/r"), runner


class Observing(unittest.TestCase):
    def test_labels_are_read_across_pages_with_their_uses(self) -> None:
        state, runner = observe_with(**{"repos/o/r/rulesets?includes_parents=false&per_page=100":
                                        (0, "[]", "")})
        self.assertEqual([label.name for label in state.labels], ["bug", "wontfix", "good first issue"])
        self.assertEqual({label.uses for label in state.labels}, {3})
        self.assertEqual({label.color for label in state.labels}, {"d73a4a"})
        cursors = [arg for argv, _ in runner.calls for arg in argv if arg.startswith("cursor=")]
        self.assertEqual(cursors, ["cursor=c1"])

    def test_only_managed_settings_are_kept(self) -> None:
        state, _ = observe_with()
        self.assertNotIn("description", state.settings)
        self.assertEqual(state.settings["allow_squash_merge"], True)

    def test_security_states_come_from_three_sources_and_an_error_stays_unknown(self) -> None:
        state, _ = observe_with(**{
            "repos/o/r/vulnerability-alerts": (1, "", "gh: Vulnerability alerts are disabled. (HTTP 404)"),
            "repos/o/r/automated-security-fixes": (0, json.dumps({"enabled": True, "paused": False}), ""),
            "repos/o/r/private-vulnerability-reporting": (1, "", "gh: Server Error (HTTP 500)"),
        })
        self.assertEqual(state.security, {
            "secret_scanning": True, "secret_scanning_push_protection": False,
            "dependabot_alerts": False, "dependabot_security_updates": True,
            "private_vulnerability_reporting": None,
        })

    def test_a_404_that_is_not_the_disabled_answer_stays_unknown(self) -> None:
        state, _ = observe_with(**{"repos/o/r/vulnerability-alerts": (1, "", "gh: Not Found (HTTP 404)")})
        self.assertIsNone(state.security["dependabot_alerts"])

    def test_archived_and_discussions_are_read_from_the_repository(self) -> None:
        state, _ = observe_with()
        self.assertEqual((state.archived, state.discussions), (False, True))

    def test_alerts_that_answer_204_are_enabled(self) -> None:
        state, _ = observe_with(**{"repos/o/r/vulnerability-alerts": (0, "", "")})
        self.assertTrue(state.security["dependabot_alerts"])

    def test_a_non_admin_reads_labels_but_neither_security_nor_rulesets(self) -> None:
        repo = {**REPO, "permissions": {"admin": False, "push": True}}
        runner = Runner({"repos/o/r": (0, json.dumps(repo), "")})
        state = GhEtabli(runner=runner).observe("o/r")
        self.assertFalse(state.admin)
        self.assertTrue(state.push)
        self.assertEqual((state.security, state.rulesets), ({}, ()))
        paths = [argv[1] for argv, _ in runner.calls if argv[:1] == ["api"]]
        self.assertFalse(any("rulesets" in path or "vulnerability" in path for path in paths))

    def test_repository_rulesets_are_read_in_detail_and_inherited_ones_left_out(self) -> None:
        summaries = [{"id": 1, "name": "main", "source_type": "Repository"},
                     {"id": 2, "name": "org", "source_type": "Organization"}]
        state, runner = observe_with(**{
            "repos/o/r/rulesets?includes_parents=false&per_page=100": (0, json.dumps(summaries), ""),
            "repos/o/r/rulesets/1": (0, json.dumps({"id": 1, "name": "main", "rules": []}), ""),
        })
        self.assertEqual([ruleset["name"] for ruleset in state.rulesets], ["main"])
        self.assertNotIn("repos/o/r/rulesets/2", [argv[1] for argv, _ in runner.calls])

    def test_a_failing_read_raises_instead_of_returning_an_empty_state(self) -> None:
        runner = Runner({"repos/o/r": (1, "", "gh: Not Found (HTTP 404)")})
        with self.assertRaises(GhEtabliError):
            GhEtabli(runner=runner).observe("o/r")


class Running(unittest.TestCase):
    def test_a_missing_gh_is_an_error_not_a_crash(self) -> None:
        with self.assertRaises(GhEtabliError):
            GhEtabli(executable="gh-that-does-not-exist-anywhere").observe("o/r")

    def test_a_timeout_is_an_error_that_says_the_state_is_unknown(self) -> None:
        expired = subprocess.TimeoutExpired(cmd=["gh"], timeout=60)
        with mock.patch("forgeron.gh_etabli.subprocess.run", side_effect=expired):
            with self.assertRaises(GhEtabliError) as caught:
                GhEtabli().apply(Change("o/r", "labels", Kind.DELETE, "wontfix"))
        self.assertIn("unknown", str(caught.exception))


class Applying(unittest.TestCase):
    def sent(self, change: Change) -> tuple[list[str], dict | None]:
        runner = Runner()
        GhEtabli(runner=runner).apply(change)
        (argv, stdin), = runner.calls
        return argv, json.loads(stdin) if stdin else None

    def test_a_rename_patches_the_old_name_with_new_name(self) -> None:
        argv, body = self.sent(Change("o/r", "labels", Kind.RENAME, "good first issue",
                                      after={"name": "type:good", "color": "7057ff", "description": "d"}))
        self.assertEqual(argv[:4], ["api", "-X", "PATCH", "repos/o/r/labels/good%20first%20issue"])
        self.assertEqual(body, {"new_name": "type:good", "color": "7057ff", "description": "d"})

    def test_a_label_name_with_a_colon_is_encoded(self) -> None:
        argv, _ = self.sent(Change("o/r", "labels", Kind.DELETE, "forgeron:hold"))
        self.assertEqual(argv[:4], ["api", "-X", "DELETE", "repos/o/r/labels/forgeron%3Ahold"])

    def test_push_protection_goes_through_security_and_analysis(self) -> None:
        argv, body = self.sent(Change("o/r", "security", Kind.UPDATE, "secret_scanning_push_protection",
                                      before=False, after=True))
        self.assertEqual(argv[:4], ["api", "-X", "PATCH", "repos/o/r"])
        self.assertEqual(body, {"security_and_analysis": {
            "secret_scanning_push_protection": {"status": "enabled"}}})

    def test_dependabot_alerts_are_a_put_without_body(self) -> None:
        argv, body = self.sent(Change("o/r", "security", Kind.UPDATE, "dependabot_alerts",
                                      before=False, after=True))
        self.assertEqual(argv, ["api", "-X", "PUT", "repos/o/r/vulnerability-alerts"])
        self.assertIsNone(body)

    def test_a_ruleset_update_puts_the_whole_ruleset_at_its_id(self) -> None:
        ruleset = {"name": "main", "target": "branch", "enforcement": "active", "rules": [],
                   "bypass_actors": []}
        argv, body = self.sent(Change("o/r", "rulesets", Kind.UPDATE, "main", before={"id": 42},
                                      after=ruleset))
        self.assertEqual(argv[:4], ["api", "-X", "PUT", "repos/o/r/rulesets/42"])
        self.assertEqual(body, ruleset)

    def test_a_non_write_change_is_refused(self) -> None:
        with self.assertRaises(GhEtabliError):
            GhEtabli(runner=Runner()).apply(Change("o/r", "labels", Kind.UNLISTED, "wontfix"))

    def test_settings_go_out_in_one_patch_with_every_key(self) -> None:
        argv, body = self.sent(Change("o/r", "settings", Kind.UPDATE, "settings",
                                      before={"merge_commit_title": "MERGE_MESSAGE",
                                              "merge_commit_message": "PR_TITLE"},
                                      after={"merge_commit_title": "PR_TITLE",
                                             "merge_commit_message": "PR_BODY"}))
        self.assertEqual(argv[:4], ["api", "-X", "PATCH", "repos/o/r"])
        self.assertEqual(body, {"merge_commit_title": "PR_TITLE", "merge_commit_message": "PR_BODY"})

    def test_a_refused_write_raises(self) -> None:
        runner = Runner({"repos/o/r": (1, "", "gh: Forbidden (HTTP 403)")})
        with self.assertRaises(GhEtabliError) as caught:
            GhEtabli(runner=runner).apply(Change("o/r", "settings", Kind.UPDATE, "settings",
                                                 before={"allow_merge_commit": True},
                                                 after={"allow_merge_commit": False}))
        self.assertIn("403", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
