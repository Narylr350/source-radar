"""Test that fetch_with_fallback lives in acquisition layer, not MCP server."""
import unittest
from unittest.mock import patch, MagicMock
from source_radar.acquisition import fetch_with_fallback, AcquisitionRequest, AcquisitionResult


class UnifiedFetchEntryTest(unittest.TestCase):
    """fetch_with_fallback must be in acquisition layer, usable by both MCP and agent."""

    def test_fetch_with_fallback_exists_in_acquisition(self):
        """fetch_with_fallback is importable from acquisition."""
        self.assertTrue(callable(fetch_with_fallback))

    def test_fetch_with_fallback_uses_trafilatura_first(self):
        """When trafilatura returns good content, no crawl4ai fallback."""
        from source_radar.models import SourceItem
        request = AcquisitionRequest(query="", url="https://example.com/page", limit=1)
        good_result = AcquisitionResult(
            provider="trafilatura", provider_type="generic-crawler",
            status="ok", reason="items-found", message="ok",
            items=[SourceItem(
                source_type="web-page", title="Test", url="https://example.com/page",
                snippet="test snippet", adapter="trafilatura",
                raw_content="x" * 300,
            )],
        )
        with patch("source_radar.acquisition.TrafilaturaProvider") as mock_trafilatura:
            mock_trafilatura.return_value.collect.return_value = good_result
            result = fetch_with_fallback(request)

        self.assertEqual(result.provider, "trafilatura")

    def test_crawl4ai_domains_on_provider_class(self):
        """Crawl4AIProvider should know which domains need JS rendering."""
        from source_radar.acquisition import Crawl4AIProvider
        self.assertTrue(hasattr(Crawl4AIProvider, "JS_RENDER_DOMAINS"))
        self.assertIn("liquipedia.net", Crawl4AIProvider.JS_RENDER_DOMAINS)


if __name__ == "__main__":
    unittest.main()
