"""Regression tests that MCP no longer owns backend idle-stop state."""

import unittest


class McpLifecycleOwnershipTest(unittest.TestCase):
    def test_mcp_does_not_expose_private_idle_watchdog_state_machine(self):
        from source_radar.mcp import server

        private_state = [
            "_touch_activity",
            "_idle_watchdog",
            "_stop_searxng",
            "_last_activity_time",
            "_searxng_autostart_just_succeeded",
            "_searxng_last_autostart_result",
            "_searxng_last_autostart_error",
            "_searxng_last_autostart_time",
        ]

        for name in private_state:
            self.assertFalse(hasattr(server, name), name)


if __name__ == "__main__":
    unittest.main()
