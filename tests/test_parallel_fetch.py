"""Test that fetch_search_results fetches URLs in parallel, not serially."""
import unittest
import asyncio
import time
from unittest.mock import patch
from source_radar.acquisition import AcquisitionResult, CandidateSource, SourceItem


class ParallelFetchTest(unittest.TestCase):
    """handle_fetch_search_results should fetch pages concurrently."""

    def test_fetch_pages_run_in_parallel(self):
        """3 URLs each taking 1s should finish in ~1s (parallel), not ~3s (serial)."""
        from source_radar.mcp.server import handle_fetch_search_results

        search_result = AcquisitionResult(
            provider="searxng", provider_type="external-bridge",
            status="ok", reason="items-found", message="ok",
            candidates=[
                CandidateSource(
                    title=f"Result {i}", url=f"https://example.com/{i}",
                    snippet="snippet", provider="searxng", source_type="search-result",
                )
                for i in range(3)
            ],
        )

        def slow_fetch(request):
            time.sleep(1.0)
            return AcquisitionResult(
                provider="trafilatura", provider_type="generic-crawler",
                status="ok", reason="items-found", message="ok",
                items=[SourceItem(
                    source_type="web-page", title="Page", url=request.url,
                    snippet="s", adapter="trafilatura",
                    raw_content="content " * 50, raw_content_length=400,
                    metadata={"extractor": "trafilatura"},
                )],
            )

        async def run():
            with patch("source_radar.mcp.server.dispatch_search", return_value=search_result):
                with patch("source_radar.mcp.server._ensure_searxng_for_search", return_value=(True, "")):
                    with patch("source_radar.mcp.server.fetch_with_fallback", side_effect=slow_fetch):
                        return await handle_fetch_search_results(
                            {"query": "test", "limit": 5, "fetch_count": 3}
                        )

        t0 = time.time()
        result = asyncio.run(run())
        elapsed = time.time() - t0

        self.assertFalse(result.isError)
        # Parallel: ~1s. Serial would be ~3s. Allow generous margin.
        self.assertLess(elapsed, 2.0, f"Expected parallel (~1s), got {elapsed:.1f}s (serial?)")

    def test_output_order_preserved(self):
        """Parallel fetch must preserve result order (result 1, 2, 3)."""
        from source_radar.mcp.server import handle_fetch_search_results

        search_result = AcquisitionResult(
            provider="searxng", provider_type="external-bridge",
            status="ok", reason="items-found", message="ok",
            candidates=[
                CandidateSource(
                    title=f"Title-{i}", url=f"https://example.com/{i}",
                    snippet="snippet", provider="searxng", source_type="search-result",
                )
                for i in range(3)
            ],
        )

        def fetch(request):
            return AcquisitionResult(
                provider="trafilatura", provider_type="generic-crawler",
                status="ok", reason="items-found", message="ok",
                items=[SourceItem(
                    source_type="web-page", title="Page", url=request.url,
                    snippet="s", adapter="trafilatura",
                    raw_content=f"body-of-{request.url}", raw_content_length=20,
                    metadata={"extractor": "trafilatura"},
                )],
            )

        async def run():
            with patch("source_radar.mcp.server.dispatch_search", return_value=search_result):
                with patch("source_radar.mcp.server._ensure_searxng_for_search", return_value=(True, "")):
                    with patch("source_radar.mcp.server.fetch_with_fallback", side_effect=fetch):
                        return await handle_fetch_search_results(
                            {"query": "test", "limit": 5, "fetch_count": 3}
                        )

        result = asyncio.run(run())
        text = result.content[0].text
        pos0 = text.find("Title-0")
        pos1 = text.find("Title-1")
        pos2 = text.find("Title-2")
        self.assertTrue(0 <= pos0 < pos1 < pos2, "Results must be in order 0,1,2")


if __name__ == "__main__":
    unittest.main()
