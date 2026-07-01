"""Test idle watchdog that stops SearXNG after inactivity."""
import unittest
import asyncio
import time
from unittest.mock import patch, MagicMock


class IdleWatchdogTest(unittest.TestCase):
    """MCP server should stop SearXNG after N minutes of no tool calls."""

    def test_touch_activity_updates_timestamp(self):
        """_touch_activity should update the last activity time."""
        from source_radar.mcp import server
        old = server._last_activity_time
        server._touch_activity()
        self.assertGreater(server._last_activity_time, old or 0)

    def test_watchdog_stops_searxng_when_idle(self):
        """When idle longer than threshold, watchdog should stop SearXNG."""
        from source_radar.mcp.server import _idle_watchdog

        stopped = {"called": False}
        def fake_stop():
            stopped["called"] = True

        async def run():
            with patch("source_radar.mcp.server._searxng_autostart_just_succeeded", True):
                with patch("source_radar.mcp.server._idle_timeout_seconds", 0.1):
                    with patch("source_radar.mcp.server._IDLE_CHECK_INTERVAL", 0.1):
                        with patch("source_radar.mcp.server._stop_searxng", side_effect=fake_stop):
                            import source_radar.mcp.server as s
                            s._last_activity_time = time.time() - 1.0
                            task = asyncio.create_task(_idle_watchdog())
                            await asyncio.sleep(0.5)
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass

        asyncio.run(run())
        self.assertTrue(stopped["called"], "Watchdog should have stopped SearXNG when idle")

    def test_watchdog_does_not_stop_when_active(self):
        """When recently active, watchdog should not stop SearXNG."""
        from source_radar.mcp.server import _idle_watchdog

        stopped = {"called": False}
        def fake_stop():
            stopped["called"] = True

        async def run():
            with patch("source_radar.mcp.server._searxng_autostart_just_succeeded", True):
                with patch("source_radar.mcp.server._idle_timeout_seconds", 0.5):
                    with patch("source_radar.mcp.server._IDLE_CHECK_INTERVAL", 0.1):
                        with patch("source_radar.mcp.server._stop_searxng", side_effect=fake_stop):
                            import source_radar.mcp.server as s
                            s._last_activity_time = time.time()  # just now
                            task = asyncio.create_task(_idle_watchdog())
                            await asyncio.sleep(0.3)
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass

        asyncio.run(run())
        self.assertFalse(stopped["called"], "Watchdog should NOT stop SearXNG when recently active")

    def test_watchdog_does_not_stop_user_started_searxng(self):
        """If SearXNG was started by user (not autostart), watchdog should not stop it."""
        from source_radar.mcp.server import _idle_watchdog

        stopped = {"called": False}

        async def run():
            with patch("source_radar.mcp.server._searxng_autostart_just_succeeded", False):
                with patch("source_radar.mcp.server._idle_timeout_seconds", 0.1):
                    with patch("source_radar.mcp.server._IDLE_CHECK_INTERVAL", 0.1):
                        with patch("source_radar.mcp.server._stop_searxng", side_effect=lambda: stopped.__setitem__("called", True)):
                            import source_radar.mcp.server as s
                            s._last_activity_time = time.time() - 10.0
                            task = asyncio.create_task(_idle_watchdog())
                            await asyncio.sleep(0.5)
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass

        asyncio.run(run())
        self.assertFalse(stopped["called"], "Should not stop user-started SearXNG")


if __name__ == "__main__":
    unittest.main()
