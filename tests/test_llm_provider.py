import json
import os
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from source_radar.llm import LocalFallbackProvider, AIProvider
from source_radar.models import EvidenceCard


class LlmProviderTests(unittest.TestCase):
    def test_provider_uses_local_fallback_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = AIProvider.from_environment()

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
            provider = AIProvider.from_environment()

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
            provider = AIProvider("test-key", model="local-model")
            judgement = provider.judge("claim", [card])

        self.assertEqual(judgement.status, "ai-judged")
        self.assertEqual(judgement.summary, "AI cites ev-001.")
        self.assertEqual(judgement.evidence_ids, ["ev-001"])

    def test_provider_parses_structured_judgement_json(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "output_text": json.dumps(
                            {
                                "summary": "不能确定今年会考微积分，现有来源缺少官方依据。",
                                "evidence_ids": ["ev-001"],
                                "gaps": ["缺少教育部或考试院官方来源。"],
                                "confidence": "low",
                                "confidence_reason": "缺少官方来源。",
                            },
                            ensure_ascii=False,
                        )
                    }
                ).encode("utf-8")

        card = EvidenceCard(
            id="ev-001",
            source_type="web-page",
            title="Title",
            url="https://example.test",
            summary="Summary",
            adapter="web",
        )

        with patch("source_radar.llm.urlopen", return_value=Response()):
            provider = AIProvider("test-key", model="local-model")
            judgement = provider.judge("claim", [card])

        self.assertEqual(judgement.summary, "不能确定今年会考微积分，现有来源缺少官方依据。")
        self.assertEqual(judgement.evidence_ids, ["ev-001"])
        self.assertEqual(judgement.gaps, ["缺少教育部或考试院官方来源。"])
        self.assertEqual(judgement.confidence, "low")
        self.assertEqual(judgement.confidence_reason, "缺少官方来源。")

    def test_provider_parses_synthesis_json(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "output_text": json.dumps(
                            {
                                "summary": "综合结论。",
                                "key_points": ["搜索结果要点一。"],
                                "source_notes": ["来源分布 ev-001。"],
                                "disagreements": [],
                                "noise_notes": ["搜索结果只是线索。"],
                            },
                            ensure_ascii=False,
                        )
                    }
                ).encode("utf-8")

        card = EvidenceCard(
            id="ev-001",
            source_type="web-page",
            title="Title",
            url="https://example.test",
            summary="Summary",
            adapter="trafilatura",
        )

        with patch("source_radar.llm.urlopen", return_value=Response()):
            provider = AIProvider("test-key", model="local-model")
            analysis = provider.synthesize("query", [card])

        self.assertEqual(analysis.summary, "综合结论。")
        self.assertEqual(analysis.key_points, ["搜索结果要点一。"])
        self.assertEqual(analysis.disagreements, [])
        self.assertEqual(analysis.noise_notes, ["搜索结果只是线索。"])

    def test_provider_falls_back_to_chat_completions_for_local_apis(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": "Chat cites ev-001."}}]}
                ).encode("utf-8")

        card = EvidenceCard(
            id="ev-001",
            source_type="web-page",
            title="Title",
            url="https://example.test",
            summary="Summary",
            adapter="web",
        )
        requested_urls = []

        def fake_urlopen(request, timeout=60):
            requested_urls.append(request.full_url)
            if request.full_url.endswith("/responses"):
                raise HTTPError(request.full_url, 502, "Bad Gateway", {}, None)
            return Response()

        with patch("source_radar.llm.urlopen", side_effect=fake_urlopen):
            provider = AIProvider(
                "test-key",
                model="local-model",
                endpoint="http://127.0.0.1:8000/v1/responses",
            )
            judgement = provider.judge("claim", [card])

        self.assertEqual(requested_urls, [
            "http://127.0.0.1:8000/v1/responses",
            "http://127.0.0.1:8000/v1/chat/completions",
        ])
        self.assertEqual(judgement.status, "ai-judged")
        self.assertEqual(judgement.summary, "Chat cites ev-001.")


if __name__ == "__main__":
    unittest.main()
