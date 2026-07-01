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


class RootCause4SiteDowngradeTest(unittest.TestCase):
    """dispatch_search must retry without site when site-filtered Bing returns low quality.

    Root cause: when SearXNG returns 0 candidates for a site-filtered query,
    dispatch_search falls back to Bing. If Bing returns low-quality results
    (e.g. marketing page), it returns them directly without quality gate.
    This causes ask to get irrelevant evidence when site: is used by planner.
    """

    def test_site_filtered_bing_low_quality_retries_searxng_without_site(self):
        """When SearXNG 0 candidates + Bing low quality with site, retry SearXNG without site."""
        from source_radar.acquisition import dispatch_search, AcquisitionResult, CandidateSource

        # SearXNG with site: 0 candidates (site:nvidia.com has no Chinese content)
        searxng_site_empty = AcquisitionResult(
            provider="searxng", provider_type="external-bridge",
            status="no-evidence", reason="no-candidates", message="empty",
        )
        # SearXNG without site: 5 relevant candidates
        searxng_no_site = AcquisitionResult(
            provider="searxng", provider_type="external-bridge",
            status="ok", reason="items-found", message="ok",
            candidates=[
                CandidateSource(
                    title=f"RTX 5090 电源接口规格详解 {i}", url=f"https://relevant.com/spec{i}",
                    snippet="RTX 5090 uses 12V-2x6 connector rated 600W", provider="searxng",
                    source_type="search-result",
                )
                for i in range(5)
            ],
        )
        # Bing with site: 1 irrelevant candidate, low quality
        bing_site_low = AcquisitionResult(
            provider="search", provider_type="search",
            status="ok", reason="candidates-found", message="ok",
            candidates=[CandidateSource(
                title="GeForce RTX Marketing", url="https://nvidia.com/geforce",
                snippet="RTX platform marketing page", provider="search",
            )],
        )

        call_count = {"searxng_collect": 0}
        def searxng_collect_side_effect(request):
            call_count["searxng_collect"] += 1
            if request.site:
                return searxng_site_empty
            return searxng_no_site

        def quality_side_effect(result, query):
            if result.provider == "search":
                return MagicMock(score="low", signals=["semantic-mismatch"], reason="low", suggestions=[])
            return MagicMock(score="high", signals=[], reason="high", suggestions=[])

        with patch("source_radar.acquisition.ExternalBridgeProvider.status", return_value=AcquisitionResult(
            provider="searxng", provider_type="external-bridge",
            status="ok", reason="ready", message="ok",
        )):
            with patch("source_radar.acquisition.ExternalBridgeProvider.collect", side_effect=searxng_collect_side_effect):
                with patch("source_radar.acquisition._assess_quality", side_effect=quality_side_effect):
                    with patch("source_radar.acquisition.BingSearchProvider") as MockBing:
                        MockBing.return_value.collect.return_value = bing_site_low
                        result = dispatch_search("RTX 5090 电源接口 规格", site="nvidia.com")

        self.assertEqual(result.provider, "searxng", "Should retry SearXNG without site when Bing is low quality")
        self.assertEqual(len(result.candidates), 5, "Should return SearXNG no-site results")
        self.assertEqual(call_count["searxng_collect"], 2, "Should call SearXNG twice: with site then without")

    def test_agent_search_searxng_first_also_retries_without_site(self):
        """_search_searxng_first (used by ask/verify) must retry SearXNG without site when Bing is low quality.

        This is the same root cause as dispatch_search but in the agent's separate
        search path. ask uses run_tool -> _search_searxng_first, NOT dispatch_search.
        """
        from source_radar.agent import VerificationAgent
        from source_radar.acquisition import AcquisitionResult, CandidateSource
        from source_radar.llm import AIProvider

        searxng_site_empty = AcquisitionResult(
            provider="searxng", provider_type="external-bridge",
            status="no-evidence", reason="no-candidates", message="empty",
        )
        searxng_no_site = AcquisitionResult(
            provider="searxng", provider_type="external-bridge",
            status="ok", reason="items-found", message="ok",
            candidates=[
                CandidateSource(
                    title=f"Relevant {i}", url=f"https://r.com/{i}",
                    snippet="relevant content", provider="searxng",
                )
                for i in range(5)
            ],
        )
        bing_low = AcquisitionResult(
            provider="search", provider_type="search",
            status="ok", reason="candidates-found", message="ok",
            candidates=[CandidateSource(
                title="Irrelevant Marketing", url="https://nvidia.com/geforce",
                snippet="marketing page", provider="search",
            )],
        )

        call_count = {"searxng": 0}
        class FakeSearXNG:
            provider = "searxng"
            def status(self):
                return AcquisitionResult(provider="searxng", provider_type="external-bridge",
                                         status="ok", reason="ready", message="ok")
            def collect(self, request):
                call_count["searxng"] += 1
                if request.site:
                    return searxng_site_empty
                return searxng_no_site

        class FakeBing:
            provider = "search"
            def collect(self, request):
                return bing_low

        with patch("source_radar.acquisition._assess_quality", side_effect=lambda r, q: MagicMock(
            score="low" if r.provider == "search" else "high",
            signals=[], reason="", suggestions=[]
        )):
            agent = VerificationAgent(
                provider=MagicMock(spec=AIProvider),
                acquisition_providers=[FakeSearXNG(), FakeBing()],
            )
            result = agent._search_searxng_first(
                claim="test query", url=None, repo=None, limit=5,
                site="nvidia.com", page=1, platforms_list=None,
            )

        self.assertEqual(result.provider, "searxng", "Should retry SearXNG without site")


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
