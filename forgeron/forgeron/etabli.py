from __future__ import annotations

import dataclasses
import enum
import json
import re
from typing import Any

DOMAINS = ("labels", "settings", "security", "rulesets")

BOOLEAN_SETTINGS = frozenset({
    "allow_squash_merge", "allow_merge_commit", "allow_rebase_merge", "allow_auto_merge",
    "allow_update_branch", "delete_branch_on_merge", "web_commit_signoff_required", "has_issues",
    "has_projects", "has_wiki",
})

CHOICE_SETTINGS = {
    "squash_merge_commit_title": ("PR_TITLE", "COMMIT_OR_PR_TITLE"),
    "squash_merge_commit_message": ("PR_BODY", "COMMIT_MESSAGES", "BLANK"),
    "merge_commit_title": ("PR_TITLE", "MERGE_MESSAGE"),
    "merge_commit_message": ("PR_BODY", "PR_TITLE", "BLANK"),
}

SETTINGS_KEYS = BOOLEAN_SETTINGS | frozenset(CHOICE_SETTINGS)

MESSAGE_PAIRS = {
    ("merge_commit_title", "merge_commit_message"): (
        ("PR_TITLE", "PR_BODY"), ("PR_TITLE", "BLANK"), ("MERGE_MESSAGE", "PR_TITLE"),
    ),
    ("squash_merge_commit_title", "squash_merge_commit_message"): (
        ("PR_TITLE", "PR_BODY"), ("PR_TITLE", "BLANK"), ("PR_TITLE", "COMMIT_MESSAGES"),
        ("COMMIT_OR_PR_TITLE", "COMMIT_MESSAGES"),
    ),
}

SECURITY_KEYS = (
    "secret_scanning", "secret_scanning_push_protection", "dependabot_alerts",
    "dependabot_security_updates", "private_vulnerability_reporting",
)

UNLISTED_POLICIES = ("report", "delete-unused")

REPO_KEYS = frozenset({"labels", "renames", "unlisted_labels", "settings", "security", "rulesets",
                       "required_checks", "only"})
DEFAULT_KEYS = REPO_KEYS - {"required_checks", "only"}

RULESET_KEYS = ("name", "target", "enforcement", "conditions", "rules", "bypass_actors")
RULESET_REQUIRED = ("name", "target", "enforcement", "rules", "bypass_actors")
TARGETS = ("branch", "tag", "push")
ENFORCEMENTS = ("active", "evaluate", "disabled")
PULL_REQUEST_REQUIRED = ("dismiss_stale_reviews_on_push", "require_code_owner_review",
                         "require_last_push_approval", "required_approving_review_count",
                         "required_review_thread_resolution")
ACTOR_TYPES = ("Integration", "OrganizationAdmin", "RepositoryRole", "Team", "DeployKey")
BYPASS_MODES = ("always", "pull_request", "exempt")
BYPASS_MODES_BY_REACH = ("pull_request", "always", "exempt")
API_ONLY_KEYS = frozenset({"id", "source", "source_type", "node_id", "_links", "created_at",
                           "updated_at", "current_user_can_bypass"})

_COLOR = re.compile(r"^[0-9a-f]{6}$")
_SLUG = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ConfigError(ValueError):
    pass


class Kind(enum.Enum):
    CREATE = "+"
    UPDATE = "~"
    RENAME = ">"
    DELETE = "-"
    UNLISTED = "?"
    BLOCKED = "!"
    SKIPPED = "."

    @property
    def actionable(self) -> bool:
        return self in (Kind.CREATE, Kind.UPDATE, Kind.RENAME, Kind.DELETE)


@dataclasses.dataclass(frozen=True)
class Label:
    name: str
    color: str
    description: str


@dataclasses.dataclass(frozen=True)
class Desired:
    slug: str
    labels: tuple[Label, ...] = ()
    renames: tuple[tuple[str, str], ...] = ()
    unlisted_labels: str = "report"
    settings: dict[str, Any] = dataclasses.field(default_factory=dict)
    security: dict[str, bool] = dataclasses.field(default_factory=dict)
    rulesets: tuple[dict[str, Any], ...] = ()
    domains: tuple[str, ...] = DOMAINS


@dataclasses.dataclass(frozen=True)
class ObservedLabel:
    name: str
    color: str
    description: str
    uses: int


@dataclasses.dataclass(frozen=True)
class Observed:
    slug: str
    admin: bool
    push: bool
    labels: tuple[ObservedLabel, ...] = ()
    settings: dict[str, Any] = dataclasses.field(default_factory=dict)
    security: dict[str, bool | None] = dataclasses.field(default_factory=dict)
    rulesets: tuple[dict[str, Any], ...] = ()
    archived: bool = False
    discussions: bool = False


@dataclasses.dataclass(frozen=True)
class Change:
    repo: str
    domain: str
    kind: Kind
    name: str
    before: Any = None
    after: Any = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"repo": self.repo, "domain": self.domain, "kind": self.kind.name.lower(),
                "name": self.name, "before": self.before, "after": self.after, "note": self.note}


def load(path: str) -> tuple[Desired, ...]:
    with open(path, encoding="utf-8") as handle:
        try:
            raw = json.load(handle)
        except json.JSONDecodeError as failure:
            raise ConfigError(f"{path}: invalid JSON at line {failure.lineno}: {failure.msg}")
    return parse(raw, source=path)


def parse(raw: Any, source: str = "etabli") -> tuple[Desired, ...]:
    if not isinstance(raw, dict):
        raise ConfigError(f"{source}: a JSON object is expected at the root")
    _refuse_unknown(raw, {"defaults", "repos"}, source)
    defaults = raw.get("defaults", {})
    repos = raw.get("repos")
    if not isinstance(defaults, dict):
        raise ConfigError(f"{source}.defaults: an object is expected")
    _refuse_unknown(defaults, DEFAULT_KEYS, f"{source}.defaults")
    if not isinstance(repos, dict) or not repos:
        raise ConfigError(f"{source}.repos: at least one repository is expected, as "
                          f"\"owner/name\": {{}}")
    _refuse_case_twins(repos, f"{source}.repos", "repository")
    base = {
        "labels": _labels(defaults.get("labels", {}), f"{source}.defaults.labels"),
        "renames": _renames(defaults.get("renames", {}), f"{source}.defaults.renames"),
        "unlisted_labels": defaults.get("unlisted_labels", "report"),
        "settings": _settings(defaults.get("settings", {}), f"{source}.defaults.settings"),
        "security": _security(defaults.get("security", {}), f"{source}.defaults.security"),
        "rulesets": _rulesets(defaults.get("rulesets", []), f"{source}.defaults.rulesets"),
    }
    return tuple(_desired(slug, base, entry, f"{source}.repos.{slug}")
                 for slug, entry in repos.items())


def _desired(slug: str, base: dict[str, Any], entry: Any, where: str) -> Desired:
    if not _SLUG.match(slug):
        raise ConfigError(f"{where}: \"{slug}\" is not of the form owner/name")
    if not isinstance(entry, dict):
        raise ConfigError(f"{where}: an object is expected")
    _refuse_unknown(entry, REPO_KEYS, where)

    labels = {**base["labels"], **_labels(entry.get("labels", {}), f"{where}.labels")}
    renames = {**base["renames"], **_renames(entry.get("renames", {}), f"{where}.renames")}
    _refuse_case_twins(labels, f"{where}.labels", "label")
    _refuse_case_twins(renames, f"{where}.renames", "label")
    declared = {name.lower() for name in labels}
    for old, new in renames.items():
        if new.lower() not in declared:
            raise ConfigError(f"{where}.renames: \"{old}\" -> \"{new}\", but \"{new}\" is not "
                              f"a declared label")
        if old.lower() in declared and old.lower() != new.lower():
            raise ConfigError(f"{where}.renames: \"{old}\" is both declared and renamed")

    policy = entry.get("unlisted_labels", base["unlisted_labels"])
    if policy not in UNLISTED_POLICIES:
        raise ConfigError(f"{where}.unlisted_labels: \"{policy}\", expected one of: "
                          f"{', '.join(UNLISTED_POLICIES)}")

    settings = {**base["settings"], **_settings(entry.get("settings", {}), f"{where}.settings")}
    _check_message_pairs(settings, f"{where}.settings")
    security = {**base["security"], **_security(entry.get("security", {}), f"{where}.security")}
    rulesets = (_rulesets(entry["rulesets"], f"{where}.rulesets") if "rulesets" in entry
                else base["rulesets"])
    rulesets = _with_required_checks(rulesets, entry.get("required_checks", []),
                                     f"{where}.required_checks")

    only = entry.get("only", list(DOMAINS))
    if not isinstance(only, list) or not only or any(domain not in DOMAINS for domain in only):
        raise ConfigError(f"{where}.only: {only!r}, expected a list among {', '.join(DOMAINS)}")

    return Desired(
        slug=slug,
        labels=tuple(labels.values()),
        renames=tuple(renames.items()),
        unlisted_labels=policy,
        settings=settings,
        security=security,
        rulesets=rulesets,
        domains=tuple(domain for domain in DOMAINS if domain in only),
    )


def _refuse_unknown(value: dict[str, Any], allowed, where: str) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise ConfigError(f"{where}: unknown key(s) {', '.join(unknown)}; "
                          f"expected: {', '.join(sorted(allowed))}")


def _refuse_case_twins(names, where: str, what: str) -> None:
    seen: dict[str, str] = {}
    for name in names:
        twin = seen.setdefault(name.lower(), name)
        if twin != name:
            raise ConfigError(f"{where}: \"{twin}\" and \"{name}\" are the same {what} for the forge, "
                              f"which ignores case")


def _labels(raw: Any, where: str) -> dict[str, Label]:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: an object {{\"name\": {{\"color\", \"description\"}}}} is expected")
    labels: dict[str, Label] = {}
    for name, spec in raw.items():
        if not name.strip():
            raise ConfigError(f"{where}: a label name cannot be empty")
        if not isinstance(spec, dict):
            raise ConfigError(f"{where}.{name}: an object is expected")
        _refuse_unknown(spec, {"color", "description"}, f"{where}.{name}")
        color = str(spec.get("color", "")).lower().lstrip("#")
        if not _COLOR.match(color):
            raise ConfigError(f"{where}.{name}.color: \"{spec.get('color')}\", expected six hexadecimal "
                              f"digits such as d73a4a")
        description = spec.get("description", "")
        if not isinstance(description, str) or not description.strip():
            raise ConfigError(f"{where}.{name}.description: required, it is what shows on hover "
                              f"and in the label picker")
        if len(description) > 100:
            raise ConfigError(f"{where}.{name}.description: {len(description)} characters, "
                              f"the forge accepts 100")
        labels[name] = Label(name=name, color=color, description=description)
    return labels


def _renames(raw: Any, where: str) -> dict[str, str]:
    if not isinstance(raw, dict) or any(not isinstance(value, str) for value in raw.values()):
        raise ConfigError(f"{where}: an object {{\"old name\": \"new name\"}} is expected")
    return dict(raw)


def _settings(raw: Any, where: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: an object is expected")
    _refuse_unknown(raw, SETTINGS_KEYS, where)
    for key, value in raw.items():
        if key in BOOLEAN_SETTINGS and not isinstance(value, bool):
            raise ConfigError(f"{where}.{key}: true or false, not {value!r}")
        if key in CHOICE_SETTINGS and value not in CHOICE_SETTINGS[key]:
            raise ConfigError(f"{where}.{key}: {value!r}, expected one of: "
                              f"{', '.join(CHOICE_SETTINGS[key])}")
    return dict(raw)


def _check_message_pairs(settings: dict[str, Any], where: str) -> None:
    for (title, message), valid in MESSAGE_PAIRS.items():
        present = [key for key in (title, message) if key in settings]
        if not present:
            continue
        combinations = ", ".join(f"{first}+{second}" for first, second in valid)
        if len(present) == 1 or (settings[title], settings[message]) not in valid:
            raise ConfigError(f"{where}: {title} and {message} are declared together, as one of: "
                              f"{combinations}")


def _security(raw: Any, where: str) -> dict[str, bool]:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: an object is expected")
    _refuse_unknown(raw, set(SECURITY_KEYS), where)
    for key, value in raw.items():
        if not isinstance(value, bool):
            raise ConfigError(f"{where}.{key}: true or false, not {value!r}")
    return dict(raw)


def _rulesets(raw: Any, where: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(raw, list):
        raise ConfigError(f"{where}: a list of rulesets in the API format is expected")
    names: set[str] = set()
    for index, ruleset in enumerate(raw):
        at = f"{where}[{index}]"
        if not isinstance(ruleset, dict) or not isinstance(ruleset.get("name"), str) \
                or not ruleset["name"].strip():
            raise ConfigError(f"{at}: an object with a \"name\" is expected")
        _refuse_unknown(ruleset, RULESET_KEYS, f"{at} ({ruleset['name']})")
        for key in RULESET_REQUIRED:
            if key not in ruleset:
                raise ConfigError(f"{at} ({ruleset['name']}): \"{key}\" is missing")
        if ruleset["target"] not in TARGETS:
            raise ConfigError(f"{at}.target: {ruleset['target']!r}, expected one of: {', '.join(TARGETS)}")
        if ruleset["enforcement"] not in ENFORCEMENTS:
            raise ConfigError(f"{at}.enforcement: {ruleset['enforcement']!r}, expected one of: "
                              f"{', '.join(ENFORCEMENTS)}")
        if not isinstance(ruleset.get("conditions", {}), dict):
            raise ConfigError(f"{at}.conditions: an object is expected")
        _check_rules(ruleset["rules"], f"{at}.rules")
        _check_bypass(ruleset["bypass_actors"], f"{at}.bypass_actors")
        if ruleset["name"] in names:
            raise ConfigError(f"{where}: two rulesets are named \"{ruleset['name']}\"")
        names.add(ruleset["name"])
    return tuple(json.loads(json.dumps(ruleset)) for ruleset in raw)


def _check_rules(rules: Any, where: str) -> None:
    if not isinstance(rules, list):
        raise ConfigError(f"{where}: a list of rules is expected")
    for index, rule in enumerate(rules):
        at = f"{where}[{index}]"
        if not isinstance(rule, dict) or not isinstance(rule.get("type"), str):
            raise ConfigError(f"{at}: an object with a \"type\" is expected, not {rule!r}")
        _refuse_unknown(rule, {"type", "parameters"}, at)
        parameters = rule.get("parameters") or {}
        if not isinstance(parameters, dict):
            raise ConfigError(f"{at}.parameters: an object is expected")
        if rule["type"] == "pull_request":
            missing = [key for key in PULL_REQUEST_REQUIRED if key not in parameters]
            if missing:
                raise ConfigError(f"{at}.parameters: the forge requires {', '.join(missing)}")


def _check_bypass(actors: Any, where: str) -> None:
    if not isinstance(actors, list):
        raise ConfigError(f"{where}: a list is expected, [] for no bypass")
    for index, actor in enumerate(actors):
        at = f"{where}[{index}]"
        if not isinstance(actor, dict):
            raise ConfigError(f"{at}: an object is expected")
        _refuse_unknown(actor, {"actor_id", "actor_type", "bypass_mode"}, at)
        if actor.get("actor_type") not in ACTOR_TYPES:
            raise ConfigError(f"{at}.actor_type: {actor.get('actor_type')!r}, expected one of: "
                              f"{', '.join(ACTOR_TYPES)}")
        if actor.get("bypass_mode", "always") not in BYPASS_MODES:
            raise ConfigError(f"{at}.bypass_mode: {actor.get('bypass_mode')!r}, expected one of: "
                              f"{', '.join(BYPASS_MODES)}")


def _with_required_checks(rulesets: tuple[dict[str, Any], ...], checks: Any,
                          where: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(checks, list):
        raise ConfigError(f"{where}: a list of check names is expected")
    entries = [_check_entry(check, f"{where}[{index}]") for index, check in enumerate(checks)]
    if not entries:
        return rulesets
    branch = [ruleset for ruleset in rulesets if ruleset["target"] == "branch"]
    if not branch:
        raise ConfigError(f"{where}: no branch ruleset to add the checks to")
    for ruleset in branch:
        if any(rule.get("type") == "required_status_checks" for rule in ruleset["rules"]):
            raise ConfigError(f"{where}: ruleset \"{ruleset['name']}\" already declares "
                              f"required_status_checks; declare the checks in one place")
    rule = {"type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": False,
        "required_status_checks": entries,
    }}
    completed = []
    for ruleset in rulesets:
        ruleset = json.loads(json.dumps(ruleset))
        if ruleset["target"] == "branch":
            ruleset["rules"].append(json.loads(json.dumps(rule)))
        completed.append(ruleset)
    return tuple(completed)


def _check_entry(check: Any, where: str) -> dict[str, Any]:
    if isinstance(check, str) and check:
        return {"context": check}
    if isinstance(check, dict) and isinstance(check.get("context"), str) and check["context"] \
            and set(check) <= {"context", "integration_id"} \
            and isinstance(check.get("integration_id", 0), int):
        return dict(check)
    raise ConfigError(f"{where}: a check name, or {{\"context\", \"integration_id\"}}, not {check!r}")


def declared_domains(desired: Desired) -> tuple[str, ...]:
    declared = {
        "labels": bool(desired.labels or desired.renames),
        "settings": bool(desired.settings),
        "security": bool(desired.security),
        "rulesets": bool(desired.rulesets),
    }
    return tuple(domain for domain in desired.domains if declared[domain])


def plan(desired: Desired, observed: Observed) -> list[Change]:
    if observed.archived:
        return [Change(desired.slug, "repository", Kind.SKIPPED, "*",
                       note="archived: the repository is read-only")]
    changes: list[Change] = []
    if "labels" in desired.domains:
        changes += _plan_labels(desired, observed)
    if "settings" in desired.domains:
        changes += _plan_settings(desired, observed)
    if "security" in desired.domains:
        changes += _plan_security(desired, observed)
    if "rulesets" in desired.domains:
        changes += _plan_rulesets(desired, observed)
    return changes


def _plan_labels(desired: Desired, observed: Observed) -> list[Change]:
    repo = desired.slug
    if not observed.push:
        return [Change(repo, "labels", Kind.SKIPPED, "*", note="no write access to the repository")]

    present = {label.name.lower(): label for label in observed.labels}
    wanted = {label.name.lower(): label for label in desired.labels}
    changes: list[Change] = []
    taken: set[str] = set()
    consumed: set[str] = set()

    for old, new in desired.renames:
        source = present.get(old.lower())
        if source is None or old.lower() == new.lower():
            continue
        consumed.add(old.lower())
        if new.lower() in present:
            changes.append(Change(repo, "labels", Kind.BLOCKED, source.name,
                                  note=f"\"{new}\" already exists: move the {source.uses} item(s) of "
                                       f"\"{source.name}\" by hand"))
            continue
        if new.lower() in taken:
            changes.append(Change(repo, "labels", Kind.BLOCKED, source.name,
                                  note=f"\"{new}\" is already taken by another rename: move the "
                                       f"{source.uses} item(s) of \"{source.name}\" "
                                       f"by hand"))
            continue
        target = wanted[new.lower()]
        taken.add(new.lower())
        changes.append(Change(repo, "labels", Kind.RENAME, source.name,
                              before=_label_view(source), after=_label_view(target),
                              note=f"keeps its {source.uses} item(s)"))

    for key, label in wanted.items():
        if key in taken:
            continue
        current = present.get(key)
        if current is None:
            changes.append(Change(repo, "labels", Kind.CREATE, label.name, after=_label_view(label)))
        elif _label_view(current) != _label_view(label):
            changes.append(Change(repo, "labels", Kind.UPDATE, current.name,
                                  before=_label_view(current), after=_label_view(label)))

    for key, current in present.items():
        if key in wanted or key in consumed:
            continue
        if desired.unlisted_labels == "delete-unused" and current.uses == 0 and not observed.discussions:
            changes.append(Change(repo, "labels", Kind.DELETE, current.name, before=_label_view(current),
                                  note="undeclared, carried by no issue or pull request"))
        elif desired.unlisted_labels == "delete-unused" and current.uses == 0:
            changes.append(Change(repo, "labels", Kind.BLOCKED, current.name,
                                  note="undeclared and carried by no issue or pull request, but "
                                       "discussions are on and their labels are not counted: "
                                       "never deleted"))
        elif desired.unlisted_labels == "delete-unused":
            changes.append(Change(repo, "labels", Kind.BLOCKED, current.name,
                                  note=f"undeclared, but carried by {current.uses} item(s): "
                                       f"never deleted"))
        else:
            changes.append(Change(repo, "labels", Kind.UNLISTED, current.name,
                                  note=f"undeclared, carried by {current.uses} item(s)"))
    return changes


def _label_view(label: Label | ObservedLabel) -> dict[str, str]:
    return {"name": label.name, "color": label.color.lower(), "description": label.description or ""}


def _plan_settings(desired: Desired, observed: Observed) -> list[Change]:
    if not desired.settings:
        return []
    if not observed.admin:
        return [Change(desired.slug, "settings", Kind.SKIPPED, "*", note="requires admin on the repository")]
    differing = {key for key, value in desired.settings.items() if observed.settings.get(key) != value}
    for pair in MESSAGE_PAIRS:
        if differing & set(pair):
            differing |= {key for key in pair if key in desired.settings}
    if not differing:
        return []
    keys = [key for key in desired.settings if key in differing]
    return [Change(desired.slug, "settings", Kind.UPDATE, "settings",
                   before={key: observed.settings.get(key) for key in keys},
                   after={key: desired.settings[key] for key in keys})]


def _plan_security(desired: Desired, observed: Observed) -> list[Change]:
    if not desired.security:
        return []
    if not observed.admin:
        return [Change(desired.slug, "security", Kind.SKIPPED, "*", note="requires admin on the repository")]
    changes = []
    for key in SECURITY_KEYS:
        if key not in desired.security:
            continue
        want, have = desired.security[key], observed.security.get(key)
        if have is None:
            changes.append(Change(desired.slug, "security", Kind.BLOCKED, key,
                                  note="unreadable state: neither on nor off, nothing is proven"))
        elif have and not want:
            changes.append(Change(desired.slug, "security", Kind.BLOCKED, key, before=have, after=want,
                                  note="removing a protection is not done by this tool: do it by "
                                       "hand, with its reason written down"))
        elif have != want:
            changes.append(Change(desired.slug, "security", Kind.UPDATE, key, before=have, after=want))
    return changes


def _plan_rulesets(desired: Desired, observed: Observed) -> list[Change]:
    if not desired.rulesets:
        return []
    if not observed.admin:
        return [Change(desired.slug, "rulesets", Kind.SKIPPED, "*", note="requires admin on the repository")]
    present = {ruleset["name"]: ruleset for ruleset in observed.rulesets
               if ruleset.get("source_type", "Repository") == "Repository"}
    changes = []
    for want in desired.rulesets:
        have = present.get(want["name"])
        if have is None:
            changes.append(Change(desired.slug, "rulesets", Kind.CREATE, want["name"], after=want))
            continue
        differences = ruleset_differences(want, have)
        kept = forge_only(want, have)
        weaker = ruleset_weakening(want, have) + [f"the PUT would drop {path}" for path in kept]
        if differences and weaker:
            changes.append(Change(desired.slug, "rulesets", Kind.BLOCKED, want["name"],
                                  note="weakens the ruleset: " + " ; ".join(weaker)
                                       + ". Declare it in the file to keep it, or change it by hand "
                                         "with its reason written down"))
        elif differences:
            changes.append(Change(desired.slug, "rulesets", Kind.UPDATE, want["name"],
                                  before=have, after=want, note=" ; ".join(differences)))
        elif kept:
            changes.append(Change(desired.slug, "rulesets", Kind.UNLISTED, want["name"],
                                  note="forge-only parameters, kept: " + ", ".join(kept)))
    declared = {want["name"] for want in desired.rulesets}
    for name in present:
        if name not in declared:
            changes.append(Change(desired.slug, "rulesets", Kind.UNLISTED, name,
                                  note="undeclared, never deleted"))
    return changes


def ruleset_differences(want: dict[str, Any], have: dict[str, Any]) -> list[str]:
    differences = []
    for key in ("target", "enforcement"):
        if want.get(key) != have.get(key):
            differences.append(f"{key} {have.get(key)} -> {want.get(key)}")
    if not contains(have.get("conditions") or {}, want.get("conditions") or {}):
        differences.append("conditions")

    wanted_rules = _rules_by_type(want)
    present_rules = _rules_by_type(have)
    for kind, rule in wanted_rules.items():
        if kind not in present_rules:
            differences.append(f"+ rule {kind}")
        elif not contains(present_rules[kind].get("parameters") or {}, rule.get("parameters") or {}):
            differences.append(f"~ rule {kind}")
    for kind in present_rules:
        if kind not in wanted_rules:
            differences.append(f"- rule {kind}")

    wanted_bypass = _bypass(want)
    present_bypass = _bypass(have)
    if wanted_bypass != present_bypass:
        differences.append(f"bypass {sorted(present_bypass, key=str)} -> {sorted(wanted_bypass, key=str)}")
    return differences


def ruleset_weakening(want: dict[str, Any], have: dict[str, Any]) -> list[str]:
    weaker = []
    rank = {mode: position for position, mode in enumerate(ENFORCEMENTS)}
    if rank.get(want.get("enforcement"), 0) > rank.get(have.get("enforcement"), 0):
        weaker.append(f"enforcement {have.get('enforcement')} -> {want.get('enforcement')}")
    wanted_rules = _rules_by_type(want)
    weaker += [f"removes rule {kind}" for kind in _rules_by_type(have) if kind not in wanted_rules]
    present = _bypass(have)
    weaker += [f"adds bypass {actor}" for actor in sorted(_bypass(want), key=str)
               if not any(kind == actor[0] and ident == actor[1]
                          and BYPASS_MODES_BY_REACH.index(mode) >= BYPASS_MODES_BY_REACH.index(actor[2])
                          for kind, ident, mode in present)]
    return weaker


def forge_only(want: dict[str, Any], have: dict[str, Any]) -> list[str]:
    paths = [key for key, value in have.items()
             if key not in RULESET_KEYS and key not in API_ONLY_KEYS and meaningful(value)]
    paths += [f"conditions.{path}" for path in _extra_paths(have.get("conditions") or {},
                                                            want.get("conditions") or {})]
    wanted_rules = _rules_by_type(want)
    for kind, rule in _rules_by_type(have).items():
        if kind in wanted_rules:
            paths += [f"{kind}.{path}" for path in _extra_paths(rule.get("parameters") or {},
                                                                wanted_rules[kind].get("parameters") or {})]
    return paths


def _extra_paths(have: Any, want: Any) -> list[str]:
    if not isinstance(have, dict) or not isinstance(want, dict):
        return []
    paths = []
    for key, value in have.items():
        if key not in want:
            if meaningful(value):
                paths.append(key)
        else:
            paths += [f"{key}.{path}" for path in _extra_paths(value, want[key])]
    return paths


def meaningful(value: Any) -> bool:
    if isinstance(value, dict):
        return any(meaningful(inner) for inner in value.values())
    return bool(value)


def _rules_by_type(ruleset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {rule.get("type"): rule for rule in ruleset.get("rules") or ()}


def _bypass(ruleset: dict[str, Any]) -> set[tuple[str, Any, str]]:
    return {(actor.get("actor_type"), actor.get("actor_id"), actor.get("bypass_mode", "always"))
            for actor in ruleset.get("bypass_actors") or ()}


def contains(have: Any, want: Any) -> bool:
    if isinstance(want, dict):
        return isinstance(have, dict) and all(key in have and contains(have[key], value)
                                              for key, value in want.items())
    if isinstance(want, list):
        if not isinstance(have, list) or len(have) != len(want):
            return False
        remaining = list(have)
        for wanted in want:
            match = next((index for index, present in enumerate(remaining) if contains(present, wanted)),
                         None)
            if match is None:
                return False
            remaining.pop(match)
        return True
    return have == want
