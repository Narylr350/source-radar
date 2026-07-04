"""Test SearXNG background prewarm on MCP server startup."""
import unittest
import asyncio
from unittest.mock import patch


class PrewarmTest(unittest.TestCase):
    """MCP server should prewarm SearXNG in background without blocking startup."""

    def test_prewarm_function_exists(self):
        from source_radar.mcp import server
        self.assertTrue(hasattr(server, "_prewarm_searxng"))

    def test_prewarm_calls_ensure_searxng(self):
        """_prewarm_searxng should delegate to lifecycle-backed ensure off the event loop."""
        from source_radar.mcp.server import _prewarm_searxng

        called = {"n": 0}
        def fake_ensure():
            called["n"] += 1
            return True, ""

        async def run():
            with patch("source_radar.mcp.server._ensure_searxng_for_search", side_effect=fake_ensure):
                await _prewarm_searxng()

        asyncio.run(run())
        self.assertEqual(called["n"], 1)

    def test_prewarm_swallows_errors(self):
        """Prewarm failure must not propagate."""
        from source_radar.mcp.server import _prewarm_searxng

        async def run():
            with patch("source_radar.mcp.server._ensure_searxng_for_search", side_effect=RuntimeError("boom")):
                await _prewarm_searxng()

        asyncio.run(run())  # if it raises, test fails


if __name__ == "__main__":
    unittest.main()
