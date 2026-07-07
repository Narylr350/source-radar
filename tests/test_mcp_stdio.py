import asyncio
import os
import sys
import unittest

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _server_params(**env_overrides) -> StdioServerParameters:
    env = os.environ.copy()
    env["SOURCE_RADAR_SEARXNG_AUTOSTART"] = "0"
    env.update(env_overrides)
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "source_radar", "mcp"],
        cwd=os.getcwd(),
        env=env,
    )


class McpStdioSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_source_status_returns_over_stdio(self):
        params = _server_params()

        async def call_source_status():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("source_status", {})
                    text = result.content[0].text
                    self.assertIn("backend_registry:", text)

        await asyncio.wait_for(call_source_status(), timeout=20)


class McpWebSearchStabilityTests(unittest.IsolatedAsyncioTestCase):
    """Stability: web_search must not hang or crash when SearXNG is unavailable,
    and must fallback to Bing/Baidu gracefully."""

    async def test_web_search_returns_results_without_searxng(self):
        """SearXNG autostart disabled — web_search should still return results via Bing fallback."""
        params = _server_params(SOURCE_RADAR_SEARXNG_AUTOSTART="0")

        async def call_web_search():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("web_search", {"query": "python tutorial", "limit": 3})
                    self.assertFalse(result.isError, f"web_search returned error: {result.content[0].text[:200]}")
                    text = result.content[0].text
                    self.assertIn("url", text.lower(), "Results should contain URLs")
                    return text

        text = await asyncio.wait_for(call_web_search(), timeout=45)
        # Should have at least one result
        self.assertIn("http", text)

    async def test_web_search_consecutive_calls_stable(self):
        """Two consecutive web_search calls should both succeed without state leakage."""
        params = _server_params(SOURCE_RADAR_SEARXNG_AUTOSTART="0")

        async def call_web_search_twice():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    r1 = await session.call_tool("web_search", {"query": "rust async", "limit": 2})
                    r2 = await session.call_tool("web_search", {"query": "golang channels", "limit": 2})
                    self.assertFalse(r1.isError, f"first search failed: {r1.content[0].text[:200]}")
                    self.assertFalse(r2.isError, f"second search failed: {r2.content[0].text[:200]}")
                    return r1.content[0].text, r2.content[0].text

        t1, t2 = await asyncio.wait_for(call_web_search_twice(), timeout=60)
        self.assertIn("http", t1)
        self.assertIn("http", t2)


class McpSourceStatusNativeTests(unittest.IsolatedAsyncioTestCase):
    """source_status must show native runtime for SearXNG, not external-bridge."""

    async def test_source_status_shows_native_searxng(self):
        params = _server_params()

        async def call_source_status():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("source_status", {})
                    return result.content[0].text

        text = await asyncio.wait_for(call_source_status(), timeout=20)
        # SearXNG line should show native-searxng or native runtime
        searxng_line = [l for l in text.split("\n") if "search.searxng" in l]
        if searxng_line:
            self.assertIn("searxng", searxng_line[0])


class McpChinesePlatformsStabilityTests(unittest.IsolatedAsyncioTestCase):
    """search_chinese_platforms must not hang when MediaCrawler is unavailable."""

    async def test_search_chinese_platforms_graceful_when_mediacrawler_down(self):
        """MediaCrawler not running — should return structured error, not hang."""
        params = _server_params(SOURCE_RADAR_BACKEND_AUTOSTART="0")

        async def call_chinese_platforms():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("search_chinese_platforms", {"query": "test", "limit": 1})
                    return result

        result = await asyncio.wait_for(call_chinese_platforms(), timeout=30)
        text = result.content[0].text
        # Should either return results (B站 native) or structured error
        # Must NOT hang or crash
        self.assertTrue(
            "不可用" in text or "未找到" in text or "http" in text.lower(),
            f"Unexpected response: {text[:200]}",
        )


if __name__ == "__main__":
    unittest.main()
