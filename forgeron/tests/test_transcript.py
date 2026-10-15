from __future__ import annotations

import json
import os
import tempfile
import unittest

from forgeron.transcript import read_snapshot

SESSION = "3f1c2b9e-0000-4000-8000-000000000001"


def skill_call(uuid: str, tool_use_id: str, skill: str, timestamp: str = "") -> dict:
    return {"type": "assistant", "uuid": uuid, "timestamp": timestamp, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tool_use_id, "name": "Skill", "input": {"skill": skill}}]}}


def other_tool_call(uuid: str, tool_use_id: str) -> dict:
    return {"type": "assistant", "uuid": uuid, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tool_use_id, "name": "Read", "input": {"file_path": "README.md"}}]}}


def compaction(uuid: str) -> dict:
    return {"type": "user", "uuid": uuid, "isCompactSummary": True,
            "message": {"role": "user", "content": "This session is being continued..."}}


class Projects:
    def __init__(self) -> None:
        self.root = tempfile.mkdtemp()

    def write(self, folder: str, session: str, entries: list[dict]) -> None:
        self.write_file(os.path.join(folder, f"{session}.jsonl"), entries)

    def write_subagent(self, folder: str, session: str, agent: str, entries: list[dict]) -> None:
        self.write_file(os.path.join(folder, session, "subagents", f"agent-{agent}.jsonl"), entries)

    def write_file(self, relative_path: str, entries: list[dict]) -> None:
        path = os.path.join(self.root, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry) + "\n")


class ReadingTheTranscriptOfARun(unittest.TestCase):
    def test_the_skills_are_read_in_order_whatever_the_project_folder(self) -> None:
        projects = Projects()
        projects.write("-home-forgeron-worktrees-o-r-42", SESSION, [
            skill_call("a1", "toolu_1", "cycle-de-dev"),
            other_tool_call("a2", "toolu_2"),
            skill_call("a3", "toolu_3", "tests-first"),
        ])
        snapshot = read_snapshot(projects.root, SESSION)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.skills_since(None), ("cycle-de-dev", "tests-first"))

    def test_a_line_replayed_after_a_compaction_counts_once_and_the_compaction_counts(self) -> None:
        projects = Projects()
        projects.write("p", SESSION, [
            skill_call("a1", "toolu_1", "cycle-de-dev"),
            compaction("c1"),
            skill_call("a1", "toolu_1", "cycle-de-dev"),
            compaction("c1"),
        ])
        snapshot = read_snapshot(projects.root, SESSION)
        self.assertEqual(snapshot.skills_since(None), ("cycle-de-dev",))
        self.assertEqual(snapshot.compactions_since(None), 1)

    def test_only_what_a_resumed_run_added_belongs_to_it(self) -> None:
        projects = Projects()
        projects.write("p", SESSION, [skill_call("a1", "toolu_1", "cadrer-et-planifier"), compaction("c0")])
        before = read_snapshot(projects.root, SESSION)
        projects.write("p", SESSION, [compaction("c1"), skill_call("a2", "toolu_2", "tests-first")])
        after = read_snapshot(projects.root, SESSION)
        self.assertEqual(after.skills_since(before), ("tests-first",))
        self.assertEqual(after.compactions_since(before), 1)

    def test_the_skills_of_subagents_are_read_apart_and_in_time_order(self) -> None:
        projects = Projects()
        projects.write("p", SESSION, [skill_call("a1", "toolu_1", "cycle-de-dev")])
        projects.write_subagent("p", SESSION, "b", [
            skill_call("s2", "toolu_s2", "tracer-le-travail", "2026-10-15T10:05:00Z")])
        projects.write_subagent("p", SESSION, "a", [
            skill_call("s1", "toolu_s1", "relire-une-pr", "2026-10-15T10:01:00Z")])
        snapshot = read_snapshot(projects.root, SESSION)
        self.assertEqual(snapshot.skills_since(None), ("cycle-de-dev",))
        self.assertEqual(snapshot.subagent_skills_since(None), ("relire-une-pr", "tracer-le-travail"))

    def test_only_the_subagents_a_resumed_run_launched_belong_to_it(self) -> None:
        projects = Projects()
        projects.write("p", SESSION, [skill_call("a1", "toolu_1", "cycle-de-dev")])
        projects.write_subagent("p", SESSION, "a", [skill_call("s1", "toolu_s1", "relire-une-pr")])
        before = read_snapshot(projects.root, SESSION)
        projects.write_subagent("p", SESSION, "b", [skill_call("s2", "toolu_s2", "relire-une-pr")])
        after = read_snapshot(projects.root, SESSION)
        self.assertEqual(after.subagent_skills_since(before), ("relire-une-pr",))

    def test_a_copy_of_a_call_counts_once_and_a_malformed_entry_is_skipped(self) -> None:
        projects = Projects()
        copy = skill_call("", "toolu_1", "cycle-de-dev")
        copy["type"] = "api-request-blob"
        malformed = skill_call("a2", "toolu_2", "tests-first")
        malformed["message"]["content"][0]["input"] = None
        projects.write("p", SESSION, [skill_call("a1", "toolu_1", "cycle-de-dev"), copy, malformed,
                                      {"type": "assistant", "uuid": "a3", "message": "not a dict"}])
        self.assertEqual(read_snapshot(projects.root, SESSION).skills_since(None), ("cycle-de-dev", ""))

    def test_a_missing_transcript_is_not_read_rather_than_empty(self) -> None:
        self.assertIsNone(read_snapshot(Projects().root, SESSION))

    def test_two_transcripts_for_one_session_are_not_guessed_between(self) -> None:
        projects = Projects()
        projects.write("one", SESSION, [skill_call("a1", "toolu_1", "cycle-de-dev")])
        projects.write("two", SESSION, [skill_call("b1", "toolu_9", "tests-first")])
        self.assertIsNone(read_snapshot(projects.root, SESSION))


if __name__ == "__main__":
    unittest.main()
