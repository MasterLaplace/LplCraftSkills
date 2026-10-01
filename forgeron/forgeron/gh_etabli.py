from __future__ import annotations

import json
import subprocess
import urllib.parse
from typing import Any, Callable

from .etabli import SETTINGS_KEYS, Change, Kind, Observed, ObservedLabel
from .etabli_projects import REFUSED_IN_VIEWS, DesiredProject, ObservedField, ObservedProject, Option

Runner = Callable[[list[str], "str | None"], "tuple[int, str, str]"]

LABELS_QUERY = (
    "query($owner: String!, $name: String!, $cursor: String) {"
    "  repository(owner: $owner, name: $name) {"
    "    labels(first: 100, after: $cursor) {"
    "      nodes { name color description issues { totalCount } pullRequests { totalCount } }"
    "      pageInfo { hasNextPage endCursor }"
    "    }"
    "  }"
    "}"
)

SCANNING = ("secret_scanning", "secret_scanning_push_protection")

TOGGLES = {
    "dependabot_alerts": "vulnerability-alerts",
    "dependabot_security_updates": "automated-security-fixes",
    "private_vulnerability_reporting": "private-vulnerability-reporting",
}

PROJECTS_QUERY = (
    "query($owner: String!, $cursor: String) {"
    "  repositoryOwner(login: $owner) {"
    "    __typename"
    "    ... on ProjectV2Owner {"
    "      id"
    "      projectsV2(first: 100, after: $cursor) {"
    "        nodes { id number title }"
    "        pageInfo { hasNextPage endCursor }"
    "      }"
    "    }"
    "  }"
    "}"
)

PROJECT_QUERY = (
    "query($id: ID!) {"
    "  node(id: $id) {"
    "    ... on ProjectV2 {"
    "      id number url title public shortDescription readme viewerCanUpdate"
    "      items(archivedStates: [ARCHIVED, NOT_ARCHIVED]) { totalCount }"
    "      repositories(first: 100) { nodes { nameWithOwner } pageInfo { hasNextPage } }"
    "      fields(first: 100) {"
    "        nodes {"
    "          ... on ProjectV2FieldCommon { id databaseId name dataType }"
    "          ... on ProjectV2SingleSelectField { options { id name color description } }"
    "        }"
    "        pageInfo { hasNextPage }"
    "      }"
    "      views(first: 100) {"
    "        nodes {"
    "          id number name layout filter"
    "          fields(first: 100) { nodes { ... on ProjectV2FieldCommon { name } } }"
    "          groupByFields(first: 10) { nodes { ... on ProjectV2FieldCommon { name } } }"
    "          verticalGroupByFields(first: 10) { nodes { ... on ProjectV2FieldCommon { name } } }"
    "          sortByFields(first: 10) { nodes { direction field { ... on ProjectV2FieldCommon { name } } } }"
    "        }"
    "        pageInfo { hasNextPage }"
    "      }"
    "      workflows(first: 100) { nodes { name enabled } pageInfo { hasNextPage } }"
    "    }"
    "  }"
    "}"
)

REPOSITORY_QUERY = "query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) { id } }"

MUTATIONS = {
    "createProjectV2": "CreateProjectV2Input",
    "updateProjectV2": "UpdateProjectV2Input",
    "linkProjectV2ToRepository": "LinkProjectV2ToRepositoryInput",
    "createProjectV2Field": "CreateProjectV2FieldInput",
    "updateProjectV2Field": "UpdateProjectV2FieldInput",
    "updateProjectV2View": "UpdateProjectV2ViewInput",
    "deleteProjectV2View": "DeleteProjectV2ViewInput",
}

SETTING_NAMES = {"public": "public", "short_description": "shortDescription", "readme": "readme"}
OWNER_PATHS = {"User": "users", "Organization": "orgs"}
PROJECT_DOMAINS = ("project", "links", "fields", "views", "workflows")
REST_VERSION = "2026-03-10"


class GhEtabliError(RuntimeError):
    pass


class GhEtabli:
    def __init__(self, runner: Runner | None = None, executable: str = "gh", timeout: int = 60) -> None:
        self._gh = executable
        self._timeout = timeout
        self._runner = runner or self._subprocess
        self._owners: dict[str, str] = {}
        self._projects: dict[str, ObservedProject] = {}

    def observe(self, slug: str) -> Observed:
        repo = self._json(["api", f"repos/{slug}"])
        permissions = repo.get("permissions") or {}
        admin = bool(permissions.get("admin"))
        push = admin or bool(permissions.get("push"))
        return Observed(
            slug=slug,
            admin=admin,
            push=push,
            labels=self._labels(slug),
            settings={key: repo[key] for key in SETTINGS_KEYS if key in repo},
            security=self._security(slug, repo) if admin else {},
            rulesets=self._rulesets(slug) if admin else (),
            archived=bool(repo.get("archived")),
            discussions=bool(repo.get("has_discussions")),
        )

    def apply(self, change: Change) -> None:
        if not change.kind.actionable:
            raise GhEtabliError(f"{change.kind.name} is not a write: {change.name}")
        if change.domain in PROJECT_DOMAINS:
            self._apply_project(change)
            return
        slug = change.repo
        if change.domain == "labels":
            self._apply_label(slug, change)
        elif change.domain == "settings":
            self._send("PATCH", f"repos/{slug}", change.after)
        elif change.domain == "security":
            self._apply_security(slug, change)
        elif change.domain == "rulesets" and change.kind is Kind.CREATE:
            self._send("POST", f"repos/{slug}/rulesets", change.after)
        elif change.domain == "rulesets":
            self._send("PUT", f"repos/{slug}/rulesets/{change.before['id']}", change.after)
        else:
            raise GhEtabliError(f"unknown domain: {change.domain}")

    def observe_project(self, desired: DesiredProject) -> ObservedProject:
        owner = self._graphql(PROJECTS_QUERY, owner=desired.owner).get("repositoryOwner")
        if owner is None:
            raise GhEtabliError(f"{desired.owner}: no such user or organization")
        self._owners[desired.key] = owner.get("id", "")
        owner_type = owner.get("__typename", "User")
        found = self._find_project(desired, owner)
        if found is None:
            state = ObservedProject(key=desired.key, exists=False, owner_type=owner_type)
        else:
            state = self._read_project(desired.key, found, owner_type)
        self._projects[desired.key] = state
        return state

    def _find_project(self, desired: DesiredProject, owner: dict[str, Any]) -> str | None:
        block = owner.get("projectsV2") or {}
        found: list[str] = []
        while True:
            found += [node["id"] for node in block.get("nodes") or () if node.get("title") == desired.title]
            page = block.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                break
            following = self._graphql(PROJECTS_QUERY, owner=desired.owner, cursor=page.get("endCursor"))
            block = (following.get("repositoryOwner") or {}).get("projectsV2") or {}
        if len(found) > 1:
            raise GhEtabliError(f"{desired.owner} has {len(found)} projects titled \"{desired.title}\": "
                                f"rename all but one, the title is what etabli finds a project by")
        return found[0] if found else None

    def _read_project(self, key: str, project_id: str, owner_type: str) -> ObservedProject:
        node = self._graphql(PROJECT_QUERY, id=project_id).get("node") or {}
        if not all(block in node for block in ("repositories", "fields", "views", "workflows")):
            raise GhEtabliError(f"{key}: the forge did not return the project it listed")
        for block in ("repositories", "fields", "views", "workflows"):
            if ((node.get(block) or {}).get("pageInfo") or {}).get("hasNextPage"):
                raise GhEtabliError(f"{key}: more than 100 {block}, which etabli does not read")
        return ObservedProject(
            key=key, exists=True, can_update=bool(node.get("viewerCanUpdate")), id=node.get("id", ""),
            number=int(node.get("number") or 0), url=node.get("url", ""), owner_type=owner_type,
            items=int((node.get("items") or {}).get("totalCount") or 0),
            public=bool(node.get("public")), short_description=node.get("shortDescription") or "",
            readme=node.get("readme") or "",
            repositories=tuple(repo["nameWithOwner"] for repo in node["repositories"]["nodes"]),
            fields=tuple(_field(field) for field in node["fields"]["nodes"] if field),
            views=tuple(_view(view) for view in node["views"]["nodes"]),
            workflows={flow["name"]: bool(flow.get("enabled")) for flow in node["workflows"]["nodes"]},
        )

    def _apply_project(self, change: Change) -> None:
        state = self._projects.get(change.repo)
        if state is None:
            raise GhEtabliError(f"{change.repo}: observe the project before writing to it")
        if change.domain == "project" and change.kind is Kind.CREATE:
            self._mutate("createProjectV2", {"ownerId": self._owners[change.repo],
                                             "title": change.after["title"]})
        elif change.domain == "project":
            self._mutate("updateProjectV2", {"projectId": state.id, **{SETTING_NAMES[key]: value
                                                                     for key, value in change.after.items()}})
        elif change.domain == "links":
            owner, name = change.name.split("/", 1)
            repository = self._graphql(REPOSITORY_QUERY, owner=owner, name=name).get("repository") or {}
            if not repository.get("id"):
                raise GhEtabliError(f"{change.name}: repository not found")
            self._mutate("linkProjectV2ToRepository", {"projectId": state.id,
                                                       "repositoryId": repository["id"]})
        elif change.domain == "fields" and change.kind is Kind.CREATE:
            fields = {"projectId": state.id, "dataType": change.after["type"].upper(),
                      "name": change.after["name"]}
            if change.after["options"]:
                fields["singleSelectOptions"] = change.after["options"]
            self._mutate("createProjectV2Field", fields)
        elif change.domain == "fields":
            self._mutate("updateProjectV2Field", {"fieldId": change.before["id"],
                                                  "singleSelectOptions": change.after["options"]})
        elif change.domain == "views" and change.kind is Kind.CREATE:
            self._create_view(state, change.after)
        elif change.domain == "views" and change.after.get("rebuild"):
            self._create_view(state, _carried(change.before, change.after))
            self._mutate("deleteProjectV2View", {"viewId": change.before["id"]})
        elif change.domain == "views":
            self._update_view(state, change)
        else:
            raise GhEtabliError(f"{change.domain} {change.kind.name} cannot be written: {change.name}")

    def _create_view(self, state: ObservedProject, view: dict[str, Any]) -> None:
        ids = self._field_ids(state, "database_id")
        body: dict[str, Any] = {"name": view["name"], "layout": view["layout"]}
        if "filter" in view:
            body["filter"] = view["filter"]
        if "fields" in view:
            body["visible_fields"] = [ids[name] for name in view["fields"]]
        if "sort_by" in view:
            body["sort_by"] = [[ids[name], direction] for name, direction in view["sort_by"]]
        for key in ("group_by", "vertical_group_by"):
            if key in view:
                body[key] = [ids[name] for name in view[key]]
        owner = state.key.split("/", 1)[0]
        path = f"{OWNER_PATHS.get(state.owner_type, 'users')}/{owner}/projectsV2/{state.number}/views"
        self._send("POST", path, body, ["-H", f"X-GitHub-Api-Version: {REST_VERSION}"])

    def _update_view(self, state: ObservedProject, change: Change) -> None:
        fields: dict[str, Any] = {"viewId": change.before["id"],
                                  "layout": f"{change.after['layout'].upper()}_LAYOUT"}
        if "filter" in change.after:
            fields["filter"] = change.after["filter"]
        if "fields" in change.after:
            ids = self._field_ids(state, "id")
            fields["configuration"] = {"visibleFieldIds": [ids[name] for name in change.after["fields"]]}
        self._mutate("updateProjectV2View", fields)

    def _field_ids(self, state: ObservedProject, attribute: str) -> "_FieldIds":
        return _FieldIds(state.key, {field.name.lower(): getattr(field, attribute)
                                     for field in self._current_fields(state)})

    def _current_fields(self, state: ObservedProject) -> tuple[ObservedField, ...]:
        node = self._graphql(PROJECT_QUERY, id=state.id).get("node") or {}
        return tuple(_field(field) for field in (node.get("fields") or {}).get("nodes") or () if field)

    def _mutate(self, mutation: str, fields: dict[str, Any]) -> dict[str, Any]:
        query = (f"mutation($input: {MUTATIONS[mutation]}!) "
                 f"{{ {mutation}(input: $input) {{ clientMutationId }} }}")
        return self._graphql(query, input=fields)

    def _graphql(self, query: str, **variables: Any) -> dict[str, Any]:
        payload = json.dumps({"query": query, "variables": variables})
        code, out, err = self._runner(["api", "graphql", "--input", "-"], payload)
        try:
            data = json.loads(out or "null") or {}
        except json.JSONDecodeError:
            data = {}
        if data.get("errors"):
            messages = "; ".join(error.get("message", "?") for error in data["errors"])
            raise GhEtabliError(f"gh api graphql: {messages}")
        if code != 0:
            raise GhEtabliError(f"gh api graphql -> {code}: {err.strip()[:500]}")
        return data.get("data") or {}

    def _labels(self, slug: str) -> tuple[ObservedLabel, ...]:
        owner, name = slug.split("/", 1)
        labels: list[ObservedLabel] = []
        cursor = ""
        while True:
            argv = ["api", "graphql", "-f", f"query={LABELS_QUERY}", "-f", f"owner={owner}",
                    "-f", f"name={name}"]
            if cursor:
                argv += ["-f", f"cursor={cursor}"]
            data = self._json(argv)
            repository = (data.get("data") or {}).get("repository")
            if repository is None:
                raise GhEtabliError(f"{slug}: repository not found through GraphQL ({data.get('errors')})")
            block = repository.get("labels") or {}
            for node in block.get("nodes") or ():
                uses = ((node.get("issues") or {}).get("totalCount", 0)
                        + (node.get("pullRequests") or {}).get("totalCount", 0))
                labels.append(ObservedLabel(name=node["name"], color=(node.get("color") or "").lower(),
                                            description=node.get("description") or "", uses=int(uses)))
            page = block.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                return tuple(labels)
            cursor = page.get("endCursor") or ""

    def _security(self, slug: str, repo: dict[str, Any]) -> dict[str, bool | None]:
        analysis = repo.get("security_and_analysis") or {}
        state: dict[str, bool | None] = {
            key: {"enabled": True, "disabled": False}.get((analysis.get(key) or {}).get("status"))
            for key in SCANNING
        }
        state["dependabot_alerts"] = self._answers(f"repos/{slug}/{TOGGLES['dependabot_alerts']}")
        for key in ("dependabot_security_updates", "private_vulnerability_reporting"):
            state[key] = self._enabled(f"repos/{slug}/{TOGGLES[key]}")
        return state

    def _answers(self, path: str) -> bool | None:
        code, _, err = self._runner(["api", path], None)
        if code == 0:
            return True
        return False if "are disabled" in err and "HTTP 404" in err else None

    def _enabled(self, path: str) -> bool | None:
        code, out, _ = self._runner(["api", path], None)
        if code != 0:
            return None
        try:
            enabled = json.loads(out or "{}").get("enabled")
        except (json.JSONDecodeError, AttributeError):
            return None
        return enabled if isinstance(enabled, bool) else None

    def _rulesets(self, slug: str) -> tuple[dict[str, Any], ...]:
        summaries = self._json(["api", f"repos/{slug}/rulesets?includes_parents=false&per_page=100"])
        return tuple(self._json(["api", f"repos/{slug}/rulesets/{summary['id']}"])
                     for summary in summaries or ()
                     if summary.get("source_type", "Repository") == "Repository")

    def _apply_label(self, slug: str, change: Change) -> None:
        path = f"repos/{slug}/labels"
        if change.kind is Kind.CREATE:
            self._send("POST", path, change.after)
        elif change.kind is Kind.DELETE:
            self._send("DELETE", f"{path}/{_quote(change.name)}", None)
        else:
            self._send("PATCH", f"{path}/{_quote(change.name)}", {
                "new_name": change.after["name"],
                "color": change.after["color"],
                "description": change.after["description"],
            })

    def _apply_security(self, slug: str, change: Change) -> None:
        if change.name in SCANNING:
            status = "enabled" if change.after else "disabled"
            self._send("PATCH", f"repos/{slug}", {"security_and_analysis": {change.name: {"status": status}}})
        else:
            self._send("PUT" if change.after else "DELETE", f"repos/{slug}/{TOGGLES[change.name]}", None)

    def _send(self, method: str, path: str, body: Any, headers: list[str] | None = None) -> None:
        argv = ["api", "-X", method, path, *(headers or ())]
        stdin = None
        if body is not None:
            argv += ["--input", "-"]
            stdin = json.dumps(body)
        code, _, err = self._runner(argv, stdin)
        if code != 0:
            raise GhEtabliError(f"gh {' '.join(argv)} -> {code}: {err.strip()[:500]}")

    def _json(self, argv: list[str]) -> Any:
        code, out, err = self._runner(argv, None)
        if code != 0:
            raise GhEtabliError(f"gh {' '.join(argv[:2])} -> {code}: {err.strip()[:500]}")
        try:
            return json.loads(out or "null")
        except json.JSONDecodeError as failure:
            raise GhEtabliError(f"gh {' '.join(argv[:2])}: unreadable response ({failure.msg})")

    def _subprocess(self, argv: list[str], stdin: str | None) -> tuple[int, str, str]:
        try:
            done = subprocess.run([self._gh, *argv], input=stdin, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=self._timeout)
        except subprocess.TimeoutExpired:
            raise GhEtabliError(f"gh {' '.join(argv[:4])}: no answer after {self._timeout} s, "
                                f"the state of the forge is unknown")
        except OSError as failure:
            raise GhEtabliError(f"gh {' '.join(argv[:4])}: could not run {self._gh} ({failure}), "
                                f"the state of the forge is unknown")
        return done.returncode, done.stdout, done.stderr


def _field(node: dict[str, Any]) -> ObservedField:
    options = node.get("options") or ()
    return ObservedField(
        id=node.get("id", ""), database_id=int(node.get("databaseId") or 0), name=node.get("name", ""),
        type=node.get("dataType", ""),
        options=tuple(Option(option["name"], option["color"], option.get("description") or "")
                      for option in options),
        option_ids=tuple(option["id"] for option in options),
    )


def _view(node: dict[str, Any]) -> dict[str, Any]:
    def names(block: str) -> list[str]:
        return [field.get("name", "") for field in (node.get(block) or {}).get("nodes") or ()]
    return {
        "id": node.get("id", ""),
        "name": node.get("name", ""),
        "layout": (node.get("layout") or "").split("_")[0].lower(),
        "filter": node.get("filter") or "",
        "fields": names("fields"),
        "sort_by": [[(sort.get("field") or {}).get("name", ""), (sort.get("direction") or "").lower()]
                    for sort in (node.get("sortByFields") or {}).get("nodes") or ()],
        "group_by": names("groupByFields"),
        "vertical_group_by": names("verticalGroupByFields"),
    }


class _FieldIds:
    def __init__(self, key: str, ids: dict[str, Any]) -> None:
        self._key = key
        self._ids = ids

    def __getitem__(self, name: str) -> Any:
        if name.lower() not in self._ids:
            raise GhEtabliError(f"{self._key}: no field named {name} on the project")
        return self._ids[name.lower()]


def _carried(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    view = {key: value for key, value in after.items() if key != "rebuild"}
    refused = {name.lower() for name in REFUSED_IN_VIEWS}
    kept = {
        "fields": [name for name in before.get("fields") or () if name.lower() not in refused],
        "sort_by": [pair for pair in before.get("sort_by") or () if pair[0].lower() not in refused],
        "group_by": [name for name in before.get("group_by") or () if name.lower() not in refused],
        "vertical_group_by": [name for name in before.get("vertical_group_by") or ()
                              if name.lower() not in refused],
    }
    for key, value in kept.items():
        if key in view or not value:
            continue
        if key == "fields" and view["layout"] == "roadmap":
            continue
        if key == "vertical_group_by" and view["layout"] != "board":
            continue
        view[key] = value
    return view


def _quote(name: str) -> str:
    return urllib.parse.quote(name, safe="")
