"""When to run a pass. Polling today, push events later, same driver either way.

The seam exists because the choice is an infrastructure decision, not a program
one: polling needs nothing, `gh webhook forward` needs one extra OAuth scope, a
GitHub App needs a public endpoint. Deciding that now would bake today's lack of
a cluster into the loop.
"""

from __future__ import annotations

import time
from typing import Iterator, Protocol


class Trigger(Protocol):
    def ticks(self) -> Iterator[str]:
        """Yield one string per pass to run. The string is a reason, for the journal."""
        ...


class IntervalTrigger:
    """A pass every `seconds`. The whole PoC runs on this.

    Latency is half the interval on average; the API budget is 5000 calls an hour
    and one pass costs about four calls per tracked issue, so a 60 second interval
    supports roughly twenty live issues before the ceiling is anywhere near.
    """

    def __init__(self, seconds: int, limit: int = 0) -> None:
        self._seconds = seconds
        self._limit = limit

    def ticks(self) -> Iterator[str]:
        count = 0
        while True:
            yield "interval"
            count += 1
            if self._limit and count >= self._limit:
                return
            time.sleep(self._seconds)


class WebhookTrigger:
    """Push events instead of polling. Not implemented, and the reason is written here.

    Two ways in, neither of which needs a public address:

    1. `gh extension install cli/gh-webhook` then
       `gh webhook forward --repo OWNER/NAME --events issues,issue_comment,pull_request_review,pull_request_review_comment --url http://127.0.0.1:8787/hook`
       GitHub posts to the gh relay, the relay posts to localhost. Needs the
       `admin:repo_hook` scope, which the default `gh auth login` does not grant:
       `gh auth refresh -s admin:repo_hook`.

    2. A GitHub App with a webhook, which is what also buys a bot identity - pull
       requests authored by the app instead of by the human, and the checks API so
       the agent's own verdict shows up as a check run rather than a comment.

    Deliberately a stub: a trigger without a receiver is a feature nobody runs, and
    the driver already reconciles from observed state, so pushing events only
    changes latency - never correctness.
    """

    def __init__(self, port: int = 8787) -> None:
        self._port = port

    def ticks(self) -> Iterator[str]:
        raise NotImplementedError(
            "WebhookTrigger is a stub. Read its docstring for the two supported routes, "
            "then implement ticks() as an HTTP server yielding one tick per delivery. "
            "Until then: forgeron run --interval 60"
        )
