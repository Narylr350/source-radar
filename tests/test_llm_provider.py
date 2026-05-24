import json
import os
import unittest
from unittest.mock import patch

from source_radar.llm import LocalFallbackProvider, OpenAIResponsesProvider
from source_radar.models import EvidenceCard


class LlmProviderTests(unittest.TestCase):
    def test_provider_uses_local_fallback_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = OpenAIResponsesProvider.from_environment()

        self.assertIsInstance(provider, LocalFallbackProvider)

    def test_provider_reads_endpoint_and_model_from_environment(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "SOURCE_RADAR_OPENAI_MODEL": "local-model",
                "SOURCE_RADAR_OPENAI_ENDPOINT": "http://127.0.0.1:8000/v1/responses",
            },
            clear=True,
        ):
            provider = OpenAIResponsesProvider.from_environment()

        self.assertEqual(provider.model, "local-model")
        self.assertEqual(provider.endpoint, "http://127.0.0.1:8000/v1/responses")

    def test_provider_parses_responses_api_text(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps({"output_text": "AI cites ev-001."}).encode("utf-8")

        card = EvidenceCard(
            id="ev-001",
            source_type="web-page",
            title="Title",
            url="https://example.test",
            summary="Summary",
            adapter="web",
        )

        with patch("source_radar.llm.urlopen", return_value=Response()):
            provider = OpenAIResponsesProvider("test-key", model="local-model")
            judgement = provider.judge("claim", [card])

        self.assertEqual(judgement.status, "ai-judged")
        self.assertEqual(judgement.summary, "AI cites ev-001.")
        self.assertEqual(judgement.evidence_ids, ["ev-001"])


if __name__ == "__main__":
    unittest.main()
