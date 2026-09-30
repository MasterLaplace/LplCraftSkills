"""What the agent is told, and the shape of what it must answer.

Every run answers a schema, never prose. That is the whole reason the driver can
be a state machine: reading a verdict out of a paragraph is a parser nobody can
keep correct, and a bot that mis-reads its own success is a bot that asks for
review on nothing.

The rails live in CONTRACT and are repeated in every prompt on purpose. A rule
stated once, in a system prompt, is a rule the model can lose behind a long tool
transcript.
"""

from __future__ import annotations

from typing import Any

from .model import Feedback, FeedbackKind, IssueRef, Record

CONTRACT = """\
You are launched UNATTENDED by an orchestrator (forgeron). Nobody will answer
a question asked in your final answer: the only channel to the human is the
forge (issue, pull request), and the only channel to the orchestrator is the final
JSON required by the schema.

Permissions, strictly bounded:
- you may commit and push ON THE BRANCH {branch} and on it alone;
- you NEVER push to {base}, you NEVER push --force, you NEVER merge,
  you NEVER close the issue, you NEVER modify .github/workflows/;
- you stay in {worktree}. It is a dedicated git worktree: the human's checkout
  is elsewhere and must not be touched;
- no `git rebase`, no `git reset --hard` on anything already pushed: a human reads
  this diff as it goes, and rewriting history under their eyes cancels their review.

Method, non-negotiable:
- invoke the `cycle-de-dev` skill (Skill tool) before writing a line, and follow
  its exit gates. It delegates to the other skills, let it;
- a claim is proved: you do not declare a gate passed without having just run
  the command that shows it, and you copy that command into
  `commands_run`. "it should work" is not a result;
- no new warning gets past a commit;
- if you are blocked (ambiguity, missing dependency, access denied), you answer
  verdict="blocked" with `blocked_reason`. Guessing costs more than asking.

Commits: Conventional Commits, in English, with no Co-Authored-By line and no
mention of an AI tool. The repository's author is MasterLaplace.
"""

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "branch_slug": {"type": "string", "description": "kebab-case, 2 to 5 words, no prefix"},
        "kind": {"type": "string", "enum": ["feat", "fix", "refactor", "docs", "test", "chore", "perf"]},
        "pr_title": {"type": "string"},
        "pr_body": {"type": "string", "description": "markdown: context, approach, criteria, out of scope"},
        "acceptance": {
            "type": "array",
            "items": {"type": "string"},
            "description": "falsifiable criteria, each one checkable by a command",
        },
        "files_expected": {"type": "array", "items": {"type": "string"}},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "empty if and only if nothing blocks the coding",
        },
    },
    "required": ["branch_slug", "kind", "pr_title", "pr_body", "acceptance", "risk", "questions"],
    "additionalProperties": False,
}

WORK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["ready_for_review", "blocked", "no_change_needed"]},
        "summary": {"type": "string", "description": "one paragraph, in English"},
        "commands_run": {"type": "array", "items": {"type": "string"}},
        "acceptance": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string"},
                    "met": {"type": "boolean"},
                    "evidence": {"type": "string", "description": "the output or the command that proves it"},
                },
                "required": ["criterion", "met", "evidence"],
                "additionalProperties": False,
            },
        },
        "pushed": {"type": "boolean"},
        "visuals": {
            "type": "array",
            "description": "empty unless the change is better seen than read",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "path RELATIVE to the worktree"},
                    "caption": {"type": "string", "description": "what the reader is looking at"},
                    "command": {"type": "string", "description": "the command that produces this file"},
                },
                "required": ["path", "caption", "command"],
                "additionalProperties": False,
            },
        },
        "blocked_reason": {"type": "string"},
        "answers": {
            "type": "array",
            "items": {"type": "string"},
            "description": "one answer per review remark handled, in the order received",
        },
    },
    "required": ["verdict", "summary", "commands_run", "acceptance", "pushed"],
    "additionalProperties": False,
}

WRAP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "followups": {
            "type": "array",
            "items": {"type": "string"},
            "description": "what is left and deserves its own issue",
        },
    },
    "required": ["summary", "followups"],
    "additionalProperties": False,
}


def contract(record: Record, base: str, exception: str = "") -> str:
    """The rails. `exception` widens exactly one of them, for exactly one phase.

    Written as an addition rather than by editing the rule, so the rule and its
    single exception are read together and the exception cannot outlive the phase
    that needed it.
    """
    text = CONTRACT.format(branch=record.branch or "(to be created)", base=base,
                           worktree=record.worktree)
    if exception:
        text += "\nEXCEPTION, valid ONLY for this round:\n" + exception
    return text


def plan_prompt(issue: IssueRef, answers: tuple[Feedback, ...] = ()) -> str:
    parts = [
        "PHASE 1 of 4: FRAME. You modify NO file in this phase.",
        "",
        f"Issue {issue.repo}#{issue.number}: {issue.title}",
        f"URL: {issue.url}",
        "",
        "Issue body:",
        _quote(issue.body or "(empty)"),
        "",
        "Invoke the `cadrer-et-planifier` skill, explore the repository to ground yourself in the real code,",
        "and return the plan in the required format.",
        "",
        "Two rules that decide the rest:",
        "- `acceptance` holds only FALSIFIABLE criteria, each one checkable by a command.",
        "  \"the code is clean\" is not one, \"the suite passes twice in a row\" is one;",
        "- `questions` is NOT a place to be polite: put there only what, left unanswered,",
        "  could make you build the wrong thing. If you put one there, no code will be",
        "  written and a human will be asked. An empty list is the normal answer.",
    ]
    if answers:
        parts += ["", "A human has answered since your last attempt:", _feedback_block(answers)]
    return "\n".join(parts)


VISUAL_CONTRACT = [
    "",
    "If the change is better SEEN than read, `visuals` lets you attach an image or",
    "a video to the pull request. Invoke `rendre-l-etat-visible` before producing one: a",
    "visual is only useful when the information is in the SHAPE and not in a value. Everywhere",
    "else a table of numbers beats a screenshot.",
    "",
    "The constraint is strict, and it is CHECKED, not believed: `command` must REPRODUCE",
    "`path`. The orchestrator sets the file aside, runs your command again, and attaches the visual",
    "only if it comes back. A file that does not regenerate is a screenshot, and a screenshot",
    "lies silently as soon as the code moves, since an image breaks no build.",
]


def implement_prompt(issue: IssueRef, plan: dict[str, Any], pr_url: str) -> str:
    criteria = "\n".join(f"- {item}" for item in plan.get("acceptance", ())) or "- (none)"
    return "\n".join([
        "PHASE 2 of 4: IMPLEMENT. The draft pull request is already open,",
        f"a human can read it while you work: {pr_url}",
        "",
        f"Issue {issue.repo}#{issue.number}: {issue.title}",
        "",
        "Acceptance criteria, taken from YOUR plan and already published in the pull request:",
        criteria,
        "",
        "Invoke `cycle-de-dev` and follow it: a red test first when the subject lends itself to it, code next,",
        "derived docs, and an exit gate proved by a command at every step.",
        "",
        "Finish with Conventional Commits commits and a `git push` on your branch.",
        "`pushed` must tell the truth: the orchestrator checks it against the state of git.",
        *VISUAL_CONTRACT,
    ])


def revise_prompt(issue: IssueRef, feedback: tuple[Feedback, ...], round_number: int) -> str:
    return "\n".join([
        f"PHASE 3 of 4: REVISE, round {round_number}.",
        f"A human reviewed your pull request for {issue.repo}#{issue.number} and left this:",
        "",
        _feedback_block(feedback),
        "",
        "For EACH remark, in order: either you handle it, or you explain why you do not.",
        "A remark skipped silently is the only forbidden answer.",
        "",
        "Invoke `trouver-la-cause` if the remark reports a bug: no fix without a root cause,",
        "and a fix that masks the symptom will be sent back by the next review.",
        "",
        "Fill `answers` with one line per remark, in the order received: these lines are published",
        "as they are on the pull request, they are your answer to the reviewer.",
        "Then commit and push on your branch.",
        *VISUAL_CONTRACT,
    ])


def fix_checks_prompt(issue: IssueRef, failing: tuple, logs: str, attempt: int,
                      max_attempts: int) -> str:
    names = ", ".join(f"`{run.name}`" for run in failing) or "(unknown)"
    return "\n".join([
        f"PHASE 3b: CONTINUOUS INTEGRATION IS RED. Attempt {attempt} of {max_attempts}.",
        f"Issue {issue.repo}#{issue.number}. Failing jobs: {names}.",
        "",
        "Here are the logs, trimmed from the start (so the error is there, the setup is not):",
        "",
        "```",
        logs.strip() or "(no log retrievable)",
        "```",
        "",
        "Invoke `trouver-la-cause`. Read the error message IN FULL before touching anything:",
        "a fix placed on the first red line repairs the symptom and leaves the",
        "cause in place, and the job will turn red again on the next round.",
        "",
        "Three traps to name explicitly if you meet them, rather than work around:",
        "- if the job fails for an ENVIRONMENT reason (missing secret, quota, runner),",
        "  it is not your code: answer verdict=\"blocked\" and say so;",
        "- if you cannot reproduce the failure locally, say so in `summary` rather than",
        "  push a blind fix and let CI decide in your place;",
        "- disabling, skipping or making tolerant a failing test is NOT a fix. If the",
        "  test is right, fix the code; if it is wrong, fix the test and explain why.",
        "",
        "You NEVER modify .github/workflows/: the token has no right to, and the push",
        "would be refused. Then commit and push.",
    ])


CONFLICT_EXCEPTION = """\
- you may run `git rebase --continue`, `git merge --continue`, `git add` on the files
  you resolve, and `git rebase --abort` if you give up. Rewriting history is
  allowed HERE and nowhere else, because it is the only way to replay your branch
  onto a base that has moved;
- you do NOT push yourself. The orchestrator pushes, with --force-with-lease, and only
  after checking that no conflicted file is left. A force push by you would go
  around that check.
"""


def resolve_conflict_prompt(issue: IssueRef, base: str, method: str,
                            conflicted: tuple[str, ...], landed: tuple[str, ...],
                            attempt: int, max_attempts: int) -> str:
    files = "\n".join(f"- `{path}`" for path in conflicted) or "- (none?)"
    commits = "\n".join(f"- {line}" for line in landed) or "- (unknown)"
    verb = "rebase" if method.upper() == "REBASE" else "merge"
    return "\n".join([
        f"PHASE 3c: CONFLICT WITH `{base}`. Attempt {attempt} of {max_attempts}.",
        f"Issue {issue.repo}#{issue.number}. A {verb} of `{base}` onto your branch is IN PROGRESS",
        "and stopped on conflicts.",
        "",
        "Conflicted files:",
        files,
        "",
        f"What landed on `{base}` while you were working, newest first:",
        commits,
        "",
        "**The rule that counts: a conflict is resolved by understanding BOTH intentions, not by**",
        "**picking a side.** For each hunk:",
        "1. read what YOUR change meant to do (your diff, your commits, the issue);",
        "2. read what the OTHER change meant to do (the list above, and `git log -p` on",
        f"   the commits of `{base}` that touch this file);",
        "3. write the version that holds both. If they are truly incompatible, it is a",
        "   design decision and not a text conflict: answer verdict=\"blocked\",",
        "   explaining which of the two intentions must give way, and why.",
        "",
        "⚠ `git checkout --ours` and `--theirs` are forbidden blindly. They resolve nothing:",
        "they throw away half of someone's work, and the result compiles, so nobody sees it",
        "until someone misses the lost feature.",
        "",
        "When everything is resolved: `git add` the files, then finish the operation",
        f"(`git {'rebase' if method.upper() == 'REBASE' else 'merge'} --continue`).",
        "Then check that the suite passes: a resolution that compiles is not a resolution",
        "that works, and that is exactly the class of bug a conflict produces.",
        "",
        "In `summary`, say for each file what you kept from each side. It is published",
        "as it is on the pull request: it is the only trace the reviewer will have of your arbitration.",
    ])


def wrap_prompt(issue: IssueRef, pr: int) -> str:
    return "\n".join([
        "PHASE 4 of 4: CLOSE. The pull request "
        f"#{pr} was APPROVED AND MERGED by the human. The work is accepted.",
        "",
        "You modify nothing more and push nothing more. Two things only:",
        "- `summary`: what was delivered, in one paragraph, as it would be written in a changelog;",
        "- `followups`: what you saw go by and deserves ITS OWN issue. Nothing invented to",
        "  fill the list; an empty list is an answer.",
    ])


def _feedback_block(items: tuple[Feedback, ...]) -> str:
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        where = f" ({item.path}:{item.line})" if item.kind is FeedbackKind.INLINE else ""
        state = f" [{item.state}]" if item.state else ""
        lines.append(f"{index}. @{item.author}{state}{where}:")
        lines.append(_quote(item.body))
    return "\n".join(lines)


def _quote(text: str) -> str:
    return "\n".join(f"  > {line}" for line in text.strip().splitlines() or [""])
