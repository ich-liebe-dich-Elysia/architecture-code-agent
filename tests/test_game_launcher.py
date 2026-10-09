"""The launcher keeps a stable local browser origin when a port is available."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.game_launcher import choose_game_port


class GameLauncherPortTests(unittest.TestCase):
    def probe(self, port: int, occupied: bool = False):
        context = MagicMock()
        probe = context.__enter__.return_value
        if occupied:
            probe.bind.side_effect = OSError("Address already in use")
        probe.getsockname.return_value = ("127.0.0.1", port)
        return context, probe

    @patch("agent.game_launcher.socket.socket")
    def test_prefers_standalone_port_for_resume(self, socket_factory):
        context, probe = self.probe(3000)
        socket_factory.return_value = context
        self.assertEqual(choose_game_port(Path("demo-game")), 3000)
        probe.bind.assert_called_once_with(("127.0.0.1", 3000))
        probe.setsockopt.assert_not_called()
        self.assertEqual(socket_factory.call_count, 1)

    @patch("agent.game_launcher.socket.socket")
    def test_occupied_default_uses_repeatable_project_port(self, socket_factory):
        ports = []
        for _ in range(2):
            occupied_context, occupied = self.probe(3000, occupied=True)
            fallback_context, fallback = self.probe(35001)
            socket_factory.side_effect = [occupied_context, fallback_context]
            self.assertEqual(choose_game_port(Path("demo-game")), 35001)
            occupied.bind.assert_called_once_with(("127.0.0.1", 3000))
            host, port = fallback.bind.call_args.args[0]
            self.assertEqual(host, "127.0.0.1")
            self.assertGreaterEqual(port, 35000)
            self.assertLessEqual(port, 55000)
            fallback.setsockopt.assert_not_called()
            ports.append(port)
        self.assertEqual(ports[0], ports[1])

    @patch("agent.game_launcher.socket.socket")
    def test_only_uses_ephemeral_port_when_both_candidates_occupied(self, socket_factory):
        first_context, first = self.probe(3000, occupied=True)
        second_context, second = self.probe(35001, occupied=True)
        free_context, free = self.probe(60123)
        socket_factory.side_effect = [first_context, second_context, free_context]
        self.assertEqual(choose_game_port(Path("demo-game")), 60123)
        first.bind.assert_called_once_with(("127.0.0.1", 3000))
        self.assertNotEqual(second.bind.call_args.args[0][1], 0)
        free.bind.assert_called_once_with(("127.0.0.1", 0))
        self.assertEqual(socket_factory.call_count, 3)


if __name__ == "__main__":
    unittest.main()
