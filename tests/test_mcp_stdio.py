import asyncio
import os
import sys
import unittest

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class McpStdioSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_source_status_returns_over_stdio(self):
        env = os.environ.copy()
        env["SOURCE_RADAR_SEARXNG_AUTOSTART"] = "0"
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "source_radar", "mcp"],
            cwd=os.getcwd(),
            env=env,
        )

        async def call_source_status():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("source_status", {})
                    text = result.content[0].text
                    self.assertIn("backend_registry:", text)

        await asyncio.wait_for(call_source_status(), timeout=20)


if __name__ == "__main__":
    unittest.main()
