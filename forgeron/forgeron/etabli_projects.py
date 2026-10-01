from __future__ import annotations

import dataclasses
import json
import pathlib
import re
from typing import Any, Callable

from .etabli import _SLUG, Change, ConfigError, Kind, _refuse_case_twins, _refuse_unknown

PROJECT_KEYS = ("public", "short_description", "readme", "repositories", "fields", "views", "workflows")
FIELD_TYPES = {"single_select": "SINGLE_SELECT", "date": "DATE", "number": "NUMBER", "text": "TEXT"}
CUSTOM_TYPES = frozenset({"SINGLE_SELECT", "DATE", "NUMBER", "TEXT", "ITERATION", "MULTI_SELECT"})
COLORS = ("GRAY", "BLUE", "GREEN", "YELLOW", "ORANGE", "RED", "PINK", "PURPLE")
LAYOUTS = ("table", "board", "roadmap")
DIRECTIONS = ("asc", "desc")
BUILT_IN_FIELDS = ("Title", "Assignees", "Status", "Labels", "Linked pull requests", "Milestone",
                   "Repository", "Reviewers", "Parent issue", "Sub-issues progress")
REFUSED_IN_VIEWS = ("Created", "Updated", "Closed")
RESERVED = frozenset(name.lower() for name in BUILT_IN_FIELDS + REFUSED_IN_VIEWS) - {"status"}
REFUSED = frozenset(name.lower() for name in REFUSED_IN_VIEWS)
NEW_PROJECT_STATUS = (("Todo", "GREEN", "This item hasn't been started"),
                      ("In Progress", "YELLOW", "This is actively being worked on"),
                      ("Done", "PURPLE", "This has been completed"))
VIEW_KEYS = ("name", "layout", "filter", "fields", "sort_by", "group_by", "vertical_group_by")
IN_PLACE = ("layout", "filter", "fields")
REBUILT = ("sort_by", "group_by", "vertical_group_by")


@dataclasses.dataclass(frozen=True)
class Option:
    name: str
    color: str
    description: str


@dataclasses.dataclass(frozen=True)
class Field:
    name: str
    type: str
    options: tuple[Option, ...] = ()


@dataclasses.dataclass(frozen=True)
class DesiredProject:
    key: str
    owner: str
    title: str
    public: bool | None = None
    short_description: str | None = None
    readme: str | None = None
    repositories: tuple[str, ...] | None = None
    fields: tuple[Field, ...] = ()
    views: tuple[dict[str, Any], ...] = ()
    workflows: tuple[tuple[str, bool], ...] = ()


@dataclasses.dataclass(frozen=True)
class ObservedField:
    id: str
    database_id: int
    name: str
    type: str
    options: tuple[Option, ...] = ()
    option_ids: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class ObservedProject:
    key: str
    exists: bool
    can_update: bool = False
    id: str = ""
    number: int = 0
    url: str = ""
    owner_type: str = "User"
    items: int = 0
    public: bool = False
    short_description: str = ""
    readme: str = ""
    repositories: tuple[str, ...] = ()
    fields: tuple[ObservedField, ...] = ()
    views: tuple[dict[str, Any], ...] = ()
    workflows: dict[str, bool] = dataclasses.field(default_factory=dict)


def load_projects(path: str) -> tuple[DesiredProject, ...]:
    with open(path, encoding="utf-8") as handle:
        try:
            raw = json.load(handle)
        except json.JSONDecodeError as failure:
            raise ConfigError(f"{path}: invalid JSON at line {failure.lineno}: {failure.msg}")
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: a JSON object is expected at the root")
    base = pathlib.Path(path).resolve().parent

    def read(relative: str) -> str:
        target = (base / relative).resolve()
        if not target.is_relative_to(base):
            raise FileNotFoundError(f"{target} is outside {base}")
        return target.read_text(encoding="utf-8")

    return parse_projects(raw.get("projects", {}), source=f"{path}.projects", read=read)


def parse_projects(raw: Any, source: str, read: Callable[[str], str]) -> tuple[DesiredProject, ...]:
    if not isinstance(raw, dict):
        raise ConfigError(f"{source}: an object {{\"OWNER/TITLE\": {{...}}}} is expected")
    return tuple(_project(key, entry, f"{source}.{key}", read) for key, entry in raw.items())


def _project(key: str, entry: Any, where: str, read: Callable[[str], str]) -> DesiredProject:
    owner, _, title = key.partition("/")
    if not owner.strip() or not title.strip():
        raise ConfigError(f"{where}: \"{key}\" is not of the form OWNER/TITLE")
    if not isinstance(entry, dict):
        raise ConfigError(f"{where}: an object is expected")
    _refuse_unknown(entry, PROJECT_KEYS, where)
    public = entry.get("public")
    if public is not None and not isinstance(public, bool):
        raise ConfigError(f"{where}.public: true or false, not {public!r}")
    description = entry.get("short_description")
    if description is not None and not isinstance(description, str):
        raise ConfigError(f"{where}.short_description: a string is expected")
    fields = _fields(entry.get("fields", {}), f"{where}.fields")
    return DesiredProject(
        key=key,
        owner=owner,
        title=title,
        public=public,
        short_description=description,
        readme=_readme(entry.get("readme"), f"{where}.readme", read),
        repositories=_repositories(entry.get("repositories"), owner, f"{where}.repositories"),
        fields=fields,
        views=_views(entry.get("views", []), fields, f"{where}.views"),
        workflows=_workflows(entry.get("workflows", {}), f"{where}.workflows"),
    )


def _readme(value: Any, where: str, read: Callable[[str], str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: the path of a Markdown file, relative to the configuration file")
    parts = pathlib.PurePosixPath(value.replace("\\", "/"))
    if parts.is_absolute() or ".." in parts.parts or re.match(r"^[A-Za-z]:", value):
        raise ConfigError(f"{where}: {value} leaves the folder of the configuration file; the README is "
                          f"published on the project, so it is read from that folder only")
    try:
        return read(value)
    except (OSError, UnicodeDecodeError) as failure:
        raise ConfigError(f"{where}: {value} cannot be read as UTF-8 ({failure.__class__.__name__}); the "
                          f"path is relative to the configuration file")


def _repositories(value: Any, owner: str, where: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(slug, str) or not _SLUG.match(slug)
                                          for slug in value):
        raise ConfigError(f"{where}: a list of \"owner/name\" is expected")
    _refuse_case_twins(value, where, "repository")
    for slug in value:
        other = slug.split("/", 1)[0]
        if other.lower() != owner.lower():
            raise ConfigError(f"{where}: {slug} belongs to {other}, and a project of {owner} can only be "
                              f"linked to repositories of {owner}")
    return tuple(value)


def _fields(raw: Any, where: str) -> tuple[Field, ...]:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: an object {{\"name\": {{\"type\": ...}}}} is expected")
    _refuse_case_twins(raw, where, "field")
    fields = []
    for name, spec in raw.items():
        at = f"{where}.{name}"
        if name.lower() in RESERVED:
            raise ConfigError(f"{at}: a built-in field of every project, it cannot be declared")
        if not isinstance(spec, dict):
            raise ConfigError(f"{at}: an object is expected")
        _refuse_unknown(spec, ("type", "options"), at)
        kind = spec.get("type")
        if kind not in FIELD_TYPES:
            raise ConfigError(f"{at}.type: {kind!r}, expected one of: {', '.join(FIELD_TYPES)}")
        if name.lower() == "status" and kind != "single_select":
            raise ConfigError(f"{at}.type: Status is a single_select field on every project")
        if kind != "single_select":
            if "options" in spec:
                raise ConfigError(f"{at}.options: only a single_select field has options")
            fields.append(Field(name=name, type=kind))
            continue
        fields.append(Field(name=name, type=kind, options=_options(spec.get("options"), f"{at}.options")))
    return tuple(fields)


def _options(raw: Any, where: str) -> tuple[Option, ...]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError(f"{where}: a single_select field needs a list of options, "
                          f"each {{\"name\", \"color\", \"description\"}}")
    options = []
    for index, spec in enumerate(raw):
        at = f"{where}[{index}]"
        if not isinstance(spec, dict) or not isinstance(spec.get("name"), str) or not spec["name"].strip():
            raise ConfigError(f"{at}: an object with a \"name\" is expected")
        _refuse_unknown(spec, ("name", "color", "description"), at)
        color = spec.get("color")
        if color not in COLORS:
            raise ConfigError(f"{at}.color: {color!r}, expected one of: {', '.join(COLORS)}")
        description = spec.get("description", "")
        if not isinstance(description, str):
            raise ConfigError(f"{at}.description: a string is expected")
        options.append(Option(name=spec["name"], color=color, description=description))
    _refuse_case_twins([option.name for option in options], where, "option")
    return tuple(options)


def _views(raw: Any, fields: tuple[Field, ...], where: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(raw, list):
        raise ConfigError(f"{where}: a list of views is expected")
    known = {name.lower(): name for name in BUILT_IN_FIELDS}
    known.update({field.name.lower(): field.name for field in fields})
    views: list[dict[str, Any]] = []
    for index, spec in enumerate(raw):
        at = f"{where}[{index}]"
        if not isinstance(spec, dict) or not isinstance(spec.get("name"), str) or not spec["name"].strip():
            raise ConfigError(f"{at}: an object with a \"name\" is expected")
        at = f"{where}.{spec['name']}"
        _refuse_unknown(spec, VIEW_KEYS, at)
        if spec.get("layout") not in LAYOUTS:
            raise ConfigError(f"{at}.layout: {spec.get('layout')!r}, expected one of: {', '.join(LAYOUTS)}")
        view: dict[str, Any] = {"name": spec["name"], "layout": spec["layout"]}
        if "filter" in spec:
            if not isinstance(spec["filter"], str):
                raise ConfigError(f"{at}.filter: a string is expected")
            view["filter"] = spec["filter"]
        if "fields" in spec:
            if spec["layout"] == "roadmap":
                raise ConfigError(f"{at}.fields: a roadmap shows no columns, the API refuses visible fields")
            if not isinstance(spec["fields"], list) \
                    or any(not isinstance(name, str) for name in spec["fields"]):
                raise ConfigError(f"{at}.fields: a list of field names is expected")
            view["fields"] = [_known(name, known, f"{at}.fields") for name in spec["fields"]]
        if "sort_by" in spec:
            view["sort_by"] = _sort(spec["sort_by"], known, f"{at}.sort_by")
        if "group_by" in spec:
            view["group_by"] = [_known(spec["group_by"], known, f"{at}.group_by")]
        if "vertical_group_by" in spec:
            if spec["layout"] != "board":
                raise ConfigError(f"{at}.vertical_group_by: columns exist on a board only")
            view["vertical_group_by"] = [_known(spec["vertical_group_by"], known, f"{at}.vertical_group_by")]
        views.append(view)
    names = [view["name"] for view in views]
    twins = sorted({name for name in names if names.count(name) > 1})
    if twins:
        raise ConfigError(f"{where}: two views are named {', '.join(twins)}")
    return tuple(views)


def _known(name: Any, known: dict[str, str], where: str) -> str:
    if isinstance(name, str) and name.lower() in REFUSED:
        raise ConfigError(f"{where}: {name} is refused by the API in a view (400 unsupported_ids); "
                          f"set it in the interface and leave it out of the declaration")
    if not isinstance(name, str) or name.lower() not in known:
        raise ConfigError(f"{where}: {name!r} is neither a built-in field nor a declared one")
    return name


def _sort(raw: Any, known: dict[str, str], where: str) -> list[list[str]]:
    if not isinstance(raw, list):
        raise ConfigError(f"{where}: a list of [\"field\", \"asc\" or \"desc\"] is expected")
    pairs = []
    for index, pair in enumerate(raw):
        if not isinstance(pair, list) or len(pair) != 2:
            raise ConfigError(f"{where}[{index}]: [\"field\", \"asc\" or \"desc\"] is expected")
        name = _known(pair[0], known, f"{where}[{index}]")
        if pair[1] not in DIRECTIONS:
            raise ConfigError(f"{where}[{index}]: {pair[1]!r}, expected one of: {', '.join(DIRECTIONS)}")
        pairs.append([name, pair[1]])
    return pairs


def _workflows(raw: Any, where: str) -> tuple[tuple[str, bool], ...]:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: an object {{\"workflow name\": true or false}} is expected")
    for name, value in raw.items():
        if not isinstance(value, bool):
            raise ConfigError(f"{where}.{name}: true or false, not {value!r}")
    return tuple(raw.items())


def plan_project(desired: DesiredProject, observed: ObservedProject) -> list[Change]:
    key = desired.key
    if not observed.exists:
        create = Change(key, "project", Kind.CREATE, desired.title,
                        after={"owner": desired.owner, "title": desired.title},
                        note="then, on the new project:")
        return [create] + _plan_content(desired, new_project(key, observed.owner_type))
    if not observed.can_update:
        return [Change(key, "project", Kind.SKIPPED, "*", note="no write access to the project")]
    return _plan_content(desired, observed)


def new_project(key: str, owner_type: str = "User") -> ObservedProject:
    builtins = tuple(ObservedField(id="", database_id=0, name=name, type=name.upper().replace(" ", "_"))
                     for name in BUILT_IN_FIELDS if name != "Status")
    status = ObservedField(id="", database_id=0, name="Status", type="SINGLE_SELECT",
                           options=tuple(Option(*option) for option in NEW_PROJECT_STATUS),
                           option_ids=("", "", ""))
    view = {"id": "", "name": "View 1", "layout": "table", "filter": "", "fields": [], "sort_by": [],
            "group_by": [], "vertical_group_by": []}
    return ObservedProject(key=key, exists=True, can_update=True, owner_type=owner_type,
                           fields=builtins + (status,), views=(view,))


def _plan_content(desired: DesiredProject, observed: ObservedProject) -> list[Change]:
    return (_plan_settings(desired, observed) + _plan_links(desired, observed)
            + _plan_fields(desired, observed) + _plan_views(desired, observed)
            + _plan_workflows(desired, observed))


def _plan_settings(desired: DesiredProject, observed: ObservedProject) -> list[Change]:
    wanted = {"public": desired.public, "short_description": desired.short_description,
              "readme": desired.readme}
    present = {"public": observed.public, "short_description": observed.short_description or "",
               "readme": observed.readme or ""}
    differing = [key for key, value in wanted.items()
                 if value is not None and _settled(key, value) != _settled(key, present[key])]
    if not differing:
        return []
    return [Change(desired.key, "project", Kind.UPDATE, "settings",
                   before={key: present[key] for key in differing},
                   after={key: wanted[key] for key in differing})]


def _settled(key: str, value: Any) -> Any:
    if key == "readme":
        return value.replace("\r\n", "\n").rstrip()
    return value


def _plan_links(desired: DesiredProject, observed: ObservedProject) -> list[Change]:
    if desired.repositories is None:
        return []
    present = {slug.lower() for slug in observed.repositories}
    declared = {slug.lower() for slug in desired.repositories}
    changes = [Change(desired.key, "links", Kind.CREATE, slug) for slug in desired.repositories
               if slug.lower() not in present]
    changes += [Change(desired.key, "links", Kind.UNLISTED, slug, note="linked, undeclared: never unlinked")
                for slug in observed.repositories if slug.lower() not in declared]
    return changes


def _plan_fields(desired: DesiredProject, observed: ObservedProject) -> list[Change]:
    present = {field.name.lower(): field for field in observed.fields}
    changes = []
    for field in desired.fields:
        have = present.get(field.name.lower())
        if have is None:
            options = [dataclasses.asdict(option) for option in field.options]
            changes.append(Change(desired.key, "fields", Kind.CREATE, field.name,
                                  after={"name": field.name, "type": field.type, "options": options}))
        elif have.type != FIELD_TYPES[field.type]:
            changes.append(Change(desired.key, "fields", Kind.BLOCKED, field.name,
                                  note=f"{have.type.lower()} on the project, declared {field.type}: changing "
                                       f"the type deletes every value it holds, do it by hand"))
        elif field.options:
            changes += _plan_options(desired.key, field, have, observed.items)
    declared = {field.name.lower() for field in desired.fields}
    for have in observed.fields:
        if have.type in CUSTOM_TYPES and have.name != "Status" and have.name.lower() not in declared:
            changes.append(Change(desired.key, "fields", Kind.UNLISTED, have.name,
                                  note="undeclared: never deleted, a deleted field takes its values with it"))
    return changes


def _plan_options(key: str, field: Field, have: ObservedField, items: int) -> list[Change]:
    wanted = {option.name.lower() for option in field.options}
    removed = [option.name for option in have.options if option.name.lower() not in wanted]
    if removed and items:
        return [Change(key, "fields", Kind.BLOCKED, field.name,
                       note=f"removing {', '.join(removed)} clears it from every item that carries it, "
                            f"among the {items} of the project: remove it by hand")]
    if list(have.options) == list(field.options):
        return []
    ids = {option.name.lower(): option_id for option, option_id in zip(have.options, have.option_ids)}
    after = []
    for option in field.options:
        entry = dataclasses.asdict(option)
        if option.name.lower() in ids:
            entry["id"] = ids[option.name.lower()]
        after.append(entry)
    return [Change(key, "fields", Kind.UPDATE, field.name,
                   before={"id": have.id, "options": [dataclasses.asdict(option) for option in have.options]},
                   after={"options": after})]


def _plan_views(desired: DesiredProject, observed: ObservedProject) -> list[Change]:
    present = {view["name"]: view for view in observed.views}
    changes = []
    for want in desired.views:
        have = present.get(want["name"])
        if have is None:
            changes.append(Change(desired.key, "views", Kind.CREATE, want["name"], after=dict(want)))
            continue
        changed = [key for key in IN_PLACE if key in want and _differs(key, want, have)]
        moved = [key for key in REBUILT if key in want and _differs(key, want, have)]
        if not changed and not moved:
            continue
        note = ", ".join(changed + moved)
        if moved:
            note += "; grouping or sorting changes: the view is created anew, then the old one deleted"
        changes.append(Change(desired.key, "views", Kind.UPDATE, want["name"], before=have,
                              after={**want, "rebuild": bool(moved)}, note=note))
    declared = {want["name"] for want in desired.views}
    changes += [Change(desired.key, "views", Kind.UNLISTED, view["name"], note="undeclared view")
                for view in observed.views if view["name"] not in declared]
    return changes


def _differs(key: str, want: dict[str, Any], have: dict[str, Any]) -> bool:
    return _shape(key, want[key]) != _shape(key, have.get(key))


def _shape(key: str, value: Any) -> Any:
    if key == "fields":
        return sorted(value or ())
    if key == "filter":
        return (value or "").strip()
    if key == "sort_by":
        return [[name, direction.lower()] for name, direction in value or ()]
    return value if value is not None else []


def _plan_workflows(desired: DesiredProject, observed: ObservedProject) -> list[Change]:
    where = f"{observed.url}/workflows" if observed.url else "on the project's Workflows page"
    changes = []
    for name, wanted in desired.workflows:
        enabled = observed.workflows.get(name, False)
        if wanted and not enabled:
            state = "off" if name in observed.workflows else "absent"
            changes.append(Change(desired.key, "workflows", Kind.BLOCKED, name,
                                  note=f"{state}: switch it on in the interface, {where}"))
        elif enabled and not wanted:
            changes.append(Change(desired.key, "workflows", Kind.BLOCKED, name,
                                  note=f"on: switch it off in the interface, {where}"))
    return changes
