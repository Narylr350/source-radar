import json
import unittest

import os
from unittest.mock import patch

from source_radar.acquisition import (
    AcquisitionResult,
    CandidateSource,
    ExternalBridgeProvider,
)
from source_radar.agent import VerificationAgent
from source_radar.models import Judgement, SourceItem
from source_radar.reporting import render_markdown


class FakeProvider:
    status = "configured"
    model = "fake-model"

    def judge(self, claim, evidence):
        return Judgement(
            status="ai-judged",
            summary=f"AI judged {claim} using {len(evidence)} evidence cards.",
            evidence_ids=[card.id for card in evidence],
            gaps=["No extra gap from fake provider."],
        )


class FailingProvider:
    status = "configured"
    model = "failing-model"

    def judge(self, claim, evidence):
        raise RuntimeError("provider unavailable")


class FakeSearchProvider:
    provider = "search"
    provider_type = "search"

    def collect(self, request):
        return AcquisitionResult(
            provider="search",
            provider_type="search",
            status="ok",
            reason="candidates-found",
            message="Search returned candidates.",
            candidates=[
                CandidateSource(
                    title="Candidate",
                    url="https://example.test/candidate",
                    provider="search",
                    snippet="Candidate snippet.",
                )
            ],
            items=[
                SourceItem(
                    source_type="search-result",
                    title="Candidate",
                    url="https://example.test/candidate",
                    snippet="Candidate snippet.",
                    adapter="search",
                )
            ],
        )


class FakeBridgeProvider:
    provider = "firecrawl"
    provider_type = "external-bridge"

    def status(self):
        return AcquisitionResult(
            provider="firecrawl",
            provider_type="external-bridge",
            status="ok",
            reason="ready",
            message="Bridge is ready for AI calls.",
            diagnostics={
                "capabilities": "search",
                "contract_version": "source-radar.bridge.v1",
                "ai_guidance": "Use for broad web source discovery.",
            },
        )

    def collect(self, request):
        return AcquisitionResult(
            provider="firecrawl",
            provider_type="external-bridge",
            status="ok",
            reason="items-found",
            message="Bridge returned evidence.",
            items=[
                SourceItem(
                    source_type="web-page",
                    title="Bridge Evidence",
                    url="https://example.test/bridge",
                    snippet="Bridge evidence.",
                    adapter="firecrawl",
                )
            ],
        )


class AgentFlowTests(unittest.TestCase):
    def test_agent_auto_plans_fixture_tool_for_project_claim(self):
        report = VerificationAgent(provider=FakeProvider()).verify(
            "source-radar 是本地 CLI"
        )

        self.assertEqual(report.status, "ai-judged")
        self.assertEqual(report.agent.mode, "agent")
        self.assertEqual(report.agent.ai_status, "configured")
        self.assertEqual(report.agent.planned_tools, ["fixture"])
        self.assertEqual(report.agent.tool_calls[0]["items_found"], "1")
        self.assertEqual(report.judgement.evidence_ids, ["ev-001"])

    def test_agent_can_run_explicit_github_tool_with_fixture_payload(self):
        payload = {
            "full_name": "openai/source-radar-example",
            "description": "Example repository.",
            "html_url": "https://github.com/openai/source-radar-example",
            "stargazers_count": 7,
            "forks_count": 1,
            "pushed_at": "2026-05-24T00:00:00Z",
        }

        report = VerificationAgent(provider=FakeProvider()).verify(
            "openai/source-radar-example",
            source="github",
            repo="openai/source-radar-example",
            github_payload=payload,
        )

        self.assertEqual(report.agent.planned_tools, ["github"])
        self.assertEqual(report.evidence[0].adapter, "github")
        self.assertEqual(report.judgement.status, "ai-judged")

    def test_agent_report_json_contains_trace(self):
        report = VerificationAgent(provider=FakeProvider()).verify(
            "source-radar 是本地 CLI"
        )

        payload = report.to_dict()

        self.assertEqual(payload["agent"]["mode"], "agent")
        self.assertEqual(payload["agent"]["model"], "fake-model")
        json.dumps(payload)

    def test_agent_returns_structured_ai_error_when_provider_fails(self):
        report = VerificationAgent(provider=FailingProvider()).verify(
            "source-radar 是本地 CLI"
        )

        self.assertEqual(report.status, "ai-error")
        self.assertEqual(report.agent.ai_status, "error")
        self.assertEqual(report.judgement.evidence_ids, ["ev-001"])
        self.assertIn("provider unavailable", report.judgement.gaps[0])

    def test_agent_auto_uses_acquisition_provider_for_generic_claims(self):
        report = VerificationAgent(
            provider=FakeProvider(),
            acquisition_providers=[FakeSearchProvider()],
        ).verify("generic product change")

        self.assertEqual(report.agent.planned_tools, ["search"])
        self.assertEqual(report.agent.acquisition[0].provider, "search")
        self.assertEqual(report.agent.acquisition[0].candidate_count, 1)
        self.assertEqual(report.evidence[0].adapter, "search")

    def test_agent_json_contains_source_acquisition_trace(self):
        report = VerificationAgent(
            provider=FakeProvider(),
            acquisition_providers=[FakeSearchProvider()],
        ).verify("generic product change")

        payload = report.to_dict()

        self.assertEqual(payload["agent"]["acquisition"][0]["provider"], "search")
        self.assertEqual(
            payload["agent"]["acquisition"][0]["candidates"][0]["url"],
            "https://example.test/candidate",
        )

    def test_markdown_report_contains_source_acquisition_trace(self):
        report = VerificationAgent(
            provider=FakeProvider(),
            acquisition_providers=[FakeSearchProvider()],
        ).verify("generic product change")

        markdown = render_markdown(report)

        self.assertIn("## Source Acquisition", markdown)
        self.assertIn("search: ok", markdown)
        self.assertIn("https://example.test/candidate", markdown)

    def test_agent_auto_invokes_ai_callable_bridge_provider(self):
        report = VerificationAgent(
            provider=FakeProvider(),
            acquisition_providers=[FakeSearchProvider(), FakeBridgeProvider()],
        ).verify("generic product change")

        self.assertEqual(report.agent.planned_tools, ["search", "firecrawl"])
        self.assertEqual(
            [trace.provider for trace in report.agent.acquisition],
            ["search", "firecrawl"],
        )
        self.assertEqual(report.evidence[1].adapter, "firecrawl")

    def test_agent_uses_external_bridge_provider_contract_end_to_end(self):
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
                return Response(
                    {
                        "provider": "firecrawl",
                        "contract_version": "source-radar.bridge.v1",
                        "capabilities": [{"name": "search"}],
                        "ai_guidance": "Use for broad web discovery.",
                    }
                )
            if request.full_url == "https://bridge.test/health":
                return Response(
                    {
                        "status": "ok",
                        "reason": "ready",
                        "message": "Bridge is ready.",
                    }
                )
            if request.full_url == "https://bridge.test/collect":
                return Response(
                    {
                        "status": "ok",
                        "reason": "items-found",
                        "message": "Bridge collected crawler evidence.",
                        "items": [
                            {
                                "title": "Crawler Evidence",
                                "url": "https://example.test/crawled",
                                "snippet": "Crawled evidence.",
                                "source_type": "web-page",
                            }
                        ],
                    }
                )
            raise AssertionError(request.full_url)

        with patch.dict(os.environ, {"SOURCE_RADAR_FIRECRAWL_ENDPOINT": "https://bridge.test"}, clear=True):
            with patch("source_radar.acquisition.urlopen", side_effect=fake_urlopen):
                report = VerificationAgent(
                    provider=FakeProvider(),
                    acquisition_providers=[
                        FakeSearchProvider(),
                        ExternalBridgeProvider(
                            "firecrawl",
                            env_var="SOURCE_RADAR_FIRECRAWL_ENDPOINT",
                        ),
                    ],
                ).verify("generic product change")

        self.assertEqual(report.agent.planned_tools, ["search", "firecrawl"])
        self.assertEqual(report.agent.acquisition[1].provider, "firecrawl")
        self.assertEqual(report.agent.acquisition[1].status, "ok")
        self.assertEqual(report.evidence[1].adapter, "firecrawl")
        self.assertEqual(report.evidence[1].url, "https://example.test/crawled")


if __name__ == "__main__":
    unittest.main()
