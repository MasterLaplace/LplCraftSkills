"""The command line. It is the documentation: `forgeron --help` is the contract.

Every command prints a human line by default and a machine object under --json,
and no command performs a write on the forge unless it says so in its own help.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import subprocess
import sys
import uuid
from functools import partial

from . import __version__, attribution, config as config_module, etabli as etabli_module
from . import etabli_projects
from .claude_agent import ClaudeAgent
from .engine import Engine
from .gh_etabli import GhEtabli, GhEtabliError
from .gh_forge import GhForge
from .git_workspace import GitWorkspace
from .journal import Journal
from .regenerator import ShellRegenerator
from .model import Phase, Record
from .sources import IntervalTrigger
from .store import Store

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_ENVIRONMENT = 3
EXIT_BLOCKED = 4
EXIT_DRIFT = 5

DEFAULT_CONFIG = os.path.expanduser("~/.forgeron/config.json")
DEFAULT_ETABLI = os.path.expanduser("~/.forgeron/etabli.json")
ONLY_DOMAINS = (*etabli_module.DOMAINS, "projects")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        parser.print_help()
        return EXIT_USAGE
    return args.handler(args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forgeron",
        description=(
            "Listens to labelled GitHub issues, opens a draft pull request, "
            "codes the solution with the craft-skills, requests review, and loops on your "
            "comments until the merge."
        ),
        epilog=(
            "State: %s/state · journal: %s/journal.jsonl\n"
            "Nothing is written on the forge without --write." % (
                config_module.DEFAULT_HOME, config_module.DEFAULT_HOME)
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"forgeron {__version__}")
    parser.add_argument("--config", default=DEFAULT_CONFIG, metavar="FILE",
                        help="JSON configuration (default: %(default)s)")
    parser.add_argument("--json", action="store_true", help="machine output, nothing else on stdout")
    parser.add_argument("--verbose", action="store_true", help="adds the debug events")
    sub = parser.add_subparsers(title="commands")

    doctor = sub.add_parser("doctor", help="checks the environment without writing anything")
    doctor.set_defaults(handler=_doctor)

    show_config = sub.add_parser("config", help="prints the effective configuration, defaults included")
    show_config.add_argument("--init", action="store_true",
                             help="writes a configuration skeleton if the file is missing")
    show_config.set_defaults(handler=_config)

    status = sub.add_parser("status", help="state of each tracked issue")
    status.set_defaults(handler=_status)

    once = sub.add_parser("once", help="a single pass of the reconciler, then exit")
    once.add_argument("--write", action="store_true",
                      help="allows writes (forge, git, agent). Without this flag: simulation")
    once.set_defaults(handler=_once)

    run = sub.add_parser("run", help="loop: one pass every --interval seconds")
    run.add_argument("--interval", type=int, default=0, metavar="SECONDS",
                     help="polling period (default: the one from the configuration)")
    run.add_argument("--passes", type=int, default=0, metavar="N",
                     help="stops after N passes (0 = never)")
    run.add_argument("--write", action="store_true", help="allows writes")
    run.set_defaults(handler=_run)

    hook = sub.add_parser(
        "hook", help="the commit-msg hook that removes any AI attribution from a message")
    hook.add_argument("--install", metavar="DIRECTORY",
                      help="writes the hook into DIRECTORY and makes it executable")
    hook.set_defaults(handler=_hook)

    adopt = sub.add_parser("adopt", help="takes charge of an issue without waiting for the label")
    adopt.add_argument("repo", help="owner/name, must be in the allowlist")
    adopt.add_argument("issue", type=int)
    adopt.set_defaults(handler=_adopt)

    forget = sub.add_parser("forget", help="forgets an issue (the local state, not the branch)")
    forget.add_argument("repo")
    forget.add_argument("issue", type=int)
    forget.set_defaults(handler=_forget)

    etabli = sub.add_parser(
        "etabli",
        help="apply the declared configuration of repositories and projects: labels, settings, security, "
             "branch rules, project fields, views and links",
        description=(
            "Reads the declared configuration, observes each repository and project, and prints the plan.\n"
            "Without --write, nothing is written. With --write, applies the plan, then reads them again\n"
            "and prints what is left: a second pass that still proposes something is a disagreement\n"
            "between the tool and the forge. A project created by the run gets its fields, views and\n"
            "links in the same run. Project workflows are only read: the forge has no API to set them.\n"
            "Machine output: forgeron --json etabli."
        ),
        epilog=(
            "Symbols: + create  ~ update  > rename  - delete  ? undeclared  ! blocked  . skipped\n"
            "Exit: 0 nothing to change, 2 invalid configuration, 3 forge unreachable or a write\n"
            "refused, 4 something blocked or nothing could be checked, 5 changes left to apply.\n"
            "When several apply, 3 wins over 5, and 5 over 4."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    etabli.add_argument("--file", default=DEFAULT_ETABLI, metavar="FILE",
                        help="the declared configuration, shaped like etabli.example.json "
                             "(default: %(default)s)")
    etabli.add_argument("--repo", action="append", default=[], metavar="OWNER/NAME",
                        help="only this repository, which must be declared (repeatable)")
    etabli.add_argument("--project", action="append", default=[], metavar="OWNER/TITLE",
                        help="only this project, which must be declared (repeatable)")
    etabli.add_argument("--only", default="", metavar="DOMAINS",
                        help="only the named domains, among " + ",".join(ONLY_DOMAINS))
    etabli.add_argument("--write", action="store_true",
                        help="apply the plan, then read each repository and project again. "
                             "Without it: the plan only")
    etabli.set_defaults(handler=_etabli)

    return parser


# -- commands ---------------------------------------------------------------

def _doctor(args: argparse.Namespace) -> int:
    checks: list[dict[str, object]] = []

    def check(name: str, ok: bool, detail: str, optional: bool = False) -> None:
        # An optional check that fails is a NOTE, not a failure. Reporting both the
        # same way is how a real gap hides among things nobody needs.
        checks.append({"check": name, "ok": ok, "detail": detail, "optional": optional})

    for binary in ("gh", "git", "claude"):
        found = _which(binary)
        check(f"{binary} present", bool(found), found or "not found in the PATH")

    try:
        auth = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=20)
        scopes = ""
        for line in auth.stderr.splitlines() + auth.stdout.splitlines():
            if "Token scopes" in line:
                scopes = line.split(":", 1)[1].strip()
        check("gh authenticated", auth.returncode == 0, scopes or "no scope read")
        check("repo scope", "'repo'" in scopes, "needed for issues and pull requests")
        version = subprocess.run(["gh", "--version"], capture_output=True, text=True,
                                 timeout=20).stdout.split()
        triple = next((tuple(int(n) for n in w.split("."))
                       for w in version if w.count(".") == 2
                       and all(n.isdigit() for n in w.split("."))), (0, 0, 0))
        check("gh >= 2.99 (attachments)", triple >= (2, 99, 0),
              f"{'.'.join(str(n) for n in triple)}: --attach lets an image "
              f"or a video be attached to a pull request", optional=True)
        check("admin:repo_hook scope", "admin:repo_hook" in scopes,
              "only required for gh webhook forward: gh auth refresh -s admin:repo_hook",
              optional=True)
        check("workflow scope", "workflow" in scopes,
              "missing = the agent CANNOT push .github/workflows, which bounds the damage",
              optional=True)
    except Exception as failure:
        check("gh authenticated", False, str(failure)[:200])

    check("attribution: the hook acts", *_probe_commit_msg_hook())

    try:
        configuration = config_module.load(args.config)
        check("configuration read", True, args.config)
        for repo in configuration.repos:
            check(f"clone {repo.slug}", os.path.isdir(os.path.join(repo.path, ".git")), repo.path)
        check(f"agent {configuration.agent or '(none)'}",
              *_agent_installed(configuration.agent, USER_AGENTS_DIR))
    except FileNotFoundError:
        check("configuration read", False, f"{args.config} missing — run: forgeron config --init")
    except Exception as failure:
        check("configuration read", False, str(failure)[:200])

    failed = [entry for entry in checks if not entry["ok"] and not entry["optional"]]
    if args.json:
        print(json.dumps({"checks": checks, "ok": not failed}, ensure_ascii=False, indent=2))
    else:
        for entry in checks:
            mark = "ok" if entry["ok"] else ("note" if entry["optional"] else "MISSING")
            print(f"{mark:<8}{entry['check']:<28}{entry['detail']}")
        required = [entry for entry in checks if not entry["optional"]]
        print(f"\n{len(required) - len(failed)}/{len(required)} required checks passed, "
              f"{len(checks) - len(required)} notes")
    return EXIT_OK if not failed else EXIT_ENVIRONMENT


USER_AGENTS_DIR = os.path.expanduser("~/.claude/agents")


def _agent_installed(name: str, agents_dir: str) -> tuple[bool, str]:
    if not name:
        return True, "no agent: the contract alone, without the method's hooks"
    path = os.path.join(agents_dir, f"{name}.md")
    if os.path.isfile(path):
        return True, path
    return False, (f"{path} missing: run ../install.sh from the craft-skills repository, "
                   f"or set \"agent\": \"\" in the configuration to do without it")


def _config(args: argparse.Namespace) -> int:
    if args.init and not os.path.exists(args.config):
        os.makedirs(os.path.dirname(args.config) or ".", exist_ok=True)
        skeleton = {
            "repos": [{
                "slug": "OWNER/NAME",
                "path": os.path.expanduser("~/OWNER-NAME"),
                "base": "main",
                "labels": ["forgeron"],
                "hold_label": "forgeron:hold",
                "reviewers": ["OWNER"],
            }],
            "limits": {"max_rounds": 6, "max_spend_usd": 12.0, "auto_merge": False},
            "max_concurrent": 1,
            "poll_seconds": 60,
            "model": "sonnet",
            "budget_per_run_usd": 3.0,
            "continuity": "resume",
            "agent": "artisan",
        }
        with open(args.config, "w", encoding="utf-8") as handle:
            json.dump(skeleton, handle, ensure_ascii=False, indent=2)
        print(f"written: {args.config}", file=sys.stderr)

    try:
        effective = config_module.load(args.config)
    except FileNotFoundError:
        print(f"{args.config} missing. Run: forgeron config --init", file=sys.stderr)
        return EXIT_USAGE
    payload = effective.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return EXIT_OK


def _status(args: argparse.Namespace) -> int:
    configuration = _load_or_die(args)
    store = Store(configuration.state_dir)
    records = store.all()
    if args.json:
        payload = []
        for record in records:
            item = dataclasses.asdict(record)
            item["phase"] = record.phase.value
            payload.append(item)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK

    if not records:
        print("no tracked issue")
        return EXIT_OK
    print(f"{'issue':<28}{'phase':<16}{'pr':>5} {'rounds':>6} {'usd':>7}  note")
    for record in records:
        print(f"{record.repo + '#' + str(record.issue):<28}{record.phase.value:<16}"
              f"{record.pr or '-':>5} {record.rounds:>6} {record.spent_usd:>7.2f}  {record.note[:60]}")
    blocked = [record for record in records if record.phase is Phase.BLOCKED]
    return EXIT_BLOCKED if blocked else EXIT_OK


def _once(args: argparse.Namespace) -> int:
    engine, journal = _build(args)
    decisions = engine.pass_once()
    if args.json:
        print(json.dumps([{"action": d.action.value, "phase": d.phase.value, "reason": d.reason}
                          for d in decisions], ensure_ascii=False, indent=2))
    return EXIT_OK


def _run(args: argparse.Namespace) -> int:
    configuration = _load_or_die(args)
    engine, journal = _build(args)
    trigger = IntervalTrigger(args.interval or configuration.poll_seconds, limit=args.passes)
    journal.emit("started", interval=args.interval or configuration.poll_seconds,
                 write=bool(args.write), repos=len(configuration.repos))
    try:
        for reason in trigger.ticks():
            journal.debug("tick", reason=reason)
            engine.pass_once()
    except KeyboardInterrupt:
        journal.emit("stopped", reason="interrupt")
    return EXIT_OK


def _hook(args: argparse.Namespace) -> int:
    """Emit the hook, or install it. The script is DERIVED from the package's patterns.

    Without `--install` it goes to standard output, which makes it composable:
    `forgeron hook > ~/.config/git/hooks/commit-msg`. The derived form exists so
    that the layer that prevents and the layer that checks cannot start to
    diverge on what counts as an attribution.
    """
    script = attribution.hook_script()
    if not args.install:
        print(script, end="")
        return EXIT_OK

    os.makedirs(args.install, exist_ok=True)
    target = os.path.join(args.install, "commit-msg")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(script)
    os.chmod(target, os.stat(target).st_mode | 0o111)
    print(f"written: {target}", file=sys.stderr)
    print("to wire it: git config --global core.hooksPath " + args.install, file=sys.stderr)
    return EXIT_OK


def _adopt(args: argparse.Namespace) -> int:
    configuration = _load_or_die(args)
    repo = configuration.repo(args.repo)
    store = Store(configuration.state_dir)
    if store.load(args.repo, args.issue) is not None:
        print(f"{args.repo}#{args.issue} is already tracked", file=sys.stderr)
        return EXIT_USAGE
    record = store.save(Record(
        repo=args.repo, issue=args.issue, phase=Phase.QUEUED, session_id=str(uuid.uuid4()),
        branch=f"forgeron/issue-{args.issue}",
        worktree=os.path.join(configuration.worktree_dir,
                              args.repo.replace("/", "__"), f"issue-{args.issue}"),
    ))
    print(json.dumps({"adopted": record.key, "session": record.session_id}) if args.json
          else f"adopted: {record.key} (session {record.session_id})")
    return EXIT_OK


def _forget(args: argparse.Namespace) -> int:
    configuration = _load_or_die(args)
    store = Store(configuration.state_dir)
    record = store.load(args.repo, args.issue)
    if record is None:
        print(f"{args.repo}#{args.issue} is not tracked", file=sys.stderr)
        return EXIT_USAGE
    os.remove(store.path_of(record))
    print(f"forgotten: {record.key} (worktree {record.worktree} kept)")
    return EXIT_OK


def _etabli(args: argparse.Namespace) -> int:
    try:
        desired = select_desired(etabli_module.load(args.file), args.repo, args.only, projects=args.project)
        projects = select_projects(etabli_projects.load_projects(args.file), args.project, args.repo,
                                   args.only)
        if not desired and not projects:
            raise etabli_module.ConfigError("--repo, --project and --only leave nothing to check: a "
                                            "project is checked only when \"projects\" is among --only, "
                                            "a repository only when one of its domains is")
    except FileNotFoundError:
        print(f"{args.file} missing: start from forgeron/etabli.example.json", file=sys.stderr)
        return EXIT_USAGE
    except etabli_module.ConfigError as failure:
        print(str(failure), file=sys.stderr)
        return EXIT_USAGE
    journal = Journal(_journal_path(args.config), echo=None)
    return run_etabli(desired, GhEtabli(), write=args.write, as_json=args.json, journal=journal,
                      projects=projects)


def _journal_path(config_path: str) -> str:
    fallback = os.path.join(config_module.DEFAULT_HOME, "journal.jsonl")
    if not os.path.exists(config_path):
        return fallback
    try:
        return config_module.load(config_path).journal_path
    except (OSError, ValueError, TypeError) as failure:
        print(f"{config_path} unreadable ({failure}): the journal goes to {fallback}", file=sys.stderr)
        return fallback


def select_desired(desired: tuple[etabli_module.Desired, ...], repos: list[str],
                   only: str, projects: list[str] = ()) -> tuple[etabli_module.Desired, ...]:
    declared = {want.slug for want in desired}
    unknown = [repo for repo in repos if repo not in declared]
    if unknown:
        raise etabli_module.ConfigError(f"--repo {', '.join(unknown)}: not declared in the configuration "
                                        f"({', '.join(sorted(declared))})")
    domains = _only(only)
    repo_domains = [domain for domain in domains if domain in etabli_module.DOMAINS]
    if (projects and not repos) or (domains and not repo_domains):
        return ()
    chosen = [want for want in desired if not repos or want.slug in repos]
    if repo_domains:
        chosen = [dataclasses.replace(want, domains=tuple(d for d in want.domains if d in repo_domains))
                  for want in chosen]
    return tuple(chosen)


def select_projects(projects: tuple[etabli_projects.DesiredProject, ...], names: list[str],
                    repos: list[str], only: str) -> tuple[etabli_projects.DesiredProject, ...]:
    declared = {project.key for project in projects}
    unknown = [name for name in names if name not in declared]
    if unknown:
        raise etabli_module.ConfigError(f"--project {', '.join(unknown)}: not declared in the configuration "
                                        f"({', '.join(sorted(declared)) or 'no project'})")
    domains = _only(only)
    if (domains and "projects" not in domains) or (repos and not names):
        return ()
    return tuple(project for project in projects if not names or project.key in names)


def _only(only: str) -> list[str]:
    domains = [domain for domain in only.split(",") if domain]
    wrong = [domain for domain in domains if domain not in ONLY_DOMAINS]
    if wrong:
        raise etabli_module.ConfigError(f"--only {', '.join(wrong)}: unknown domain, expected "
                                        f"{', '.join(ONLY_DOMAINS)}")
    return domains


def run_etabli(desired, adapter, *, write: bool, as_json: bool, journal=None, out=None,
               err=None, projects=()) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    journal = journal or Journal(None, echo=None)
    report = []
    for want in desired:
        report.append(_settle(want.slug, partial(_plan_repository, want, adapter), adapter, write, journal,
                              "repository", partial(_checked, want)))
    projects_report = [_settle(project.key, partial(_plan_project, project, adapter), adapter, write, journal,
                               "project", _project_checked)
                       for project in projects]
    everything = report + projects_report

    if as_json:
        print(json.dumps({"write": write, "repos": [_etabli_entry_json(entry) for entry in report],
                          "projects": [_etabli_entry_json(entry, "project") for entry in projects_report],
                          "exit": _etabli_exit(everything)}, ensure_ascii=False, indent=2), file=out)
    else:
        for entry in everything:
            _print_etabli_entry(entry, out)
        if not write and any(change.kind.actionable for entry in everything
                             for change in entry["remaining"] or ()):
            print("\nnothing was written: run again with --write to apply this plan", file=err)
    return _etabli_exit(everything)


def _plan_repository(want, adapter) -> list:
    return etabli_module.plan(want, adapter.observe(want.slug))


def _plan_project(project, adapter) -> list:
    return etabli_projects.plan_project(project, adapter.observe_project(project))


def _settle(name, observe_and_plan, adapter, write, journal, what, checked) -> dict:
    entry = {"repo": name, "planned": [], "applied": [], "failed": [], "remaining": [],
             "error": "", "checked": (), "what": what}
    try:
        planned = observe_and_plan()
    except GhEtabliError as failure:
        entry["error"] = str(failure)
        return entry
    remaining = planned
    applied, failed = [], []
    if write and any(change.kind.actionable for change in planned):
        rounds = [_first_round(planned)]
        catch_up = True
        while rounds:
            created = False
            for change in rounds.pop():
                if not change.kind.actionable:
                    continue
                try:
                    adapter.apply(change)
                    applied.append(change)
                    created = created or _creates_project(change)
                    journal.emit("etabli_applied", key=change.repo, **_journal_fields(change))
                except GhEtabliError as failure:
                    failed.append((change, str(failure)))
                    journal.emit("etabli_failed", key=change.repo, error=str(failure),
                                 **_journal_fields(change))
            try:
                remaining = observe_and_plan()
            except GhEtabliError as failure:
                entry["error"] = f"could not read the {what} again after writing: {failure}"
                remaining = None
                break
            if created and not failed and catch_up and not any(map(_creates_project, remaining)):
                catch_up = False
                rounds.append([change for change in remaining if not _creates_project(change)])
    entry.update(planned=planned, applied=applied, failed=failed, remaining=remaining,
                 checked=checked(planned))
    return entry


def _creates_project(change) -> bool:
    return change.domain == "project" and change.kind is etabli_module.Kind.CREATE


def _first_round(planned) -> list:
    creation = [change for change in planned if _creates_project(change)]
    return creation or planned


def _project_checked(planned) -> tuple[str, ...]:
    if any(change.kind is etabli_module.Kind.SKIPPED for change in planned):
        return ()
    return ("project",)


def _checked(want, planned) -> tuple[str, ...]:
    skipped = {change.domain for change in planned if change.kind is etabli_module.Kind.SKIPPED}
    if "repository" in skipped:
        return ()
    return tuple(domain for domain in etabli_module.declared_domains(want) if domain not in skipped)


def _journal_fields(change) -> dict:
    fields = change.to_dict()
    fields.pop("repo")
    return fields


def _etabli_exit(report) -> int:
    if any(entry["error"] or entry["failed"] for entry in report):
        return EXIT_ENVIRONMENT
    remaining = [change for entry in report for change in entry["remaining"] or ()]
    if any(change.kind.actionable for change in remaining):
        return EXIT_DRIFT
    if any(change.kind is etabli_module.Kind.BLOCKED for change in remaining) \
            or any(not entry["checked"] for entry in report):
        return EXIT_BLOCKED
    return EXIT_OK


def _etabli_entry_json(entry, what: str = "repo") -> dict:
    remaining = entry["remaining"]

    def shown(change) -> dict:
        fields = change.to_dict()
        if what != "repo":
            fields[what] = fields.pop("repo")
        return fields

    return {
        what: entry["repo"],
        "error": entry["error"],
        "checked": list(entry["checked"]),
        "planned": [shown(change) for change in entry["planned"]],
        "applied": [shown(change) for change in entry["applied"]],
        "failed": [{**shown(change), "error": reason} for change, reason in entry["failed"]],
        "remaining": None if remaining is None else [shown(change) for change in remaining],
    }


def _print_etabli_entry(entry, out) -> None:
    print(f"project {entry['repo']}" if entry.get("what") == "project" else entry["repo"], file=out)
    if entry["error"] and not entry["planned"]:
        print(f"  ERROR {entry['error']}", file=out)
        return
    if entry["applied"] or entry["failed"]:
        print(f"  applied: {len(entry['applied'])}, failed: {len(entry['failed'])}", file=out)
        for change in entry["applied"]:
            print(f"    {change.kind.value} {change.domain:<9} {_describe(change)}", file=out)
        for change, reason in entry["failed"]:
            print(f"    FAILED {change.domain:<9} {change.name}  {reason}", file=out)
        if entry["remaining"] is None:
            print(f"  ERROR {entry['error']}", file=out)
            print("  not read again: what is left on the forge is unknown", file=out)
            return
        print("  after reading again:", file=out)
    shown = entry["remaining"]
    for change in shown:
        print(f"  {change.kind.value} {change.domain:<9} {_describe(change)}", file=out)
    if not entry["checked"]:
        print("  = nothing checked: every declared domain was skipped, or --only left none", file=out)
    elif not shown:
        print("  = nothing to change", file=out)


def _describe(change) -> str:
    kind = etabli_module.Kind
    if change.domain == "labels" and change.kind is kind.CREATE:
        return f"{change.name}  #{change.after['color']}  {change.after['description']}"
    if change.domain == "labels" and change.kind in (kind.RENAME, kind.UPDATE):
        renamed = change.before["name"] != change.after["name"]
        head = f"{change.name} -> {change.after['name']}" if renamed else change.name
        fields = [f"{key} {change.before[key]!r} -> {change.after[key]!r}"
                  for key in ("color", "description") if change.before[key] != change.after[key]]
        return "  ".join(part for part in (head, " ; ".join(fields), change.note) if part)
    if change.domain == "settings" and change.kind is kind.UPDATE:
        return " ; ".join(f"{key} {change.before.get(key)!r} -> {value!r}"
                          for key, value in change.after.items())
    if change.domain == "security" and change.kind is kind.UPDATE:
        return f"{change.name}  {change.before!r} -> {change.after!r}"
    if change.domain == "rulesets" and change.kind is kind.CREATE:
        rules = ", ".join(rule.get("type", "?") for rule in change.after["rules"])
        return (f"{change.name}  enforcement {change.after['enforcement']}  rules {rules}  "
                f"bypass {_bypass_text(change.after)}")
    if change.domain == "rulesets" and change.kind is kind.UPDATE:
        return f"{change.name}  {change.note}  bypass after {_bypass_text(change.after)}"
    if change.domain == "project" and change.kind is kind.UPDATE:
        return " ; ".join(_setting_text(key, change.before.get(key), value)
                          for key, value in change.after.items())
    if change.domain == "fields" and change.kind is kind.CREATE:
        options = ", ".join(option["name"] for option in change.after["options"])
        return f"{change.name}  {change.after['type']}" + (f"  {options}" if options else "")
    if change.domain == "fields" and change.kind is kind.UPDATE:
        changes = _option_changes(change.before["options"], change.after["options"])
        return f"{change.name}  " + " ; ".join(changes)
    if change.domain == "views" and change.kind is kind.CREATE:
        return f"{change.name}  {change.after['layout']}  {change.after.get('filter', '')}".rstrip()
    return f"{change.name}  {change.note}".rstrip()


def _option_changes(before: list[dict], after: list[dict]) -> list[str]:
    present = {option["name"].lower(): option for option in before}
    wanted = {option["name"].lower() for option in after}
    changes = [f"- {option['name']}" for option in before if option["name"].lower() not in wanted]
    for option in after:
        have = present.get(option["name"].lower())
        if have is None:
            changes.append(f"+ {option['name']}")
            continue
        if have["name"] != option["name"]:
            changes.append(f"{have['name']} -> {option['name']}")
        changes += [f"{option['name']} {key} {have[key]} -> {option[key]}"
                    for key in ("color", "description") if have[key] != option[key]]
    if not changes:
        changes.append("order " + ", ".join(option["name"] for option in after))
    return changes


def _setting_text(key: str, before, after) -> str:
    if key == "readme":
        return f"readme {len((before or '').splitlines())} -> {len((after or '').splitlines())} lines"
    return f"{key} {before!r} -> {after!r}"


def _bypass_text(ruleset) -> str:
    actors = [f"{actor.get('actor_type')} {actor.get('actor_id')} {actor.get('bypass_mode', 'always')}"
              for actor in ruleset.get("bypass_actors") or ()]
    return ", ".join(actors) or "none"


# -- wiring -----------------------------------------------------------------

def _build(args: argparse.Namespace) -> tuple[Engine, Journal]:
    configuration = _load_or_die(args)
    write = bool(getattr(args, "write", False))
    journal = Journal(configuration.journal_path, verbose=args.verbose)
    if not write:
        journal.emit("dry_run", detail="real reads, no action: add --write to act")
    agent = ClaudeAgent(model=configuration.model, budget_usd=configuration.budget_per_run_usd,
                        dry_run=not write, agent=configuration.agent)
    engine = Engine(configuration, GhForge(), GitWorkspace(), agent,
                    Store(configuration.state_dir), journal, dry_run=not write,
                    regenerator=ShellRegenerator())
    return engine, journal


def _probe_commit_msg_hook() -> tuple[bool, str]:
    """Run the active hook on a trap message, and report what is left of it."""
    try:
        directory = subprocess.run(["git", "config", "--get", "core.hooksPath"],
                                   capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception as failure:
        return False, f"git unreachable: {failure}"
    if not directory:
        return False, "no core.hooksPath: run forgeron hook --install <directory>"

    hook = os.path.join(os.path.expanduser(directory), "commit-msg")
    if not os.access(hook, os.X_OK):
        return False, f"{hook} missing or not executable"

    import tempfile
    piege = "feat: probe\n\nBody.\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
    with tempfile.NamedTemporaryFile("w", suffix=".msg", delete=False, encoding="utf-8") as handle:
        handle.write(piege)
        path = handle.name
    try:
        subprocess.run([hook, path], capture_output=True, text=True, timeout=10)
        with open(path, encoding="utf-8") as handle:
            left = handle.read()
    finally:
        os.remove(path)

    if attribution.offending_lines(left):
        return False, f"{hook} let the line through"
    if "Body." not in left:
        return False, f"{hook} ate the message body"
    return True, f"{hook} removes the line and keeps the body"


def _load_or_die(args: argparse.Namespace):
    try:
        return config_module.load(args.config)
    except FileNotFoundError:
        print(f"{args.config} missing. Run: forgeron config --init", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def _which(binary: str) -> str:
    import shutil
    return shutil.which(binary) or ""
