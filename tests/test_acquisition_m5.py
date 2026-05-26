import json
import os
import sys
import tempfile
import types
import unittest
from urllib.error import URLError
from unittest.mock import patch

from source_radar.acquisition import (
    AcquisitionRequest,
    Crawl4AIProvider,
    DuckDuckGoSearchProvider,
    ExternalBridgeProvider,
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

    def test_external_bridge_provider_reports_missing_endpoint(self):
        provider = ExternalBridgeProvider("firecrawl", env_var="SOURCE_RADAR_FIRECRAWL_ENDPOINT")

        with patch.dict("os.environ", {}, clear=True):
            result = provider.collect(AcquisitionRequest(query="claim"))

        self.assertEqual(result.provider, "firecrawl")
        self.assertEqual(result.status, "disabled")
        self.assertEqual(result.reason, "missing-endpoint")
        self.assertEqual(result.candidates, [])

    def test_external_bridge_provider_parses_json_items(self):
        payload = {
            "items": [
                {
                    "title": "Bridge Page",
                    "url": "https://example.test/bridge",
                    "snippet": "Bridge evidence.",
                    "source_type": "web-page",
                }
            ]
        }

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with patch.dict("os.environ", {"SOURCE_RADAR_FIRECRAWL_ENDPOINT": "https://bridge.test"}, clear=True):
            with patch("source_radar.acquisition.urlopen", return_value=Response()) as request:
                result = ExternalBridgeProvider(
                    "firecrawl",
                    env_var="SOURCE_RADAR_FIRECRAWL_ENDPOINT",
                ).collect(AcquisitionRequest(query="claim"))

        self.assertEqual(result.status, "ok")
        self.assertEqual(request.call_args.kwargs["timeout"], 90)
        self.assertEqual(result.items[0].adapter, "firecrawl")
        self.assertEqual(result.candidates[0].url, "https://example.test/bridge")

    def test_external_bridge_provider_reads_local_config_endpoint(self):
        payload = {"items": []}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
                from source_radar.config import save_provider_config

                save_provider_config("firecrawl", endpoint="https://bridge.test")
                with patch("source_radar.acquisition.urlopen", return_value=Response()) as request:
                    ExternalBridgeProvider(
                        "firecrawl",
                        env_var="SOURCE_RADAR_FIRECRAWL_ENDPOINT",
                    ).collect(AcquisitionRequest(query="claim"))

        self.assertEqual(request.call_args[0][0].full_url, "https://bridge.test/collect")

    def test_external_bridge_status_reads_manifest_and_health_for_ai_use(self):
        manifest = {
            "provider": "firecrawl",
            "contract_version": "source-radar.bridge.v1",
            "capabilities": [
                {
                    "name": "search",
                    "description": "Find candidate web sources for a claim.",
                }
            ],
            "ai_guidance": "Use for broad web source discovery.",
        }
        health = {
            "status": "ok",
            "reason": "ready",
            "message": "Bridge is ready.",
        }

        class Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        def fake_urlopen(request, timeout=30):
            if request.full_url == "https://bridge.test/manifest":
                return Response(manifest)
            if request.full_url == "https://bridge.test/health":
                return Response(health)
            raise AssertionError(request.full_url)

        with patch.dict("os.environ", {"SOURCE_RADAR_FIRECRAWL_ENDPOINT": "https://bridge.test"}, clear=True):
            with patch("source_radar.acquisition.urlopen", side_effect=fake_urlopen):
                result = ExternalBridgeProvider(
                    "firecrawl",
                    env_var="SOURCE_RADAR_FIRECRAWL_ENDPOINT",
                ).status()

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.reason, "ready")
        self.assertEqual(result.diagnostics["contract_version"], "source-radar.bridge.v1")
        self.assertEqual(result.diagnostics["capabilities"], "search")
        self.assertIn("broad web", result.diagnostics["ai_guidance"])

    def test_external_bridge_status_reports_service_unreachable_with_fix(self):
        with patch.dict("os.environ", {"SOURCE_RADAR_FIRECRAWL_ENDPOINT": "https://bridge.test"}, clear=True):
            with patch("source_radar.acquisition.urlopen", side_effect=URLError("refused")):
                result = ExternalBridgeProvider(
                    "firecrawl",
                    env_var="SOURCE_RADAR_FIRECRAWL_ENDPOINT",
                ).status()

        self.assertEqual(result.status, "error")
        self.assertEqual(result.reason, "service-unreachable")
        self.assertEqual(result.retryable, True)
        self.assertIn("source-radar bridge firecrawl", result.fix)

    def test_external_bridge_auto_repairs_endpoint_route_to_base_url(self):
        manifest = {
            "provider": "firecrawl",
            "contract_version": "source-radar.bridge.v1",
            "capabilities": [{"name": "search"}],
        }
        health = {"status": "ok", "reason": "ready", "message": "Bridge is ready."}

        class Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        requested_urls = []

        def fake_urlopen(request, timeout=30):
            requested_urls.append(request.full_url)
            if request.full_url == "https://bridge.test/manifest":
                return Response(manifest)
            if request.full_url == "https://bridge.test/health":
                return Response(health)
            raise AssertionError(request.full_url)

        with patch.dict("os.environ", {"SOURCE_RADAR_FIRECRAWL_ENDPOINT": "https://bridge.test/collect"}, clear=True):
            with patch("source_radar.acquisition.urlopen", side_effect=fake_urlopen):
                result = ExternalBridgeProvider(
                    "firecrawl",
                    env_var="SOURCE_RADAR_FIRECRAWL_ENDPOINT",
                ).status()

        self.assertEqual(result.status, "ok")
        self.assertEqual(requested_urls, [
            "https://bridge.test/manifest",
            "https://bridge.test/health",
        ])
        self.assertEqual(result.diagnostics["endpoint_auto_repair"], "stripped-route")

    def test_external_bridge_collect_preserves_bridge_diagnostics(self):
        payload = {
            "status": "needs-input",
            "reason": "auth-missing",
            "message": "Cookie is required.",
            "fix": "Configure the bridge cookie locally.",
            "retryable": False,
            "warnings": ["No anonymous access."],
            "evidence_gaps": ["Cannot collect login-gated sources."],
            "diagnostics": {"credential": "missing-cookie"},
            "items": [],
        }

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with patch.dict("os.environ", {"SOURCE_RADAR_FIRECRAWL_ENDPOINT": "https://bridge.test"}, clear=True):
            with patch("source_radar.acquisition.urlopen", return_value=Response()) as request:
                result = ExternalBridgeProvider(
                    "firecrawl",
                    env_var="SOURCE_RADAR_FIRECRAWL_ENDPOINT",
                ).collect(AcquisitionRequest(query="claim"))

        self.assertEqual(request.call_args[0][0].full_url, "https://bridge.test/collect")
        self.assertEqual(result.status, "needs-input")
        self.assertEqual(result.reason, "auth-missing")
        self.assertEqual(result.fix, "Configure the bridge cookie locally.")
        self.assertEqual(result.retryable, False)
        self.assertEqual(result.warnings, ["No anonymous access."])
        self.assertEqual(result.evidence_gaps, ["Cannot collect login-gated sources."])
        self.assertEqual(result.diagnostics["credential"], "missing-cookie")


if __name__ == "__main__":
    unittest.main()
