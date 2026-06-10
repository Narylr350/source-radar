import os
import sys
import types
import unittest
from unittest.mock import patch

from source_radar.acquisition import (
    AcquisitionRequest,
    Crawl4AIProvider,
    DuckDuckGoSearchProvider,
    TrafilaturaProvider,
)


class AcquisitionM5Tests(unittest.TestCase):
    def test_search_provider_discovers_candidate_sources(self):
        html = """
        <html><body>
          <a class="result-link" href="https://example.test/one">First Result</a>
          <a class="result-link" href="/l/?uddg=https%3A%2F%2Fexample.test%2Ftwo">Second Result</a>
        </body></html>
        """

        class Response:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return html.encode("utf-8")

        with patch("source_radar.acquisition.urlopen", return_value=Response()):
            result = DuckDuckGoSearchProvider().collect(
                AcquisitionRequest(query="source radar", limit=2)
            )

        self.assertEqual(result.provider, "search")
        self.assertEqual(result.status, "ok")
        self.assertEqual([candidate.url for candidate in result.candidates], [
            "https://example.test/one",
            "https://example.test/two",
        ])
        self.assertEqual(result.items[0].adapter, "search")
        self.assertEqual(result.items[0].source_type, "search-result")

    def test_trafilatura_provider_discovers_urls_and_extracts_main_text(self):
        html = """
        <html><body>
          <a class="result-link" href="https://example.test/page">Example Page</a>
        </body></html>
        """

        class Response:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return html.encode("utf-8")

        metadata = types.SimpleNamespace(
            title="Extracted Title",
            author="Author",
            date="2026-05-25",
        )
        fake_trafilatura = types.SimpleNamespace(
            fetch_url=lambda url: "<article>Body text</article>",
            extract=lambda downloaded, include_comments=False: "Body text from article.",
            extract_metadata=lambda downloaded: metadata,
        )

        with patch.dict(sys.modules, {"trafilatura": fake_trafilatura}):
            with patch("source_radar.acquisition.urlopen", return_value=Response()):
                result = TrafilaturaProvider().collect(
                    AcquisitionRequest(query="example", limit=1)
                )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.items[0].adapter, "trafilatura")
        self.assertEqual(result.items[0].title, "Extracted Title")
        self.assertEqual(result.items[0].metadata["extractor"], "trafilatura")
        self.assertEqual(result.candidates[0].url, "https://example.test/page")

    def test_crawl4ai_provider_discovers_urls_and_extracts_markdown(self):
        html = """
        <html><body>
          <a class="result-link" href="https://example.test/dynamic">Dynamic Page</a>
        </body></html>
        """

        class Response:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return html.encode("utf-8")

        class FakeCrawler:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            async def arun(self, url):
                return types.SimpleNamespace(
                    markdown="# Dynamic Page\nRendered content.",
                    metadata={"title": "Rendered Title"},
                )

        fake_crawl4ai = types.SimpleNamespace(AsyncWebCrawler=FakeCrawler)

        with patch.dict(sys.modules, {"crawl4ai": fake_crawl4ai}):
            with patch("source_radar.acquisition.urlopen", return_value=Response()):
                result = Crawl4AIProvider().collect(
                    AcquisitionRequest(query="dynamic", limit=1)
                )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.items[0].adapter, "crawl4ai")
        self.assertEqual(result.items[0].title, "Rendered Title")
        self.assertEqual(result.items[0].metadata["extractor"], "crawl4ai")

    def test_local_crawler_provider_reports_missing_dependency(self):
        with patch("source_radar.acquisition.importlib.import_module", side_effect=ImportError("missing")):
            result = TrafilaturaProvider().status()

        self.assertEqual(result.status, "needs-input")
        self.assertEqual(result.reason, "missing-dependency")
        self.assertIn("pip install trafilatura", result.fix)


if __name__ == "__main__":
    unittest.main()
