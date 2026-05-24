import json
import os
import tempfile
import unittest
from unittest.mock import patch

from source_radar.acquisition import (
    AcquisitionRequest,
    DuckDuckGoSearchProvider,
    ExternalBridgeProvider,
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
            with patch("source_radar.acquisition.urlopen", return_value=Response()):
                result = ExternalBridgeProvider(
                    "firecrawl",
                    env_var="SOURCE_RADAR_FIRECRAWL_ENDPOINT",
                ).collect(AcquisitionRequest(query="claim"))

        self.assertEqual(result.status, "ok")
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

        self.assertEqual(request.call_args[0][0].full_url, "https://bridge.test")


if __name__ == "__main__":
    unittest.main()
