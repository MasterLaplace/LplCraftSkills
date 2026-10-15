from __future__ import annotations

import json
import os
import tempfile
import unittest

from forgeron import cli
from forgeron import config as config_module
from forgeron.claude_agent import ClaudeAgent
from forgeron.config import Config


def argv_of(**kwargs: object) -> list[str]:
    agent = ClaudeAgent(dry_run=True, **kwargs)  # type: ignore[arg-type]
    result = agent.run(cwd=".", session_id="s", prompt="p", schema={}, resume=False, read_only=True)
    return list(result.verdict["argv"])


class TheAgentFlag(unittest.TestCase):
    def test_the_configured_agent_is_passed_to_claude(self) -> None:
        argv = argv_of(agent="artisan")
        self.assertIn("--agent", argv)
        self.assertEqual(argv[argv.index("--agent") + 1], "artisan")

    def test_the_agent_comes_before_the_variadic_tools(self) -> None:
        argv = argv_of(agent="artisan")
        self.assertLess(argv.index("--agent"), argv.index("--tools"))

    def test_an_empty_agent_means_no_flag_at_all(self) -> None:
        self.assertNotIn("--agent", argv_of(agent=""))

    def test_the_contract_still_travels_beside_the_agent(self) -> None:
        argv = argv_of(agent="artisan", contract="RAILS")
        self.assertEqual(argv[argv.index("--append-system-prompt") + 1], "RAILS")


class TheDefault(unittest.TestCase):
    def test_the_default_agent_is_artisan(self) -> None:
        self.assertEqual(Config().agent, "artisan")

    def test_the_agent_is_printed_with_the_rest_of_the_configuration(self) -> None:
        self.assertEqual(Config().to_dict()["agent"], "artisan")

    def test_the_agent_can_be_switched_off_in_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            path = os.path.join(home, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"agent": ""}, handle)
            self.assertEqual(config_module.load(path).agent, "")


class TheDoctorCheck(unittest.TestCase):
    def test_a_missing_agent_is_a_failure_that_says_how_to_install_it(self) -> None:
        with tempfile.TemporaryDirectory() as agents:
            ok, detail = cli._agent_installed("artisan", agents)
        self.assertFalse(ok)
        self.assertIn("install.sh", detail)
        self.assertIn("artisan.md", detail)

    def test_an_installed_agent_passes(self) -> None:
        with tempfile.TemporaryDirectory() as agents:
            with open(os.path.join(agents, "artisan.md"), "w", encoding="utf-8") as handle:
                handle.write("---\nname: artisan\n---\n")
            ok, _ = cli._agent_installed("artisan", agents)
        self.assertTrue(ok)

    def test_no_agent_configured_is_said_rather_than_checked(self) -> None:
        with tempfile.TemporaryDirectory() as agents:
            ok, detail = cli._agent_installed("", agents)
        self.assertTrue(ok)
        self.assertIn("no agent", detail)


FAKE_CLAUDE = """#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
flag = "--resume" if "--resume" in argv else "--session-id"
session = argv[argv.index(flag) + 1]
skill = os.environ.get("FAKE_SKILL")
if skill:
    folder = os.path.join(os.environ["FAKE_PROJECTS"], "-worktrees-o-r-42")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, session + ".jsonl"), "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "assistant", "uuid": "u-" + skill, "message": {"content": [
            {"type": "tool_use", "id": "toolu-" + skill, "name": "Skill", "input": {"skill": skill}}]}}) + "\\n")
print(json.dumps({"structured_output": {"verdict": "ready_for_review"}, "total_cost_usd": 0.1,
                  "session_id": session, "num_turns": 3}))
"""


class TheSkillsOfARun(unittest.TestCase):
    def setUp(self) -> None:
        self.projects = tempfile.mkdtemp()
        self.executable = os.path.join(tempfile.mkdtemp(), "claude")
        with open(self.executable, "w", encoding="utf-8") as handle:
            handle.write(FAKE_CLAUDE)
        os.chmod(self.executable, 0o755)
        self.addCleanup(os.environ.pop, "FAKE_SKILL", None)
        self.addCleanup(os.environ.pop, "FAKE_PROJECTS", None)
        os.environ["FAKE_PROJECTS"] = self.projects

    def run_once(self, skill: str, resume: bool):
        os.environ["FAKE_SKILL"] = skill
        agent = ClaudeAgent(executable=self.executable, transcripts_dir=self.projects)
        return agent.run(cwd=".", session_id="s-1", prompt="p", schema={}, resume=resume, read_only=False)

    def test_the_skills_a_run_loaded_come_back_with_its_result(self) -> None:
        result = self.run_once("cycle-de-dev", resume=False)
        self.assertTrue(result.ok)
        self.assertEqual(result.skills, ("cycle-de-dev",))
        self.assertEqual(result.compactions, 0)

    def test_a_resumed_run_brings_back_only_its_own_skills(self) -> None:
        self.run_once("cadrer-et-planifier", resume=False)
        result = self.run_once("tests-first", resume=True)
        self.assertEqual(result.skills, ("tests-first",))

    def test_a_run_whose_transcript_is_not_found_says_its_skills_were_not_read(self) -> None:
        result = self.run_once("", resume=False)
        self.assertTrue(result.ok)
        self.assertIsNone(result.skills)
        self.assertIsNone(result.compactions)


if __name__ == "__main__":
    unittest.main()
