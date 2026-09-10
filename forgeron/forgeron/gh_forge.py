"""GitHub through the `gh` command line, on purpose.

No token is handled here: `gh` already holds one, so the PoC inherits the human's
auth and there is no secret to leak in a config file. The cost is that the bot
speaks as the human; swapping this class for a GitHub App installation token is
what buys a separate bot identity, and it is the only class that would change.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import time
from typing import Any

from .model import (CheckRun, CheckState, Feedback, FeedbackKind, IssueRef,
                    MergeState, PullRequestView)


class GhError(RuntimeError):
    pass


class GhForge:
    def __init__(self, executable: str = "gh", timeout: int = 60) -> None:
        self._gh = executable
        self._timeout = timeout
        self._login: str | None = None
        self._repo_ids: dict[str, str] = {}

    # -- identity -----------------------------------------------------------

    @property
    def login(self) -> str:
        """Who we are on the forge. Cached: it is asked once per pass otherwise.

        Needed to tell our own comments from a human's, without which the bot
        reviews itself forever.
        """
        if self._login is None:
            self._login = self._json(["api", "user", "--jq", ".login"], raw=True).strip()
        return self._login

    # -- reads --------------------------------------------------------------

    def list_issues(self, repo: str, labels: tuple[str, ...]) -> list[IssueRef]:
        argv = ["issue", "list", "--repo", repo, "--state", "open", "--limit", "50",
                "--json", "number,title,body,url,labels,state"]
        for label in labels:
            argv += ["--label", label]
        return [_issue_from(repo, entry) for entry in self._json(argv)]

    def get_issue(self, repo: str, number: int) -> IssueRef:
        argv = ["issue", "view", str(number), "--repo", repo,
                "--json", "number,title,body,url,labels,state,id"]
        return _issue_from(repo, self._json(argv))

    def repo_node_id(self, repo: str) -> str:
        """The repository's GraphQL id. Cached: it never changes for a given repo."""
        if repo not in self._repo_ids:
            self._repo_ids[repo] = self._json(["api", f"repos/{repo}", "--jq", ".node_id"],
                                              raw=True).strip()
        return self._repo_ids[repo]

    def find_pull_request(self, repo: str, head: str) -> PullRequestView | None:
        argv = ["pr", "list", "--repo", repo, "--head", head, "--state", "all", "--limit", "1",
                "--json", "number,url,headRefName,isDraft,state,reviewDecision,mergedAt"]
        found = self._json(argv)
        if not found:
            return None
        view = _pr_from(found[0])
        # `gh pr list` does not carry the GraphQL id, the head oid, or whether anyone
        # reviewed - and all three decide how the branch may be updated. One extra
        # call rather than a second source of truth about the same pull request.
        detail = self._json(["pr", "view", str(view.number), "--repo", repo,
                             "--json", "id,headRefOid,reviews"])
        reviewed = any(
            (review.get("author") or {}).get("login") != self.login
            for review in detail.get("reviews") or ()
        )
        return dataclasses.replace(
            view, node_id=detail.get("id") or "",
            head_sha=detail.get("headRefOid") or "", reviewed=reviewed,
        )

    def merge_state(self, repo: str, pr: int, attempts: int = 3,
                    pause_seconds: float = 2.0) -> MergeState:
        """Whether the branch still merges into its base.

        GitHub computes this LAZILY: the first read after a push is almost always
        UNKNOWN, and asking again is what makes it settle. Retrying here rather than
        in the driver, because "ask again in a moment" is a property of this API and
        of nothing else - and a caller who reads UNKNOWN once and moves on will ask
        a human to review a branch that does not merge.
        """
        for attempt in range(attempts):
            raw = self._json(["pr", "view", str(pr), "--repo", repo,
                              "--json", "mergeStateStatus,mergeable"])
            state = _merge_state_from(raw)
            if state is not MergeState.UNKNOWN:
                return state
            if attempt < attempts - 1:
                time.sleep(pause_seconds)
        return MergeState.UNKNOWN

    def update_branch(self, repo: str, pull: PullRequestView, method: str) -> bool:
        """Ask GitHub to bring the branch up to date, server-side. No checkout at all.

        `updatePullRequestBranch` takes updateMethod REBASE or MERGE (introspected
        from the schema, 2026-08-28), so the whole no-conflict case costs one API
        call and zero agent tokens - the branch never has to exist on this machine.

        `expectedHeadOid` is optimistic concurrency: if the head moved since we
        looked, GitHub refuses instead of throwing away whatever moved it. Omitting
        it is how a bot silently discards a push somebody else just made.
        """
        if not pull.node_id:
            raise GhError(f"pull request {pull.number} has no node id, cannot update its branch")
        query = ("mutation($pr: ID!, $oid: GitObjectID, $method: PullRequestBranchUpdateMethod) {"
                 "  updatePullRequestBranch(input: {pullRequestId: $pr, expectedHeadOid: $oid,"
                 "                                  updateMethod: $method}) {"
                 "    pullRequest { headRefOid }"
                 "  }"
                 "}")
        argv = ["api", "graphql", "-f", f"query={query}",
                "-F", f"pr={pull.node_id}", "-F", f"method={method}"]
        if pull.head_sha:
            argv += ["-F", f"oid={pull.head_sha}"]
        out = self._run(argv, check=False)
        return '"headRefOid"' in out

    def link_branch_to_issue(self, repo: str, issue_node_id: str, repo_node_id: str,
                             branch: str, oid: str = "") -> bool:
        """Fill the issue's "Development" section, the way the web button does.

        GitHub's own button also imposes ITS naming; this mutation does the same
        linking with a name we chose, so the convention and the platform link stop
        being an either/or.
        """
        query = ("mutation($issue: ID!, $repo: ID!, $name: String, $oid: GitObjectID) {"
                 "  createLinkedBranch(input: {issueId: $issue, repositoryId: $repo,"
                 "                             name: $name, oid: $oid}) {"
                 "    linkedBranch { ref { name } }"
                 "  }"
                 "}")
        argv = ["api", "graphql", "-f", f"query={query}",
                "-F", f"issue={issue_node_id}", "-F", f"repo={repo_node_id}",
                "-F", f"name={branch}"]
        if oid:
            argv += ["-F", f"oid={oid}"]
        return '"linkedBranch"' in self._run(argv, check=False)

    def base_commits_since(self, repo: str, base: str, head_sha: str, limit: int = 30) -> list[str]:
        """What landed on the base that this branch has not seen. One line per commit.

        This is the context a conflict resolution actually needs: not "there is a
        conflict in file X", but "here is what the other change was trying to do".
        """
        out = self._run(["api", f"repos/{repo}/compare/{head_sha}...{base}",
                         "--jq", ".commits[] | \"\\(.sha[0:7]) \\(.commit.message | split(\"\\n\")[0])\""],
                        check=False)
        return [line for line in out.strip().splitlines() if line][:limit]

    def checks(self, repo: str, pr: int) -> tuple[CheckState, tuple[CheckRun, ...]]:
        """What CI says, folded into one state plus the runs that are red.

        Read through `gh pr view` rather than `gh pr checks --json`, and the
        durable reason is the second one: both node types are handled. CheckRun is
        Actions, StatusContext is a commit status posted by anything else, and a
        repository wired to an external CI would otherwise report "no checks" while
        being red.

        The original reason has expired and is kept as a dated fact rather than a
        live justification: `--json` was absent from `gh pr checks` in 2.46 (the
        version Ubuntu shipped), and it exists in 2.100. A justification that stops
        being true while the code stays right is how a comment starts lying.
        """
        argv = ["pr", "view", str(pr), "--repo", repo, "--json", "statusCheckRollup"]
        rollup = self._json(argv).get("statusCheckRollup") or []
        if not rollup:
            return CheckState.NONE, ()

        runs = tuple(_check_from(node) for node in rollup)
        failing = tuple(run for run in runs if run.state is CheckState.FAILURE)
        if failing:
            return CheckState.FAILURE, failing
        if any(run.state is CheckState.PENDING for run in runs):
            return CheckState.PENDING, ()
        return CheckState.SUCCESS, ()

    def failing_logs(self, repo: str, runs: tuple[CheckRun, ...], max_bytes: int = 12000) -> str:
        """The log of each red job, tail-trimmed, so the agent reads the error itself.

        Two sources, tried in this order, and the order was MEASURED rather than
        assumed (2026-08-27, gh 2.46, job 88891871837):

        1. `gh run view --job <id> --log-failed`. Pre-filtered to the steps that
           actually failed, so it is by far the cheapest thing to put in a prompt.
           It returned ZERO bytes on a real failed job, and so did `--log`.
        2. `gh api repos/<repo>/actions/jobs/<id>/logs`. Returned the full, real
           log for that same job. It is the fallback precisely because it is the
           one that works when the convenient one silently returns nothing.

        Trimmed from the FRONT: a build error is at the end. The trim is announced,
        so a truncated log is never read as a short one - an agent told "here is the
        log" that ends mid-error will confidently fix the wrong thing.
        """
        chunks: list[str] = []
        budget = max_bytes
        for run in runs:
            if budget <= 0:
                chunks.append("[... journaux des jobs suivants omis, budget atteint ...]")
                break
            head = f"### {run.name} ({run.workflow})\n{run.url}"
            if not run.job_id:
                chunks.append(f"{head}\n\n[pas un job GitHub Actions : journal non "
                              f"recuperable par l'API, ouvrir l'URL]")
                continue

            raw = self._run(["run", "view", "--repo", repo, "--job", run.job_id,
                             "--log-failed"], check=False)
            source = "--log-failed"
            if not raw.strip():
                raw = self._run(["api", f"repos/{repo}/actions/jobs/{run.job_id}/logs"],
                                check=False)
                source = "api jobs/logs (repli)"
            if not raw.strip():
                chunks.append(f"{head}\n\n[journal introuvable : expire (90 jours) ou "
                              f"supprime. Les deux sources ont rendu zero octet.]")
                continue

            slice_budget = min(budget, max(2000, max_bytes // max(1, len(runs))))
            trimmed = raw[-slice_budget:]
            if len(raw) > len(trimmed):
                trimmed = (f"[... {len(raw) - len(trimmed)} octets omis EN TETE, "
                           f"la fin du journal suit ...]\n" + trimmed)
            budget -= len(trimmed)
            chunks.append(f"{head}\nsource : {source}\n\n{trimmed}")
        return "\n\n".join(chunks)

    def collect_feedback(self, repo: str, pr: int, issue: int) -> list[Feedback]:
        """Everything a human said, in one flat list, ours filtered out.

        Four endpoints because GitHub keeps four kinds of saying-something in four
        places, and a review loop that reads only one of them silently ignores the
        others - which reads, to the human, as being ignored.
        """
        items: list[Feedback] = []

        if pr:
            for review in self._json(["api", f"repos/{repo}/pulls/{pr}/reviews?per_page=100"]):
                author = (review.get("user") or {}).get("login", "")
                state = review.get("state", "")
                body = (review.get("body") or "").strip()
                # A COMMENTED review with no body is the envelope around inline
                # comments, which are collected below. Keeping it would feed the
                # agent an empty remark it cannot answer.
                if author == self.login or (state == "COMMENTED" and not body):
                    continue
                items.append(Feedback(
                    ident=f"review:{review['id']}", kind=FeedbackKind.REVIEW, author=author,
                    body=body or f"(revue {state} sans commentaire)",
                    created_at=review.get("submitted_at") or "", state=state,
                ))

            for comment in self._json(["api", f"repos/{repo}/pulls/{pr}/comments?per_page=100"]):
                author = (comment.get("user") or {}).get("login", "")
                if author == self.login:
                    continue
                items.append(Feedback(
                    ident=f"inline:{comment['id']}", kind=FeedbackKind.INLINE, author=author,
                    body=(comment.get("body") or "").strip(),
                    created_at=comment.get("created_at") or "",
                    path=comment.get("path") or "",
                    line=comment.get("line") or comment.get("original_line") or 0,
                ))

            for comment in self._json(["api", f"repos/{repo}/issues/{pr}/comments?per_page=100"]):
                author = (comment.get("user") or {}).get("login", "")
                if author == self.login:
                    continue
                items.append(Feedback(
                    ident=f"conv:{comment['id']}", kind=FeedbackKind.CONVERSATION, author=author,
                    body=(comment.get("body") or "").strip(),
                    created_at=comment.get("created_at") or "",
                ))

        for comment in self._json(["api", f"repos/{repo}/issues/{issue}/comments?per_page=100"]):
            author = (comment.get("user") or {}).get("login", "")
            if author == self.login:
                continue
            items.append(Feedback(
                ident=f"issue:{comment['id']}", kind=FeedbackKind.ISSUE, author=author,
                body=(comment.get("body") or "").strip(),
                created_at=comment.get("created_at") or "",
            ))

        items.sort(key=lambda item: item.created_at)
        return items

    # -- writes -------------------------------------------------------------

    def create_draft_pull_request(
        self, repo: str, head: str, base: str, title: str, body: str
    ) -> PullRequestView:
        self._run(["pr", "create", "--repo", repo, "--head", head, "--base", base,
                   "--title", title, "--body-file", "-", "--draft"], stdin=body)
        found = self.find_pull_request(repo, head)
        if found is None:
            raise GhError(f"pull request created for {head} but not found afterwards")
        return found

    def mark_ready(self, repo: str, number: int) -> None:
        self._run(["pr", "ready", str(number), "--repo", repo])

    def request_review(self, repo: str, number: int, reviewers: tuple[str, ...]) -> None:
        if not reviewers:
            return
        # Requesting a review IS the notification: GitHub already knows how to
        # reach the human on every device they own. Building a notifier next to it
        # would be a second, worse one.
        argv = ["pr", "edit", str(number), "--repo", repo]
        for reviewer in reviewers:
            argv += ["--add-reviewer", reviewer]
        self._run(argv)

    def comment_on_pull_request(self, repo: str, number: int, body: str,
                                attachments: tuple[tuple[str, str], ...] = (),
                                cwd: str | None = None) -> None:
        """Poste un commentaire, avec ses images ou videos si la forge sait les rendre.

        `--attach` existe depuis gh 2.99.0 (mesure : absent en 2.98). Les chemins
        sont RELATIFS et la commande tourne depuis `cwd`, pour que la reference
        ecrite dans le corps reste lisible si l'envoi echoue : un `![x](rendu.png)`
        casse se voit, un chemin absolu de la machine de quelqu'un d'autre est du
        bruit que personne ne sait interpreter.

        gh reecrit en place toute reference que le corps contient deja, et ajoute
        a la fin celles qu'il ne trouve pas.
        """
        argv = ["pr", "comment", str(number), "--repo", repo, "--body-file", "-"]
        for path, caption in attachments:
            argv += ["--attach", f"{path}#{caption}" if caption else path]
        self._run(argv, stdin=body, cwd=cwd)

    def comment_on_issue(self, repo: str, number: int, body: str) -> None:
        self._run(["issue", "comment", str(number), "--repo", repo, "--body-file", "-"], stdin=body)

    # -- plumbing -----------------------------------------------------------

    def _json(self, argv: list[str], raw: bool = False) -> Any:
        out = self._run(argv)
        if raw:
            return out
        return json.loads(out or "[]")

    def version(self) -> tuple[int, int, int]:
        """La version de gh, en trois entiers. Ce qui est disponible en depend.

        Demandee plutot que supposee : `--attach` n'existe pas avant 2.99.0 et
        `gh pr checks --json` pas avant 2.6x, donc un drapeau inconnu echouerait
        au milieu d'un run, ce qui est la pire facon de l'apprendre.
        """
        raw = self._run(["--version"], check=False).split()
        for word in raw:
            parts = word.split(".")
            if len(parts) == 3 and all(part.isdigit() for part in parts):
                return tuple(int(part) for part in parts)  # type: ignore[return-value]
        return (0, 0, 0)

    def supports_attachments(self) -> bool:
        return self.version() >= (2, 99, 0)

    def _run(self, argv: list[str], stdin: str | None = None, check: bool = True,
             cwd: str | None = None) -> str:
        done = subprocess.run(
            [self._gh, *argv], input=stdin, capture_output=True, text=True,
            timeout=self._timeout, cwd=cwd,
        )
        if check and done.returncode != 0:
            raise GhError(f"gh {' '.join(argv)} -> {done.returncode}: {done.stderr.strip()[:500]}")
        return done.stdout


def _issue_from(repo: str, entry: dict[str, Any]) -> IssueRef:
    return IssueRef(
        repo=repo, number=entry["number"], title=entry.get("title", ""),
        body=entry.get("body") or "", url=entry.get("url", ""),
        labels=tuple(label["name"] for label in entry.get("labels", ())),
        state=entry.get("state", "OPEN"),
        node_id=entry.get("id") or "",
    )


def _pr_from(entry: dict[str, Any]) -> PullRequestView:
    return PullRequestView(
        number=entry["number"], url=entry.get("url", ""), head=entry.get("headRefName", ""),
        is_draft=bool(entry.get("isDraft")), state=entry.get("state", ""),
        review_decision=entry.get("reviewDecision") or "",
        merged=bool(entry.get("mergedAt")),
        head_sha=entry.get("headRefOid") or "",
    )


def _merge_state_from(raw: dict[str, Any]) -> MergeState:
    """Fold GitHub's two answers into one, refusing to invent the missing case.

    `mergeable` says CONFLICTING / MERGEABLE / UNKNOWN, `mergeStateStatus` says how.
    CONFLICTING is trusted even when the status has not settled, because a conflict
    reported once is a conflict - the lazy computation only ever moves TOWARDS an
    answer, never back to "actually it is fine".
    """
    mergeable = (raw.get("mergeable") or "UNKNOWN").upper()
    if mergeable == "CONFLICTING":
        return MergeState.DIRTY
    status = (raw.get("mergeStateStatus") or "UNKNOWN").upper()
    try:
        return MergeState(status)
    except ValueError:
        return MergeState.UNKNOWN


def _check_from(node: dict[str, Any]) -> CheckRun:
    if node.get("__typename") == "StatusContext":
        return CheckRun(
            name=node.get("context", "?"), workflow="commit status",
            state=_status_state(node.get("state", "")), url=node.get("targetUrl") or "",
        )
    return CheckRun(
        name=node.get("name", "?"), workflow=node.get("workflowName", ""),
        state=_run_state(node.get("status", ""), node.get("conclusion") or ""),
        url=node.get("detailsUrl") or "", job_id=_job_id(node.get("detailsUrl") or ""),
    )


def _run_state(status: str, conclusion: str) -> CheckState:
    if status.upper() != "COMPLETED":
        return CheckState.PENDING
    # SKIPPED and NEUTRAL are not failures: a job that opted out of running is not
    # a job that says no. Treating them as red would block on every conditional
    # workflow a repository has.
    if conclusion.upper() in ("SUCCESS", "SKIPPED", "NEUTRAL"):
        return CheckState.SUCCESS
    return CheckState.FAILURE


def _status_state(state: str) -> CheckState:
    upper = state.upper()
    if upper == "SUCCESS":
        return CheckState.SUCCESS
    if upper in ("PENDING", "EXPECTED"):
        return CheckState.PENDING
    return CheckState.FAILURE


def _job_id(details_url: str) -> str:
    """Pull the job id out of .../actions/runs/<run>/job/<job>. Empty when absent."""
    marker = "/job/"
    if marker not in details_url:
        return ""
    tail = details_url.rsplit(marker, 1)[1]
    return "".join(character for character in tail if character.isdigit())
