from __future__ import annotations

import dataclasses
import glob
import json
import os
from typing import Iterator, NamedTuple


class SkillCall(NamedTuple):
    tool_use_id: str
    skill: str
    timestamp: str


@dataclasses.dataclass(frozen=True, slots=True)
class TranscriptSnapshot:
    skill_calls: tuple[SkillCall, ...]
    subagent_skill_calls: tuple[SkillCall, ...]
    compaction_ids: frozenset[str]

    def skills_since(self, earlier: "TranscriptSnapshot | None") -> tuple[str, ...]:
        return _skills_added(self.skill_calls, earlier.skill_calls if earlier else ())

    def subagent_skills_since(self, earlier: "TranscriptSnapshot | None") -> tuple[str, ...]:
        return _skills_added(self.subagent_skill_calls, earlier.subagent_skill_calls if earlier else ())

    def compactions_since(self, earlier: "TranscriptSnapshot | None") -> int:
        return len(self.compaction_ids - (earlier.compaction_ids if earlier else frozenset()))


def read_snapshot(projects_dir: str, session_id: str) -> TranscriptSnapshot | None:
    candidates = glob.glob(os.path.join(glob.escape(projects_dir), "*", f"{glob.escape(session_id)}.jsonl"))
    if len(candidates) != 1:
        return None
    transcript = candidates[0]
    skill_calls, compaction_ids = _read(transcript)
    subagent_files = glob.glob(os.path.join(glob.escape(transcript[:-len(".jsonl")]), "subagents", "agent-*.jsonl"))
    subagent_skill_calls = sorted((call for path in subagent_files for call in _read(path)[0]),
                                  key=lambda call: call.timestamp)
    return TranscriptSnapshot(skill_calls, tuple(subagent_skill_calls), compaction_ids)


def _skills_added(calls: tuple[SkillCall, ...], earlier_calls: tuple[SkillCall, ...]) -> tuple[str, ...]:
    earlier_ids = {call.tool_use_id for call in earlier_calls}
    return tuple(call.skill for call in calls if call.tool_use_id not in earlier_ids)


def _read(path: str) -> tuple[tuple[SkillCall, ...], frozenset[str]]:
    calls_by_id: dict[str, SkillCall] = {}
    compaction_ids: set[str] = set()
    for entry in _entries(path):
        if entry.get("isCompactSummary"):
            compaction_ids.add(entry.get("uuid", ""))
            continue
        for call in _skill_calls(entry):
            calls_by_id.setdefault(call.tool_use_id, call)
    return tuple(calls_by_id.values()), frozenset(compaction_ids)


def _entries(path: str) -> Iterator[dict]:
    with open(path, encoding="utf-8", errors="replace") as transcript:
        for line in transcript:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                yield entry


def _skill_calls(entry: dict) -> list[SkillCall]:
    message = entry.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [SkillCall(block.get("id", ""), _skill_name(block), entry.get("timestamp", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill"]


def _skill_name(block: dict) -> str:
    tool_input = block.get("input")
    return tool_input.get("skill", "") if isinstance(tool_input, dict) else ""
