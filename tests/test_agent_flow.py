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
from source_radar.models import InformationAnalysis, Judgement, SourceItem
from source_radar.reporting import render_markdown, render_synthesis_markdown


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

    def synthesize(self, query, evidence):
        return InformationAnalysis(
            summary=f"综合分析 {query} using {len(evidence)} evidence cards.",
            key_points=[
                f"搜索结果要点来自 {evidence[0].id}." if evidence else "没有可分析来源。"
            ],
            source_notes=[f"来源数量: {len(evidence)}"],
            disagreements=[],
            noise_notes=["搜索结果只作为线索，正文和社区帖权重更高。"],
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


class FakeMediaCrawlerProvider:
    provider = "mediacrawler"
    provider_type = "external-bridge"

    def status(self):
        return AcquisitionResult(
            provider="mediacrawler",
            provider_type="external-bridge",
            status="ok",
            reason="ready",
            message="MediaCrawler bridge is ready.",
            diagnostics={
                "capabilities": "search",
                "contract_version": "source-radar.bridge.v1",
                "platforms": "xiaohongshu,bilibili,weibo,tieba,douyin",
                "ai_guidance": "Use for Chinese community posts, cases, opinions, and troubleshooting.",
            },
        )

    def collect(self, request):
        return AcquisitionResult(
            provider="mediacrawler",
            provider_type="external-bridge",
            status="ok",
            reason="items-found",
            message="MediaCrawler returned community evidence.",
            items=[
                SourceItem(
                    source_type="community-post",
                    title="小红书 AI 工具实测",
                    url="https://example.test/xhs-note",
                    snippet="社区实测案例。",
                    adapter="mediacrawler",
                )
            ],
        )


class FakeTrafilaturaProvider:
    provider = "trafilatura"
    provider_type = "generic-crawler"

    def status(self):
        return AcquisitionResult(
            provider="trafilatura",
            provider_type="generic-crawler",
            status="ok",
            reason="ready",
            message="Trafilatura is ready.",
            diagnostics={"capabilities": "extract", "runtime": "local"},
        )

    def collect(self, request):
        return AcquisitionResult(
            provider="trafilatura",
            provider_type="generic-crawler",
            status="ok",
            reason="items-found",
            message="Trafilatura extracted page evidence.",
            items=[
                SourceItem(
                    source_type="web-page",
                    title="Local extracted evidence",
                    url="https://example.test/local",
                    snippet="Local extraction evidence.",
                    adapter="trafilatura",
                )
            ],
        )


class FakeCrawl4AIProvider:
    provider = "crawl4ai"
    provider_type = "generic-crawler"

    def status(self):
        return AcquisitionResult(
            provider="crawl4ai",
            provider_type="generic-crawler",
            status="ok",
            reason="ready",
            message="Crawl4AI is ready.",
            diagnostics={"capabilities": "render,extract", "runtime": "local-browser"},
        )

    def collect(self, request):
        return AcquisitionResult(
            provider="crawl4ai",
            provider_type="generic-crawler",
            status="ok",
            reason="items-found",
            message="Crawl4AI rendered page evidence.",
            items=[
                SourceItem(
                    source_type="web-page",
                    title="Rendered evidence",
                    url="https://example.test/rendered",
                    snippet="Rendered extraction evidence.",
                    adapter="crawl4ai",
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

    def test_agent_auto_invokes_local_generic_crawlers_before_firecrawl(self):
        report = VerificationAgent(
            provider=FakeProvider(),
            acquisition_providers=[
                FakeSearchProvider(),
                FakeBridgeProvider(),
                FakeTrafilaturaProvider(),
                FakeCrawl4AIProvider(),
            ],
        ).verify("generic product change")

        self.assertEqual(
            report.agent.planned_tools,
            ["search", "trafilatura", "crawl4ai", "firecrawl"],
        )
        self.assertEqual(report.evidence[1].adapter, "trafilatura")
        self.assertEqual(report.evidence[2].adapter, "crawl4ai")

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

    def test_agent_uses_mediacrawler_bridge_contract_end_to_end(self):
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
            if request.full_url == "https://mediacrawler.test/manifest":
                return Response(
                    {
                        "provider": "mediacrawler",
                        "contract_version": "source-radar.bridge.v1",
                        "capabilities": [{"name": "search"}],
                        "platforms": ["xiaohongshu", "bilibili", "weibo", "tieba", "douyin"],
                        "ai_guidance": "Use for Chinese community sources.",
                    }
                )
            if request.full_url == "https://mediacrawler.test/health":
                return Response(
                    {
                        "status": "ok",
                        "reason": "ready",
                        "message": "MediaCrawler bridge is ready.",
                    }
                )
            if request.full_url == "https://mediacrawler.test/collect":
                return Response(
                    {
                        "status": "ok",
                        "reason": "items-found",
                        "message": "MediaCrawler collected community evidence.",
                        "items": [
                            {
                                "title": "社区实测案例",
                                "url": "https://example.test/community",
                                "snippet": "来自中文社区的实测线索。",
                                "source_type": "community-post",
                            }
                        ],
                    }
                )
            raise AssertionError(request.full_url)

        with patch.dict(os.environ, {"SOURCE_RADAR_MEDIACRAWLER_ENDPOINT": "https://mediacrawler.test"}, clear=True):
            with patch("source_radar.acquisition.urlopen", side_effect=fake_urlopen):
                report = VerificationAgent(
                    provider=FakeProvider(),
                    acquisition_providers=[
                        FakeSearchProvider(),
                        ExternalBridgeProvider(
                            "mediacrawler",
                            env_var="SOURCE_RADAR_MEDIACRAWLER_ENDPOINT",
                        ),
                    ],
                ).verify("找小红书 AI 工具实测案例")

        self.assertEqual(report.agent.planned_tools, ["search", "mediacrawler"])
        self.assertEqual(report.agent.acquisition[1].provider, "mediacrawler")
        self.assertEqual(report.evidence[1].adapter, "mediacrawler")
        self.assertEqual(report.evidence[1].source_type, "community-post")

    def test_agent_routes_chinese_community_claim_to_mediacrawler(self):
        report = VerificationAgent(
            provider=FakeProvider(),
            acquisition_providers=[
                FakeSearchProvider(),
                FakeBridgeProvider(),
                FakeMediaCrawlerProvider(),
                FakeTrafilaturaProvider(),
                FakeCrawl4AIProvider(),
            ],
        ).verify("找小红书 AI 工具实测案例")

        self.assertEqual(
            report.agent.planned_tools,
            ["search", "mediacrawler", "crawl4ai", "firecrawl", "trafilatura"],
        )
        self.assertEqual(report.agent.acquisition[1].provider, "mediacrawler")
        self.assertEqual(report.evidence[1].adapter, "mediacrawler")
        self.assertEqual(report.evidence[1].source_type, "community-post")

    def test_agent_routes_generic_claim_to_local_crawlers_before_external_bridges(self):
        report = VerificationAgent(
            provider=FakeProvider(),
            acquisition_providers=[
                FakeSearchProvider(),
                FakeBridgeProvider(),
                FakeMediaCrawlerProvider(),
                FakeTrafilaturaProvider(),
                FakeCrawl4AIProvider(),
            ],
        ).verify("find product documentation and tutorials")

        self.assertEqual(
            report.agent.planned_tools,
            ["search", "trafilatura", "crawl4ai", "firecrawl", "mediacrawler"],
        )

    def test_agent_ask_returns_search_synthesis_report(self):
        report = VerificationAgent(
            provider=FakeProvider(),
            acquisition_providers=[
                FakeSearchProvider(),
                FakeTrafilaturaProvider(),
                FakeCrawl4AIProvider(),
            ],
        ).ask("find product documentation and tutorials")

        self.assertEqual(report.status, "analysis-ready")
        self.assertEqual(report.agent.mode, "analysis")
        self.assertEqual(report.agent.planned_tools, ["search", "trafilatura", "crawl4ai"])
        self.assertIn("综合分析", report.analysis.summary)
        self.assertEqual(report.analysis.disagreements, [])
        self.assertEqual(report.evidence[0].adapter, "search")
        self.assertEqual(report.evidence[1].adapter, "trafilatura")

    def test_synthesis_markdown_focuses_on_search_results_not_evidence_gaps(self):
        report = VerificationAgent(
            provider=FakeProvider(),
            acquisition_providers=[FakeSearchProvider(), FakeTrafilaturaProvider()],
        ).ask("find product documentation and tutorials")

        markdown = render_synthesis_markdown(report)

        self.assertIn("# 综合信息分析", markdown)
        self.assertIn("## 综合回答", markdown)
        self.assertIn("## 搜索结果要点", markdown)
        self.assertIn("## 来源分布", markdown)
        self.assertNotIn("还缺什么", markdown)
        self.assertNotIn("## 简短建议", markdown)


if __name__ == "__main__":
    unittest.main()
