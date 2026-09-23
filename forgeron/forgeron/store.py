"""Records on disk, one JSON file per issue, plus a lease so two drivers cannot
work the same issue.

Written atomically through a temporary file and a rename: a driver killed mid-write
must leave either the old record or the new one, never half of one. A truncated
record is the single state the reconciler cannot recover from, because it parses.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import socket
import time
from typing import Any, Iterator

from .journal import _now
from .model import Phase, Record


class Store:
    def __init__(self, directory: str) -> None:
        self._dir = directory
        os.makedirs(directory, exist_ok=True)

    def path_of(self, record: Record) -> str:
        return os.path.join(self._dir, f"{record.key}.json")

    def load(self, repo: str, issue: int) -> Record | None:
        probe = Record(repo=repo, issue=issue)
        path = self.path_of(probe)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
        raw["phase"] = Phase(raw["phase"])
        for key in ("seen_feedback",):
            raw[key] = tuple(raw.get(key, ()))
        known = {field.name for field in dataclasses.fields(Record)}
        return Record(**{k: v for k, v in raw.items() if k in known})

    def save(self, record: Record) -> Record:
        record = record.with_(updated_at=_now())
        path = self.path_of(record)
        payload = dataclasses.asdict(record)
        payload["phase"] = record.phase.value
        payload["seen_feedback"] = list(record.seen_feedback)
        temporary = f"{path}.tmp.{os.getpid()}"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temporary, path)
        return record

    def all(self) -> list[Record]:
        records: list[Record] = []
        for name in sorted(os.listdir(self._dir)):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(self._dir, name), encoding="utf-8") as handle:
                raw = json.load(handle)
            records.append(self.load(raw["repo"], raw["issue"]))  # type: ignore[arg-type]
        return [record for record in records if record is not None]

    @contextlib.contextmanager
    def lease(self, record: Record, ttl_seconds: int = 3600) -> Iterator[bool]:
        """Hold the right to act on one issue. Yields False if someone else holds it.

        Expiry rather than a pid check: in a cluster the previous holder is a pod
        that no longer exists, and asking "is that pid alive" answers about the
        wrong machine.
        """
        path = self.path_of(record) + ".lease"
        now = time.time()
        holder = f"{socket.gethostname()}:{os.getpid()}"
        existing = _read_lease(path)
        if existing and existing["expires"] > now and existing["holder"] != holder:
            yield False
            return
        _write_lease(path, {"holder": holder, "expires": now + ttl_seconds})
        try:
            yield True
        finally:
            current = _read_lease(path)
            if current and current["holder"] == holder:
                with contextlib.suppress(FileNotFoundError):
                    os.remove(path)


def _read_lease(path: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_lease(path: str, payload: dict[str, Any]) -> None:
    temporary = f"{path}.tmp.{os.getpid()}"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    os.replace(temporary, path)
