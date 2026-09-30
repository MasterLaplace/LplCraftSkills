from __future__ import annotations

import json
import subprocess
import urllib.parse
from typing import Any, Callable

from .etabli import SETTINGS_KEYS, Change, Kind, Observed, ObservedLabel

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


class GhEtabliError(RuntimeError):
    pass


class GhEtabli:
    def __init__(self, runner: Runner | None = None, executable: str = "gh", timeout: int = 60) -> None:
        self._gh = executable
        self._timeout = timeout
        self._runner = runner or self._subprocess

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
        )

    def apply(self, change: Change) -> None:
        if not change.kind.actionable:
            raise GhEtabliError(f"{change.kind.name} is not a write: {change.name}")
        slug = change.repo
        if change.domain == "labels":
            self._apply_label(slug, change)
        elif change.domain == "settings":
            self._send("PATCH", f"repos/{slug}", {change.name: change.after})
        elif change.domain == "security":
            self._apply_security(slug, change)
        elif change.domain == "rulesets" and change.kind is Kind.CREATE:
            self._send("POST", f"repos/{slug}/rulesets", change.after)
        elif change.domain == "rulesets":
            self._send("PUT", f"repos/{slug}/rulesets/{change.before['id']}", change.after)
        else:
            raise GhEtabliError(f"unknown domain: {change.domain}")

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
        return False if "HTTP 404" in err else None

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

    def _send(self, method: str, path: str, body: Any) -> None:
        argv = ["api", "-X", method, path]
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
        done = subprocess.run([self._gh, *argv], input=stdin, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=self._timeout)
        return done.returncode, done.stdout, done.stderr


def _quote(name: str) -> str:
    return urllib.parse.quote(name, safe="")
