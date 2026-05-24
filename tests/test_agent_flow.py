import json
import unittest

from source_radar.acquisition import AcquisitionResult, CandidateSource
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


if __name__ == "__main__":
    unittest.main()
