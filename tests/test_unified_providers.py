"""Test that MCP server uses default_providers registry instead of ad-hoc instantiation."""
import unittest
from unittest.mock import patch, MagicMock


class UnifiedProviderRegistryTest(unittest.TestCase):
    """MCP server should use a shared provider registry, not ad-hoc new instances."""

    def test_mcp_server_has_provider_registry(self):
        """MCP server should have a module-level provider registry."""
        from source_radar.mcp import server
        self.assertTrue(hasattr(server, "_providers"))

    def test_mcp_does_not_instantiate_github_search_provider_directly(self):
        """handle_search_github should use registry, not GithubSearchProvider()."""
        from source_radar.mcp import server
        from source_radar.acquisition import GithubSearchProvider, default_providers
        server._providers = {p.provider: p for p in default_providers()}

        with patch("source_radar.mcp.server.GithubSearchProvider") as MockGithub:
            import asyncio
            async def run():
                return await server.handle_search_github({"query": "test", "limit": 1})
            with patch("source_radar.cache.get_cached_result", return_value=(None, 0)):
                with patch("source_radar.cache.put_cached_result"):
                    asyncio.run(run())
            MockGithub.assert_not_called()

    def test_mcp_does_not_instantiate_external_bridge_provider_directly(self):
        """handle_search_chinese_platforms should use registry, not ExternalBridgeProvider()."""
        from source_radar.mcp import server
        from source_radar.acquisition import default_providers
        server._providers = {p.provider: p for p in default_providers()}

        with patch("source_radar.mcp.server.ExternalBridgeProvider") as MockBridge:
            import asyncio
            ok_status = MagicMock()
            ok_status.status = "ok"
            ok_status.fix = ""
            with patch.object(server._providers.get("mediacrawler"), "status", return_value=ok_status):
                with patch.object(server._providers.get("mediacrawler"), "collect") as mock_collect:
                    mock_collect.return_value = MagicMock(status="error", items=[], candidates=[], message="test", warnings=[], reason="test")
                    async def run():
                        return await server.handle_search_chinese_platforms({"query": "test", "limit": 1})
                    with patch("source_radar.cache.get_cached_result", return_value=(None, 0)):
                        with patch("source_radar.cache.put_cached_result"):
                            asyncio.run(run())
            MockBridge.assert_not_called()


if __name__ == "__main__":
    unittest.main()
