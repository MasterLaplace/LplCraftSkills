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
        self.assertIn("sans agent", detail)


if __name__ == "__main__":
    unittest.main()
