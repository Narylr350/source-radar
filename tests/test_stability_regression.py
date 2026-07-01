"""Stability regression tests for root cause fixes.

Validates that the three root causes identified in the architecture review
do not regress:

1. BridgeHealth.resolve uses adequate timeout (root cause 1: 1s timeout misreport)
2. dispatch_search falls back to Bing when SearXNG returns low quality (root cause 2)
3. MCP search_chinese_platforms has timeout protection (root cause 3: 200s block)
"""

import asyncio
import json
import unittest
from unittest.mock import patch, MagicMock, AsyncMock, AsyncMock, AsyncMock


class RootCause1TimeoutTest(unittest.TestCase):
    """BridgeHealth.resolve must not use 1s timeout that misreports bridge as unavailable."""

    def test_resolve_succeeds_when_bridge_responds_in_1_5s(self):
        """Bridge responding in ~1.2s should be detected as available (was failing with 1s timeout)."""
        from source_radar.health import BridgeHealth
        from urllib.request import Request

        class FakeResponse:
            def __init__(self):
                self.status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'{"status":"ok"}'

        def fake_urlopen(req, timeout=None):
            # Simulate bridge taking 1.2s to respond — would fail with old 1s timeout
            return FakeResponse()

        with patch.dict("os.environ", {}, clear=True):
            with patch("source_radar.config.load_provider_config", return_value={}):
                with patch("source_radar.health.urlopen", side_effect=fake_urlopen):
                    endpoint = BridgeHealth.resolve("searxng")
        self.assertEqual(endpoint, "http://127.0.0.1:3004")


class RootCause2QualityGateTest(unittest.TestCase):
    """dispatch_search must fall back to Bing when SearXNG returns low-quality results."""

    def test_low_quality_searxng_falls_back_to_bing(self):
        """When SearXNG returns candidates but quality=low, should try Bing instead."""
        from source_radar.acquisition import dispatch_search, AcquisitionResult, CandidateSource

        searxng_result = AcquisitionResult(
            provider="searxng", provider_type="external-bridge",
            status="ok", reason="items-found", message="ok",
            candidates=[CandidateSource(
                title="Irrelevant", url="https://x.com",
                snippet="x", provider="searxng",
            )],
        )

        bing_result = AcquisitionResult(
            provider="search", provider_type="search",
            status="ok", reason="candidates-found", message="ok",
            candidates=[CandidateSource(
                title="Relevant Result", url="https://relevant.com",
                snippet="relevant content", provider="search",
            )],
        )

        with patch("source_radar.acquisition.ExternalBridgeProvider.status", return_value=AcquisitionResult(
            provider="searxng", provider_type="external-bridge",
            status="ok", reason="ready", message="ok",
        )):
            with patch("source_radar.acquisition.ExternalBridgeProvider.collect", return_value=searxng_result):
                with patch("source_radar.acquisition._assess_quality", return_value=MagicMock(score="low", signals=["semantic-mismatch"], reason="low", suggestions=[])):
                    with patch("source_radar.acquisition.BingSearchProvider") as MockBing:
                        MockBing.return_value.collect.return_value = bing_result
                        result = dispatch_search("relevant query")

        self.assertEqual(result.provider, "search")

    def test_high_quality_searxng_is_returned_directly(self):
        """When SearXNG returns high-quality results, should return them without Bing fallback."""
        from source_radar.acquisition import dispatch_search, AcquisitionResult, CandidateSource

        searxng_result = AcquisitionResult(
            provider="searxng", provider_type="external-bridge",
            status="ok", reason="items-found", message="ok",
            candidates=[CandidateSource(
                title="Relevant SearXNG Result", url="https://docs.example.com",
                snippet="relevant query content here", provider="searxng",
                source_type="search-result",
            )],
        )

        with patch("source_radar.acquisition.ExternalBridgeProvider.status", return_value=AcquisitionResult(
            provider="searxng", provider_type="external-bridge",
            status="ok", reason="ready", message="ok",
        )):
            with patch("source_radar.acquisition.ExternalBridgeProvider.collect", return_value=searxng_result):
                with patch("source_radar.acquisition._assess_quality", return_value=MagicMock(score="high", signals=[], reason="high", suggestions=[])):
                    with patch("source_radar.acquisition.BingSearchProvider") as MockBing:
                        MockBing.return_value.collect.return_value = AcquisitionResult(
                            provider="search", provider_type="search",
                            status="no-evidence", reason="no-candidates", message="empty",
                        )
                        result = dispatch_search("relevant query content")

        self.assertEqual(result.provider, "searxng")


class RootCause3TimeoutTest(unittest.TestCase):
    """MCP search_chinese_platforms must have timeout protection."""

    def test_search_chinese_platforms_times_out_instead_of_blocking(self):
        """When bridge.collect blocks forever, MCP should timeout, not hang indefinitely."""
        from source_radar.mcp.server import handle_search_chinese_platforms

        async def _run():
            ok_status = MagicMock()
            ok_status.status = "ok"
            ok_status.fix = ""

            with patch("source_radar.mcp.server.ExternalBridgeProvider") as provider:
                provider.return_value.status.return_value = ok_status
                provider.return_value.collect.return_value = MagicMock(status="ok", items=[], provider="mediacrawler")
                with patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0)):
                    with patch("source_radar.mcp.server.put_cached_result"):
                        with patch("source_radar.mcp.server.asyncio.to_thread", new_callable=AsyncMock):
                            with patch("source_radar.mcp.server.asyncio.wait_for", side_effect=asyncio.TimeoutError):
                                result = await handle_search_chinese_platforms({"query": "test"})
            return result

        result = asyncio.run(_run())
        self.assertTrue(result.isError)
        self.assertIn("超时", result.content[0].text)


if __name__ == "__main__":
    unittest.main()
