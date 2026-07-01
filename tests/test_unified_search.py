"""Test that run_tool("search") delegates to dispatch_search, not _search_searxng_first."""
import unittest
from unittest.mock import patch, MagicMock
from source_radar.agent import VerificationAgent
from source_radar.acquisition import AcquisitionResult, CandidateSource


class UnifiedSearchEntryTest(unittest.TestCase):
    """run_tool('search') must call dispatch_search, not a separate _search_searxng_first."""

    def test_run_tool_search_calls_dispatch_search(self):
        """run_tool with tool='search' should delegate to dispatch_search."""
        agent = VerificationAgent(provider=MagicMock())

        with patch("source_radar.agent.dispatch_search") as mock_dispatch:
            mock_dispatch.return_value = AcquisitionResult(
                provider="searxng", provider_type="external-bridge",
                status="ok", reason="items-found", message="ok",
                candidates=[CandidateSource(
                    title="test", url="https://test.com",
                    snippet="test content", provider="searxng",
                )],
            )
            with patch("source_radar.cache.get_cached_result", return_value=(None, 0)):
                with patch("source_radar.cache.put_cached_result"):
                    result, cache_hit, cache_key, cache_age = agent.run_tool(
                        "search", claim="test query", url=None, repo=None,
                        html=None, github_payload=None,
                    )

        mock_dispatch.assert_called_once()
        self.assertEqual(result.provider, "searxng")

    def test_run_tool_search_passes_acquisition_providers(self):
        """run_tool should pass self.acquisition_providers to dispatch_search so injected providers are used."""
        class FakeSearXNG:
            provider = "searxng"
            provider_type = "external-bridge"
            def status(self):
                return AcquisitionResult(provider="searxng", provider_type="external-bridge",
                                         status="ok", reason="ready", message="ok")
            def collect(self, request):
                return AcquisitionResult(
                    provider="searxng", provider_type="external-bridge",
                    status="ok", reason="items-found", message="ok",
                    candidates=[CandidateSource(
                        title="injected result for test", url="https://injected.com",
                        snippet="test content from injected provider for test query", provider="searxng",
                    )],
                )

        agent = VerificationAgent(
            provider=MagicMock(),
            acquisition_providers=[FakeSearXNG()],
        )

        with patch("source_radar.cache.get_cached_result", return_value=(None, 0)):
            with patch("source_radar.cache.put_cached_result"):
                result, _, _, _ = agent.run_tool(
                    "search", claim="test", url=None, repo=None,
                    html=None, github_payload=None,
                )

        self.assertEqual(result.provider, "searxng")
        self.assertEqual(result.candidates[0].title, "injected result for test")


if __name__ == "__main__":
    unittest.main()
