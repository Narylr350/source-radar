import json
import os
import sys
import types
import unittest
from unittest.mock import patch

from source_radar.acquisition import (
    AcquisitionRequest,
    BingSearchProvider,
    Crawl4AIProvider,
    TrafilaturaProvider,
    XquikProvider,
    _BaiduResultParser,
)


class AcquisitionM5Tests(unittest.TestCase):
    def test_baidu_parser_reads_container_results_with_mu_and_snippet(self):
        html = """
        <html><body>
          <div id="content_left">
            <div class="result c-container xpath-log new-pmd" mu="https://www.donews.com/news/detail/1/6481497.html">
              <h3 class="t"><a href="https://www.baidu.com/link?url=abc">张雪峰去世 公司发布讣告</a></h3>
              <div class="c-abstract">苏州峰学蔚来教育科技有限公司发布讣告。</div>
            </div>
            <div class="result c-container xpath-log new-pmd" mu="https://www.cls.cn/detail/2323463">
              <div class="c-title"><a href="https://www.baidu.com/link?url=def">张雪峰逝世 财联社</a></div>
              <div class="c-span-last">财联社报道，张雪峰因心源性猝死抢救无效。</div>
            </div>
          </div>
        </body></html>
        """

        parser = _BaiduResultParser()
        parser.feed(html)

        self.assertEqual([c.title for c in parser.candidates], [
            "张雪峰去世 公司发布讣告",
            "张雪峰逝世 财联社",
        ])
        self.assertEqual(parser.candidates[0].url, "https://www.donews.com/news/detail/1/6481497.html")
        self.assertIn("苏州峰学蔚来", parser.candidates[0].snippet)
        self.assertEqual(parser.candidates[1].url, "https://www.cls.cn/detail/2323463")
        self.assertIn("心源性猝死", parser.candidates[1].snippet)

    def test_baidu_provider_uses_browser_fallback_for_security_page(self):
        security_html = "<html><title>百度安全验证</title><body>百度安全验证</body></html>"
        rendered_html = """
        <html><body>
          <div class="result c-container xpath-log new-pmd" mu="https://www.donews.com/news/detail/1/6481497.html">
            <h3 class="t"><a href="https://www.baidu.com/link?url=abc">张雪峰官方讣告发布</a></h3>
            <div class="c-abstract">公司发布讣告，张雪峰因心源性猝死逝世。</div>
          </div>
        </body></html>
        """

        class Response:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return security_html.encode("utf-8")

        with patch("source_radar.acquisition.urlopen", return_value=Response()):
            with patch("source_radar.acquisition._fetch_baidu_with_browser", return_value=rendered_html) as browser:
                from source_radar.acquisition import BaiduSearchProvider

                result = BaiduSearchProvider().collect(
                    AcquisitionRequest(query='"张雪峰" 讣告', limit=1)
                )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.provider, "search-baidu")
        self.assertEqual(result.candidates[0].url, "https://www.donews.com/news/detail/1/6481497.html")
        self.assertIn("官方讣告", result.candidates[0].title)
        browser.assert_called_once()

    def test_search_provider_discovers_candidate_sources(self):
        html = """
        <html><body>
          <li class="b_algo">
            <h2><a href="https://example.test/one">First Result</a></h2>
            <div class="b_caption"><p>First snippet.</p></div>
          </li>
          <li class="b_algo">
            <h2><a href="https://example.test/two">Second Result</a></h2>
            <div class="b_caption"><p>Second snippet.</p></div>
          </li>
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
            result = BingSearchProvider().collect(
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
          <li class="b_algo">
            <h2><a href="https://example.test/page">Example Page</a></h2>
            <div class="b_caption"><p>Example snippet.</p></div>
          </li>
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
          <li class="b_algo">
            <h2><a href="https://example.test/dynamic">Dynamic Page</a></h2>
            <div class="b_caption"><p>Dynamic snippet.</p></div>
          </li>
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

    def test_xquik_provider_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            result = XquikProvider().collect(
                AcquisitionRequest(query="from:source_radar", limit=2)
            )

        self.assertEqual(result.status, "needs-input")
        self.assertEqual(result.reason, "missing-api-key")
        self.assertIn("XQUIK_API_KEY", result.fix)

    def test_xquik_provider_maps_tweets_to_source_items(self):
        payload = {
            "tweets": [
                {
                    "id": "1234567890123456789",
                    "text": "Source Radar now supports auditable source cards.",
                    "createdAt": "2026-06-15T00:00:00Z",
                    "url": "https://x.com/source_radar/status/1234567890123456789",
                    "author": {"username": "source_radar"},
                }
            ],
            "has_next_page": False,
            "next_cursor": "",
        }

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with patch.dict(os.environ, {"XQUIK_API_KEY": "test-key"}, clear=True):
            with patch("source_radar.acquisition.urlopen", return_value=Response()) as open_url:
                result = XquikProvider().collect(
                    AcquisitionRequest(query="source-radar", limit=2)
                )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.items[0].adapter, "xquik")
        self.assertEqual(result.items[0].source_type, "x-post")
        self.assertEqual(result.items[0].metadata["tweet_id"], "1234567890123456789")
        self.assertIn("auditable source cards", result.items[0].snippet)
        request = open_url.call_args[0][0]
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers["x-api-key"], "test-key")


if __name__ == "__main__":
    unittest.main()
