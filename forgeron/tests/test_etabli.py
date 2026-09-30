from __future__ import annotations

import json
import pathlib
import unittest

from forgeron.etabli import (ConfigError, Desired, Kind, Label, Observed, ObservedLabel, load,
                             parse, plan, ruleset_differences)

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

BUG = Label("type:bug", "d73a4a", "Something does not do what it promises")
FEATURE = Label("type:feature", "a2eeef", "A new capability")

PULL_REQUEST = {"required_approving_review_count": 0, "dismiss_stale_reviews_on_push": False,
                "require_code_owner_review": False, "require_last_push_approval": False,
                "required_review_thread_resolution": False, "allowed_merge_methods": ["merge"]}

MAIN = {
    "name": "main",
    "target": "branch",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
              {"type": "pull_request", "parameters": dict(PULL_REQUEST)}],
    "bypass_actors": [],
}

ADMIN_ON_PULL_REQUESTS = {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}


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


def copy(value):
    return json.loads(json.dumps(value))


def as_api(ruleset: dict, **extra) -> dict:
    read = copy(ruleset)
    read.update({"id": 42, "source_type": "Repository", "source": "o/r", "node_id": "RRS_x",
                 "created_at": "2026-09-30T00:00:00Z", "current_user_can_bypass": "never"})
    for rule in read["rules"]:
        if rule["type"] == "pull_request":
            rule["parameters"].update({"required_reviewers": [],
                                       "dismissal_restriction": {"enabled": False, "allowed_actors": []}})
    read.update(extra)
    return read


def real_ruleset() -> dict:
    read = json.loads((FIXTURES / "ruleset-nextjs.json").read_text(encoding="utf-8"))
    read["bypass_actors"] = read.get("bypass_actors") or []
    return read


def declared_from(read: dict, drop: tuple[str, ...] = ()) -> dict:
    declared = {key: copy(read[key]) for key in ("name", "target", "enforcement", "conditions", "rules",
                                                  "bypass_actors")}
    for rule in declared["rules"]:
        parameters = rule.get("parameters") or {}
        for key in drop:
            parameters.pop(key, None)
    return declared


def pull_request_of(ruleset: dict) -> dict:
    return next(rule for rule in ruleset["rules"] if rule["type"] == "pull_request")["parameters"]


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
        self.assertEqual(changes[0].before["description"], "Something isn't working")
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

    def test_delete_unused_never_deletes_when_discussions_may_carry_the_label(self) -> None:
        changes = plan(desired(unlisted_labels="delete-unused"),
                       observed(discussions=True, labels=(seen("invalid", uses=0),)))
        self.assertEqual(kinds(changes), [(Kind.BLOCKED, "invalid")])
        self.assertIn("discussions", changes[0].note)

    def test_without_write_access_labels_are_skipped_not_attempted(self) -> None:
        changes = plan(desired(labels=(BUG,)), observed(admin=False, push=False))
        self.assertEqual(kinds(changes), [(Kind.SKIPPED, "*")])


class Settings(unittest.TestCase):
    def test_every_setting_that_differs_goes_in_one_change(self) -> None:
        changes = plan(desired(settings={"allow_merge_commit": True, "allow_squash_merge": False,
                                         "allow_rebase_merge": False}),
                       observed(settings={"allow_merge_commit": True, "allow_squash_merge": True,
                                          "allow_rebase_merge": True}))
        self.assertEqual(kinds(changes), [(Kind.UPDATE, "settings")])
        self.assertEqual(changes[0].after, {"allow_squash_merge": False, "allow_rebase_merge": False})
        self.assertEqual(changes[0].before, {"allow_squash_merge": True, "allow_rebase_merge": True})

    def test_half_of_a_commit_message_pair_carries_the_other_half(self) -> None:
        changes = plan(desired(settings={"merge_commit_title": "PR_TITLE", "merge_commit_message": "PR_BODY"}),
                       observed(settings={"merge_commit_title": "PR_TITLE", "merge_commit_message": "PR_TITLE"}))
        self.assertEqual(changes[0].after, {"merge_commit_title": "PR_TITLE",
                                            "merge_commit_message": "PR_BODY"})

    def test_a_non_admin_is_skipped_for_settings_security_and_rulesets(self) -> None:
        changes = plan(desired(settings={"allow_merge_commit": True},
                               security={"secret_scanning": True}, rulesets=(MAIN,)),
                       observed(admin=False, push=True))
        self.assertEqual([(change.domain, change.kind) for change in changes],
                         [("settings", Kind.SKIPPED), ("security", Kind.SKIPPED),
                          ("rulesets", Kind.SKIPPED)])

    def test_an_archived_repository_is_skipped_whole(self) -> None:
        changes = plan(desired(labels=(BUG,), settings={"allow_merge_commit": True}),
                       observed(archived=True))
        self.assertEqual([(change.kind, change.domain) for change in changes],
                         [(Kind.SKIPPED, "repository")])
        self.assertIn("archived", changes[0].note)


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

    def test_a_real_ruleset_read_back_whole_proposes_nothing(self) -> None:
        read = real_ruleset()
        self.assertEqual(plan(desired(rulesets=(declared_from(read),)), observed(rulesets=(read,))), [])

    def test_lists_compare_whatever_their_order(self) -> None:
        read = real_ruleset()
        declared = declared_from(read)
        declared["conditions"]["ref_name"]["include"].reverse()
        next(rule for rule in declared["rules"] if rule["type"] == "required_status_checks")[
            "parameters"]["required_status_checks"].reverse()
        self.assertEqual(plan(desired(rulesets=(declared,)), observed(rulesets=(read,))), [])

    def test_a_forge_only_parameter_is_reported_and_kept(self) -> None:
        read = real_ruleset()
        declared = declared_from(read, drop=("require_extra_approval_for_unattributed_changes",))
        changes = plan(desired(rulesets=(declared,)), observed(rulesets=(read,)))
        self.assertEqual([change.kind for change in changes], [Kind.UNLISTED])
        self.assertIn("pull_request.require_extra_approval_for_unattributed_changes", changes[0].note)

    def test_an_update_that_would_drop_a_forge_only_parameter_is_blocked_and_names_it(self) -> None:
        read = real_ruleset()
        declared = declared_from(read, drop=("require_extra_approval_for_unattributed_changes",))
        pull_request_of(declared)["required_approving_review_count"] = 2
        changes = plan(desired(rulesets=(declared,)), observed(rulesets=(read,)))
        self.assertEqual([change.kind for change in changes], [Kind.BLOCKED])
        self.assertIn("require_extra_approval_for_unattributed_changes", changes[0].note)

    def test_an_update_carries_the_whole_ruleset_it_replaces(self) -> None:
        read = real_ruleset()
        declared = declared_from(read)
        pull_request_of(declared)["required_approving_review_count"] = 2
        changes = plan(desired(rulesets=(declared,)), observed(rulesets=(read,)))
        self.assertEqual(kinds(changes), [(Kind.UPDATE, read["name"])])
        self.assertEqual(changes[0].before, read)

    def test_a_ruleset_is_never_weakened_by_the_tool(self) -> None:
        cases = {
            "enforcement": dict(MAIN, enforcement="disabled"),
            "a rule the forge has": dict(MAIN, rules=[rule for rule in MAIN["rules"]
                                                      if rule["type"] != "deletion"]),
            "a new bypass": dict(MAIN, bypass_actors=[ADMIN_ON_PULL_REQUESTS]),
        }
        for label, weaker in cases.items():
            with self.subTest(label):
                changes = plan(desired(rulesets=(weaker,)), observed(rulesets=(as_api(MAIN),)))
                self.assertEqual([change.kind for change in changes], [Kind.BLOCKED])

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
                         "repos": {"o/r": {"required_checks": [
                             "test", {"context": "build", "integration_id": 15368}]}}})
        rule = [rule for rule in want.rulesets[0]["rules"] if rule["type"] == "required_status_checks"]
        self.assertEqual(rule[0]["parameters"]["required_status_checks"],
                         [{"context": "test"}, {"context": "build", "integration_id": 15368}])
        self.assertNotIn("required_status_checks", [rule["type"] for rule in MAIN["rules"]])

    def test_errors_name_the_path_of_what_is_wrong(self) -> None:
        tag_only = dict(MAIN, target="tag")
        with_checks = dict(MAIN, rules=MAIN["rules"] + [{"type": "required_status_checks", "parameters": {
            "strict_required_status_checks_policy": False, "required_status_checks": []}}])
        without_bypass = {key: value for key, value in MAIN.items() if key != "bypass_actors"}
        missing_parameter = copy(MAIN)
        del pull_request_of(missing_parameter)["require_last_push_approval"]
        cases = [
            ({"repos": {"o/r": {"colour": {}}}}, "etabli.repos.o/r: unknown key(s) colour"),
            ({"repos": {"o/r": {"labels": {"x": {"color": "red", "description": "d"}}}}},
             "etabli.repos.o/r.labels.x.color"),
            ({"repos": {"o/r": {"labels": {"x": {"color": "d73a4a"}}}}},
             "etabli.repos.o/r.labels.x.description"),
            ({"repos": {"o/r": {"labels": {"": {"color": "d73a4a", "description": "d"}}}}},
             "etabli.repos.o/r.labels: a label name"),
            ({"repos": {"o/r": {"renames": {"bug": "type:bug"}}}}, "is not a declared label"),
            ({"repos": {"o/r": {"labels": {"type:bug": {"color": "d73a4a", "description": "d"}},
                                "renames": {"bug": "type:bug", "Bug": "type:bug"}}}},
             "etabli.repos.o/r.renames"),
            ({"repos": {"not-a-slug": {}}}, "is not of the form owner/name"),
            ({"repos": {"o/r": {}, "O/R": {}}}, "etabli.repos"),
            ({"repos": {}}, "at least one repository"),
            ({"defaults": {"security": {"secret_scanning": "yes"}}, "repos": {"o/r": {}}},
             "etabli.defaults.security.secret_scanning"),
            ({"defaults": {"settings": {"allow_squash_merge": "false"}}, "repos": {"o/r": {}}},
             "etabli.defaults.settings.allow_squash_merge"),
            ({"defaults": {"settings": {"merge_commit_title": "WHATEVER",
                                        "merge_commit_message": "PR_BODY"}}, "repos": {"o/r": {}}},
             "etabli.defaults.settings.merge_commit_title"),
            ({"defaults": {"settings": {"merge_commit_title": "PR_TITLE",
                                        "merge_commit_message": "PR_TITLE"}}, "repos": {"o/r": {}}},
             "merge_commit_title and merge_commit_message"),
            ({"defaults": {"settings": {"merge_commit_title": "PR_TITLE"}}, "repos": {"o/r": {}}},
             "merge_commit_title and merge_commit_message"),
            ({"defaults": {"settings": {"has_discussions": True}}, "repos": {"o/r": {}}},
             "unknown key(s) has_discussions"),
            ({"defaults": {"rulesets": [without_bypass]}, "repos": {"o/r": {}}}, "\"bypass_actors\" is missing"),
            ({"defaults": {"rulesets": [dict(MAIN, bypass_actor=[])]}, "repos": {"o/r": {}}},
             "unknown key(s) bypass_actor"),
            ({"defaults": {"rulesets": [dict(MAIN, rules=["deletion"])]}, "repos": {"o/r": {}}},
             "etabli.defaults.rulesets[0].rules[0]"),
            ({"defaults": {"rulesets": [dict(MAIN, enforcement="on")]}, "repos": {"o/r": {}}},
             "etabli.defaults.rulesets[0].enforcement"),
            ({"defaults": {"rulesets": [missing_parameter]}, "repos": {"o/r": {}}},
             "require_last_push_approval"),
            ({"defaults": {"rulesets": [tag_only]}, "repos": {"o/r": {"required_checks": ["test"]}}},
             "etabli.repos.o/r.required_checks"),
            ({"defaults": {"rulesets": [with_checks]}, "repos": {"o/r": {"required_checks": ["test"]}}},
             "etabli.repos.o/r.required_checks"),
        ]
        for raw, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(ConfigError) as caught:
                    parse(raw)
                self.assertIn(expected, str(caught.exception))

    def test_two_labels_that_differ_only_by_case_are_refused(self) -> None:
        with self.assertRaises(ConfigError):
            parse({"repos": {"o/r": {"labels": {"Bug": {"color": "d73a4a", "description": "a"},
                                                "bug": {"color": "d73a4a", "description": "b"}}}}})

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


if __name__ == "__main__":
    unittest.main()
