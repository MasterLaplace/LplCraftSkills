from __future__ import annotations

import unittest

from forgeron.board import GhBoard
from forgeron.claude_agent import ClaudeAgent
from forgeron.gh_forge import GhForge
from forgeron.git_workspace import GitWorkspace
from forgeron.ports import Agent, Board, Forge, Regenerator, Workspace
from forgeron.regenerator import ShellRegenerator
from tests.fakes import FakeAgent, FakeBoard, FakeForge, FakeRegenerator, FakeWorkspace


class EverySeam(unittest.TestCase):
    def test_the_adapter_and_its_fake_satisfy_the_same_port(self) -> None:
        seams = [
            (Forge, GhForge(), FakeForge([])),
            (Workspace, GitWorkspace(), FakeWorkspace()),
            (Agent, ClaudeAgent(), FakeAgent()),
            (Regenerator, ShellRegenerator(), FakeRegenerator()),
            (Board, GhBoard("MasterLaplace/Laplace"), FakeBoard()),
        ]
        for port, adapter, fake in seams:
            with self.subTest(port=port.__name__):
                self.assertIsInstance(adapter, port)
                self.assertIsInstance(fake, port)


if __name__ == "__main__":
    unittest.main()
