from __future__ import annotations

import json
import pathlib
import unittest

from forgeron.etabli import (ConfigError, Desired, Kind, Label, Observed, ObservedLabel, load,
                             parse, plan, ruleset_differences)

ROOT = pathlib.Path(__file__).resolve().parents[1]

BUG = Label("type:bug", "d73a4a", "Something does not do what it promises")
FEATURE = Label("type:feature", "a2eeef", "A new capability")

MAIN = {
    "name": "main",
    "target": "branch",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
              {"type": "pull_request", "parameters": {"required_approving_review_count": 0,
                                                      "allowed_merge_methods": ["merge"]}}],
    "bypass_actors": [],
}


def observed(**changes) -> Observed:
    base = {"slug": "o/r", "admin": True, "push": True}
    base.update(changes)
    return Observed(**base)


def desired(**changes) -> Desired:
    base = {"slug": "o/r"}
    base.update(changes)
    return Desired(**base)


def seen(name: str, color: str = "d73a4a", description: str = "", uses: int = 0) -> ObservedLabel:
    return ObservedLabel(name=name, color=color, description=description, uses=uses)


def kinds(changes) -> list[tuple[Kind, str]]:
    return [(change.kind, change.name) for change in changes]


def as_api(ruleset: dict, **extra) -> dict:
    copy = json.loads(json.dumps(ruleset))
    copy.update({"id": 42, "source_type": "Repository", "source": "o/r", "node_id": "RRS_x",
                 "created_at": "2026-09-30T00:00:00Z"})
    for rule in copy["rules"]:
        if rule["type"] == "pull_request":
            rule["parameters"].update({"dismiss_stale_reviews_on_push": False,
                                       "required_reviewers": []})
    copy.update(extra)
    return copy


class Labels(unittest.TestCase):
    def test_a_missing_label_is_created_with_its_color_and_description(self) -> None:
        changes = plan(desired(labels=(BUG,)), observed())
        self.assertEqual(kinds(changes), [(Kind.CREATE, "type:bug")])
        self.assertEqual(changes[0].after, {"name": "type:bug", "color": "d73a4a",
                                            "description": BUG.description})

    def test_a_label_already_right_proposes_nothing(self) -> None:
        present = seen("type:bug", "D73A4A", BUG.description)
        self.assertEqual(plan(desired(labels=(BUG,)), observed(labels=(present,))), [])

    def test_a_different_color_or_description_is_an_update(self) -> None:
        present = seen("type:bug", "ffffff", "old words")
        changes = plan(desired(labels=(BUG,)), observed(labels=(present,)))
        self.assertEqual(kinds(changes), [(Kind.UPDATE, "type:bug")])

    def test_names_match_whatever_their_case_and_the_case_is_corrected(self) -> None:
        present = seen("Type:Bug", "d73a4a", BUG.description)
        changes = plan(desired(labels=(BUG,)), observed(labels=(present,)))
        self.assertEqual(kinds(changes), [(Kind.UPDATE, "Type:Bug")])
        self.assertEqual(changes[0].after["name"], "type:bug")

    def test_a_rename_keeps_the_items_instead_of_deleting_and_creating(self) -> None:
        present = seen("bug", "d73a4a", "Something isn't working", uses=7)
        changes = plan(desired(labels=(BUG,), renames=(("bug", "type:bug"),)),
                       observed(labels=(present,)))
        self.assertEqual(kinds(changes), [(Kind.RENAME, "bug")])
        self.assertEqual(changes[0].after["name"], "type:bug")
        self.assertIn("7", changes[0].note)

    def test_a_rename_whose_target_exists_is_blocked_and_touches_nothing(self) -> None:
        labels = (seen("bug", uses=3), seen("type:bug", "d73a4a", BUG.description))
        changes = plan(desired(labels=(BUG,), renames=(("bug", "type:bug"),)),
                       observed(labels=labels))
        self.assertEqual(kinds(changes), [(Kind.BLOCKED, "bug")])

    def test_two_renames_to_one_target_rename_the_first_and_block_the_second(self) -> None:
        labels = (seen("enhancement", uses=2), seen("feat", uses=5))
        changes = plan(desired(labels=(FEATURE,),
                               renames=(("enhancement", "type:feature"), ("feat", "type:feature"))),
                       observed(labels=labels))
        self.assertEqual(kinds(changes), [(Kind.RENAME, "enhancement"), (Kind.BLOCKED, "feat")])

    def test_an_undeclared_label_is_reported_with_how_many_items_carry_it(self) -> None:
        changes = plan(desired(labels=(BUG,)),
                       observed(labels=(seen("type:bug", "d73a4a", BUG.description),
                                        seen("wontfix", uses=4))))
        self.assertEqual(kinds(changes), [(Kind.UNLISTED, "wontfix")])
        self.assertIn("4", changes[0].note)

    def test_delete_unused_deletes_only_a_label_no_item_carries(self) -> None:
        changes = plan(desired(unlisted_labels="delete-unused"),
                       observed(labels=(seen("invalid", uses=0), seen("wontfix", uses=1))))
        self.assertEqual(kinds(changes), [(Kind.DELETE, "invalid"), (Kind.BLOCKED, "wontfix")])

    def test_without_write_access_labels_are_skipped_not_attempted(self) -> None:
        changes = plan(desired(labels=(BUG,)), observed(admin=False, push=False))
        self.assertEqual(kinds(changes), [(Kind.SKIPPED, "*")])


class Settings(unittest.TestCase):
    def test_only_the_settings_that_differ_are_proposed(self) -> None:
        changes = plan(desired(settings={"allow_merge_commit": True, "allow_squash_merge": False}),
                       observed(settings={"allow_merge_commit": True, "allow_squash_merge": True}))
        self.assertEqual(kinds(changes), [(Kind.UPDATE, "allow_squash_merge")])
        self.assertEqual((changes[0].before, changes[0].after), (True, False))

    def test_a_non_admin_is_skipped_for_settings_security_and_rulesets(self) -> None:
        changes = plan(desired(settings={"allow_merge_commit": True},
                               security={"secret_scanning": True}, rulesets=(MAIN,)),
                       observed(admin=False, push=True))
        self.assertEqual([(change.domain, change.kind) for change in changes],
                         [("settings", Kind.SKIPPED), ("security", Kind.SKIPPED),
                          ("rulesets", Kind.SKIPPED)])


class Security(unittest.TestCase):
    def test_protections_are_enabled_in_the_order_the_forge_requires(self) -> None:
        wanted = {key: True for key in ("private_vulnerability_reporting", "dependabot_security_updates",
                                        "secret_scanning_push_protection", "dependabot_alerts",
                                        "secret_scanning")}
        changes = plan(desired(security=wanted), observed(security={key: False for key in wanted}))
        self.assertEqual([change.name for change in changes],
                         ["secret_scanning", "secret_scanning_push_protection", "dependabot_alerts",
                          "dependabot_security_updates", "private_vulnerability_reporting"])

    def test_an_unreadable_state_is_blocked_rather_than_read_as_off(self) -> None:
        changes = plan(desired(security={"dependabot_alerts": True}),
                       observed(security={"dependabot_alerts": None}))
        self.assertEqual(kinds(changes), [(Kind.BLOCKED, "dependabot_alerts")])

    def test_removing_a_protection_is_refused(self) -> None:
        changes = plan(desired(security={"secret_scanning_push_protection": False}),
                       observed(security={"secret_scanning_push_protection": True}))
        self.assertEqual(kinds(changes), [(Kind.BLOCKED, "secret_scanning_push_protection")])


class Rulesets(unittest.TestCase):
    def test_a_missing_ruleset_is_created(self) -> None:
        changes = plan(desired(rulesets=(MAIN,)), observed())
        self.assertEqual(kinds(changes), [(Kind.CREATE, "main")])

    def test_the_same_ruleset_read_back_with_the_api_extra_fields_proposes_nothing(self) -> None:
        self.assertEqual(plan(desired(rulesets=(MAIN,)), observed(rulesets=(as_api(MAIN),))), [])

    def test_a_rule_present_on_the_forge_but_not_declared_is_an_update(self) -> None:
        extra = as_api(MAIN)
        extra["rules"].append({"type": "required_linear_history"})
        changes = plan(desired(rulesets=(MAIN,)), observed(rulesets=(extra,)))
        self.assertEqual(kinds(changes), [(Kind.UPDATE, "main")])
        self.assertIn("- rule required_linear_history", changes[0].note)
        self.assertEqual(changes[0].before, {"id": 42})

    def test_a_bypass_list_that_differs_is_shown_because_a_put_replaces_it(self) -> None:
        present = as_api(MAIN, bypass_actors=[{"actor_id": 5, "actor_type": "RepositoryRole",
                                               "bypass_mode": "always"}])
        differences = ruleset_differences(MAIN, present)
        self.assertEqual(len(differences), 1)
        self.assertTrue(differences[0].startswith("bypass"))

    def test_an_undeclared_ruleset_is_reported_and_an_inherited_one_ignored(self) -> None:
        other = as_api(MAIN, name="tags")
        inherited = as_api(MAIN, name="org-wide", source_type="Organization")
        changes = plan(desired(rulesets=(MAIN,)),
                       observed(rulesets=(as_api(MAIN), other, inherited)))
        self.assertEqual(kinds(changes), [(Kind.UNLISTED, "tags")])


class Configuration(unittest.TestCase):
    def test_the_example_shipped_with_forgeron_parses(self) -> None:
        loaded = load(str(ROOT / "etabli.example.json"))
        self.assertGreaterEqual(len(loaded), 2)
        self.assertTrue(all(want.labels and want.rulesets for want in loaded))

    def test_a_repository_adds_its_labels_to_the_defaults(self) -> None:
        (want,) = parse({"defaults": {"labels": {"type:bug": {"color": "d73a4a", "description": "x"}}},
                         "repos": {"o/r": {"labels": {"zone:net": {"color": "c5def5",
                                                                   "description": "y"}}}}})
        self.assertEqual([label.name for label in want.labels], ["type:bug", "zone:net"])

    def test_required_checks_join_every_branch_ruleset(self) -> None:
        (want,) = parse({"defaults": {"rulesets": [MAIN]},
                         "repos": {"o/r": {"required_checks": ["test"]}}})
        rule = [rule for rule in want.rulesets[0]["rules"] if rule["type"] == "required_status_checks"]
        self.assertEqual(rule[0]["parameters"]["required_status_checks"], [{"context": "test"}])
        self.assertNotIn("required_status_checks", [rule["type"] for rule in MAIN["rules"]])

    def test_errors_name_the_path_of_what_is_wrong(self) -> None:
        cases = [
            ({"repos": {"o/r": {"colour": {}}}}, "etabli.repos.o/r: unknown key(s) colour"),
            ({"repos": {"o/r": {"labels": {"x": {"color": "red", "description": "d"}}}}},
             "etabli.repos.o/r.labels.x.color"),
            ({"repos": {"o/r": {"labels": {"x": {"color": "d73a4a"}}}}},
             "etabli.repos.o/r.labels.x.description"),
            ({"repos": {"o/r": {"renames": {"bug": "type:bug"}}}}, "is not a declared label"),
            ({"repos": {"not-a-slug": {}}}, "is not of the form owner/name"),
            ({"repos": {}}, "at least one repository"),
            ({"defaults": {"security": {"secret_scanning": "yes"}}, "repos": {"o/r": {}}},
             "etabli.defaults.security.secret_scanning"),
        ]
        for raw, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(ConfigError) as caught:
                    parse(raw)
                self.assertIn(expected, str(caught.exception))

    def test_a_repository_with_its_own_vocabulary_keeps_only_the_other_domains(self) -> None:
        (want,) = parse({"defaults": {"labels": {"type:bug": {"color": "d73a4a", "description": "x"}}},
                         "repos": {"o/r": {"only": ["settings", "security", "rulesets"]}}})
        self.assertEqual(want.domains, ("settings", "security", "rulesets"))
        present = observed(labels=(seen("feat", uses=3),))
        self.assertEqual(plan(want, present), [])

    def test_an_unknown_domain_in_only_is_refused(self) -> None:
        with self.assertRaises(ConfigError) as caught:
            parse({"repos": {"o/r": {"only": ["labels", "colours"]}}})
        self.assertIn("etabli.repos.o/r.only", str(caught.exception))

    def test_two_labels_that_differ_only_by_case_are_refused(self) -> None:
        with self.assertRaises(ConfigError):
            parse({"repos": {"o/r": {"labels": {"Bug": {"color": "d73a4a", "description": "a"},
                                                "bug": {"color": "d73a4a", "description": "b"}}}}})


if __name__ == "__main__":
    unittest.main()
