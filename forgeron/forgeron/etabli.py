from __future__ import annotations

import dataclasses
import enum
import json
import re
from typing import Any

DOMAINS = ("labels", "settings", "security", "rulesets")

SETTINGS_KEYS = frozenset({
    "allow_squash_merge", "allow_merge_commit", "allow_rebase_merge", "allow_auto_merge",
    "allow_update_branch", "delete_branch_on_merge", "squash_merge_commit_title",
    "squash_merge_commit_message", "merge_commit_title", "merge_commit_message",
    "web_commit_signoff_required", "has_issues", "has_projects", "has_wiki", "has_discussions",
})

SECURITY_KEYS = (
    "secret_scanning", "secret_scanning_push_protection", "dependabot_alerts",
    "dependabot_security_updates", "private_vulnerability_reporting",
)

UNLISTED_POLICIES = ("report", "delete-unused")

REPO_KEYS = frozenset({"labels", "renames", "unlisted_labels", "settings", "security", "rulesets",
                       "required_checks", "only"})
DEFAULT_KEYS = REPO_KEYS - {"required_checks", "only"}

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
    declared = {name.lower() for name in labels}
    if len(declared) != len(labels):
        raise ConfigError(f"{where}.labels: two labels differ only by case, and the forge "
                          f"treats them as one")
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


def _refuse_unknown(value: dict[str, Any], allowed: frozenset[str] | set[str], where: str) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise ConfigError(f"{where}: unknown key(s) {', '.join(unknown)}; "
                          f"expected: {', '.join(sorted(allowed))}")


def _labels(raw: Any, where: str) -> dict[str, Label]:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: an object {{\"name\": {{\"color\", \"description\"}}}} is expected")
    labels: dict[str, Label] = {}
    for name, spec in raw.items():
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
    return dict(raw)


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
        if not isinstance(ruleset, dict) or not ruleset.get("name"):
            raise ConfigError(f"{where}[{index}]: an object with a \"name\" is expected")
        for key in ("target", "enforcement", "rules"):
            if key not in ruleset:
                raise ConfigError(f"{where}[{index}] ({ruleset['name']}): \"{key}\" is missing")
        if ruleset["name"] in names:
            raise ConfigError(f"{where}: two rulesets are named \"{ruleset['name']}\"")
        names.add(ruleset["name"])
    return tuple(json.loads(json.dumps(ruleset)) for ruleset in raw)


def _with_required_checks(rulesets: tuple[dict[str, Any], ...], checks: Any,
                          where: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(checks, list) or any(not isinstance(check, str) or not check
                                           for check in checks):
        raise ConfigError(f"{where}: a list of check names is expected")
    if not checks:
        return rulesets
    rule = {"type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": False,
        "required_status_checks": [{"context": check} for check in checks],
    }}
    completed = []
    for ruleset in rulesets:
        ruleset = json.loads(json.dumps(ruleset))
        types = {entry.get("type") for entry in ruleset["rules"]}
        if ruleset["target"] == "branch" and "required_status_checks" not in types:
            ruleset["rules"].append(json.loads(json.dumps(rule)))
        completed.append(ruleset)
    return tuple(completed)


def plan(desired: Desired, observed: Observed) -> list[Change]:
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
        if desired.unlisted_labels == "delete-unused" and current.uses == 0:
            changes.append(Change(repo, "labels", Kind.DELETE, current.name,
                                  before=_label_view(current), note="undeclared, carried by no item"))
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
    return [Change(desired.slug, "settings", Kind.UPDATE, key, before=observed.settings.get(key),
                   after=value)
            for key, value in desired.settings.items() if observed.settings.get(key) != value]


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
        if differences:
            changes.append(Change(desired.slug, "rulesets", Kind.UPDATE, want["name"],
                                  before={"id": have.get("id")}, after=want,
                                  note=" ; ".join(differences)))
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

    wanted_rules = {rule.get("type"): rule for rule in want.get("rules", [])}
    present_rules = {rule.get("type"): rule for rule in have.get("rules", [])}
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
        differences.append(f"bypass {sorted(present_bypass)} -> {sorted(wanted_bypass)}")
    return differences


def _bypass(ruleset: dict[str, Any]) -> set[tuple[str, Any, str]]:
    return {(actor.get("actor_type"), actor.get("actor_id"), actor.get("bypass_mode", "always"))
            for actor in ruleset.get("bypass_actors") or ()}


def contains(have: Any, want: Any) -> bool:
    if isinstance(want, dict):
        return isinstance(have, dict) and all(key in have and contains(have[key], value)
                                              for key, value in want.items())
    if isinstance(want, list):
        return (isinstance(have, list) and len(have) == len(want)
                and all(contains(present, wanted) for present, wanted in zip(have, want)))
    return have == want
