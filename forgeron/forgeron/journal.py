"""One structured line per decision and per action, and nothing else on stdout.

Prose logs cannot be replayed. Every line here is a JSON object carrying the
issue it is about, so a whole run is greppable by key and a test can assert on
events rather than on wording.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from typing import Any, TextIO


class Journal:
    def __init__(self, path: str | None = None, echo: TextIO | None = sys.stderr,
                 verbose: bool = False) -> None:
        self._path = path
        self._echo = echo
        self._verbose = verbose
        self.events: list[dict[str, Any]] = []
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)

    def emit(self, event: str, **fields: Any) -> None:
        line = {"ts": _now(), "event": event, **fields}
        self.events.append(line)
        if self._path:
            with open(self._path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, ensure_ascii=False) + "\n")
        if self._echo is not None:
            key = line.get("key", "-")
            extra = " ".join(
                f"{name}={value}" for name, value in line.items()
                if name not in ("ts", "event", "key")
            )
            print(f"{line['ts']} {event:<18} {key:<28} {extra}", file=self._echo)

    def debug(self, event: str, **fields: Any) -> None:
        if self._verbose:
            self.emit(event, **fields)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
