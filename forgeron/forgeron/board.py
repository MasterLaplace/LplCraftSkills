from __future__ import annotations

import json
import subprocess
from typing import Any, Callable

from .model import Phase

Runner = Callable[[list[str], "str | None"], "tuple[int, str, str]"]

OPTIONS = ("Queued", "Planning", "Awaiting answer", "Working", "In review", "Blocked", "Done")

PHASE_OPTIONS = {
    Phase.QUEUED: "Queued",
    Phase.PLANNING: "Planning",
    Phase.AWAITING_ANSWER: "Awaiting answer",
    Phase.DRAFTED: "Working",
    Phase.IMPLEMENTING: "Working",
    Phase.IMPLEMENTED: "Working",
    Phase.AWAITING_CHECKS: "Working",
    Phase.FIXING_CHECKS: "Working",
    Phase.RESOLVING: "Working",
    Phase.IN_REVIEW: "In review",
    Phase.REVISING: "In review",
    Phase.REVISED: "In review",
    Phase.BLOCKED: "Blocked",
    Phase.MERGED: "Done",
    Phase.DONE: "Done",
    Phase.ABANDONED: "Done",
}

PROJECTS_QUERY = (
    "query($owner: String!, $cursor: String) {"
    "  repositoryOwner(login: $owner) {"
    "    ... on ProjectV2Owner {"
    "      projectsV2(first: 100, after: $cursor) { nodes { id title } pageInfo { hasNextPage endCursor } }"
    "    }"
    "  }"
    "}"
)

FIELDS_QUERY = (
    "query($id: ID!) {"
    "  node(id: $id) {"
    "    ... on ProjectV2 {"
    "      fields(first: 100) { nodes { ... on ProjectV2SingleSelectField { id name options { id name } } } }"
    "    }"
    "  }"
    "}"
)

CONTENT_QUERY = (
    "query($owner: String!, $name: String!, $number: Int!) {"
    "  repository(owner: $owner, name: $name) {"
    "    issueOrPullRequest(number: $number) { ... on Issue { id } ... on PullRequest { id } }"
    "  }"
    "}"
)

ADD_ITEM = ("mutation($input: AddProjectV2ItemByIdInput!) "
            "{ addProjectV2ItemById(input: $input) { item { id } } }")

SET_FIELD = ("mutation($input: UpdateProjectV2ItemFieldValueInput!) "
             "{ updateProjectV2ItemFieldValue(input: $input) { projectV2Item { id } } }")


class BoardError(RuntimeError):
    pass


def option_for(phase: Phase) -> str:
    return PHASE_OPTIONS[phase]


class GhBoard:
    def __init__(self, project: str, field: str = "Forgeron", runner: Runner | None = None,
                 executable: str = "gh", timeout: int = 60) -> None:
        self.project = project
        self.field = field
        self._owner, _, self._title = project.partition("/")
        self._gh = executable
        self._timeout = timeout
        self._runner = runner or self._subprocess
        self._project_id = ""
        self._fields: dict[str, tuple[str, dict[str, str]]] = {}

    def place(self, repo: str, number: int) -> str:
        owner, name = repo.split("/", 1)
        found = self._graphql(CONTENT_QUERY, owner=owner, name=name, number=number)
        content = ((found.get("repository") or {}).get("issueOrPullRequest") or {}).get("id")
        if not content:
            raise BoardError(f"{repo}#{number}: no issue or pull request with that number")
        added = self._graphql(ADD_ITEM, input={"projectId": self._project(), "contentId": content})
        return added["addProjectV2ItemById"]["item"]["id"]

    def set_option(self, item: str, option: str) -> None:
        known = self._fields.get(self.field)
        if known is None or option not in known[1]:
            self._fields = self._read_fields()
        field_id, options = self._known_field()
        if option not in options:
            raise BoardError(f"{self.project}: the field {self.field} has no option {option} "
                             f"(it has {', '.join(options) or 'none'})")
        self._graphql(SET_FIELD, input={"projectId": self._project(), "itemId": item, "fieldId": field_id,
                                        "value": {"singleSelectOptionId": options[option]}})

    def missing_options(self) -> tuple[str, ...]:
        self._fields = self._read_fields()
        options = self._known_field()[1]
        return tuple(option for option in OPTIONS if option not in options)

    def _known_field(self) -> tuple[str, dict[str, str]]:
        if self.field not in self._fields:
            raise BoardError(f"{self.project}: no single-select field named {self.field}")
        return self._fields[self.field]

    def _project(self) -> str:
        if self._project_id:
            return self._project_id
        cursor = None
        found: list[str] = []
        while True:
            owner = self._graphql(PROJECTS_QUERY, owner=self._owner, cursor=cursor).get("repositoryOwner")
            if owner is None:
                raise BoardError(f"{self._owner}: no such user or organization")
            block = owner.get("projectsV2") or {}
            found += [node["id"] for node in block.get("nodes") or () if node.get("title") == self._title]
            page = block.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                break
            cursor = page.get("endCursor")
        if len(found) != 1:
            raise BoardError(f"{self._owner} has {len(found)} projects titled \"{self._title}\", "
                             f"exactly one is expected")
        self._project_id = found[0]
        return self._project_id

    def _read_fields(self) -> dict[str, tuple[str, dict[str, str]]]:
        node = self._graphql(FIELDS_QUERY, id=self._project()).get("node") or {}
        fields = [field for field in (node.get("fields") or {}).get("nodes") or ()
                  if field.get("options") is not None]
        return {field["name"]: (field["id"], {option["name"]: option["id"] for option in field["options"]})
                for field in fields}

    def _graphql(self, query: str, **variables: Any) -> dict[str, Any]:
        code, out, err = self._runner(["api", "graphql", "--input", "-"],
                                      json.dumps({"query": query, "variables": variables}))
        try:
            data = json.loads(out or "null") or {}
        except json.JSONDecodeError:
            data = {}
        if data.get("errors"):
            raise BoardError("gh api graphql: " + "; ".join(error.get("message", "?")
                                                             for error in data["errors"]))
        if code != 0:
            raise BoardError(f"gh api graphql -> {code}: {err.strip()[:300]}")
        return data.get("data") or {}

    def _subprocess(self, argv: list[str], stdin: str | None) -> tuple[int, str, str]:
        try:
            done = subprocess.run([self._gh, *argv], input=stdin, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=self._timeout)
        except subprocess.TimeoutExpired:
            raise BoardError(f"gh {' '.join(argv[:2])}: no answer after {self._timeout} s")
        except OSError as failure:
            raise BoardError(f"gh {' '.join(argv[:2])}: could not run {self._gh} ({failure})")
        return done.returncode, done.stdout, done.stderr
