import json
import unittest

from source_radar.adapters import collect_fixture_items
from source_radar.evidence import build_evidence_cards
from source_radar.judgement import judge_claim
from source_radar.models import EvidenceCard, Judgement, VerifyReport
from source_radar.reporting import render_json, render_markdown


class VerifyWorkflowTests(unittest.TestCase):
    def test_fixture_claim_builds_evidence_cards(self):
        items = collect_fixture_items("source-radar 是本地 CLI")
        cards = build_evidence_cards(items)
        judgement = judge_claim("source-radar 是本地 CLI", cards)

        self.assertEqual([card.id for card in cards], ["ev-001"])
        self.assertEqual(cards[0].title, "source-radar project README")
        self.assertEqual(judgement.status, "evidence-found")
        self.assertEqual(judgement.evidence_ids, ["ev-001"])

    def test_unknown_claim_returns_no_evidence(self):
        items = collect_fixture_items("完全未知的断言")
        cards = build_evidence_cards(items)
        judgement = judge_claim("完全未知的断言", cards)

        self.assertEqual(cards, [])
        self.assertEqual(judgement.status, "no-evidence")
        self.assertEqual(judgement.evidence_ids, [])

    def test_render_json_is_machine_readable(self):
        report = VerifyReport(
            claim="claim",
            status="evidence-found",
            evidence=[
                EvidenceCard(
                    id="ev-001",
                    source_type="project-doc",
                    title="Title",
                    url="local://README.md",
                    summary="Summary",
                )
            ],
            judgement=Judgement(
                status="evidence-found",
                summary="Summary judgement.",
                evidence_ids=["ev-001"],
                gaps=["Gap"],
            ),
        )

        rendered = json.loads(render_json(report))

        self.assertEqual(rendered["claim"], "claim")
        self.assertEqual(rendered["evidence"][0]["id"], "ev-001")
        self.assertEqual(rendered["judgement"]["evidence_ids"], ["ev-001"])
        self.assertEqual(rendered["judgement"]["confidence"], "unknown")

    def test_render_markdown_includes_evidence_ids(self):
        report = VerifyReport(
            claim="claim",
            status="evidence-found",
            evidence=[
                EvidenceCard(
                    id="ev-001",
                    source_type="project-doc",
                    title="Title",
                    url="local://README.md",
                    summary="Summary",
                )
            ],
            judgement=Judgement(
                status="evidence-found",
                summary="Summary judgement.",
                evidence_ids=["ev-001"],
                gaps=["Gap"],
            ),
        )

        rendered = render_markdown(report)

        self.assertIn("# 核验报告", rendered)
        self.assertIn("ev-001", rendered)
        self.assertIn("Summary judgement.", rendered)
        self.assertIn("## 可信度", rendered)
        self.assertIn("摘要: Summary", rendered)

    def test_current_exam_claim_without_official_source_is_low_confidence(self):
        cards = [
            EvidenceCard(
                id="ev-001",
                source_type="web-page",
                title="问答页面",
                url="https://example.test/question",
                summary="有人说新高考不学微积分。",
                adapter="trafilatura",
            )
        ]

        judgement = judge_claim("今年高考考微积分吗", cards)

        self.assertEqual(judgement.confidence, "low")
        self.assertIn("官方", judgement.confidence_reason)

    def test_public_figure_death_claim_without_first_party_source_is_low_confidence(self):
        cards = [
            EvidenceCard(
                id="ev-001",
                source_type="web-page",
                title="媒体报道一",
                url="https://news.example.test/a",
                summary="报道称某公众人物去世，但没有贴出一手确认来源。",
                adapter="trafilatura",
            ),
            EvidenceCard(
                id="ev-002",
                source_type="web-page",
                title="自媒体转载",
                url="https://content.example.test/b",
                summary="转载称该公众人物因突发疾病去世。",
                adapter="crawl4ai",
            ),
            EvidenceCard(
                id="ev-003",
                source_type="web-page",
                title="百科页面",
                url="https://zh.wikipedia.org/wiki/person",
                summary="百科页面写有逝世日期。",
                adapter="trafilatura",
            ),
        ]

        judgement = judge_claim("张雪峰死了吗", cards)

        self.assertEqual(judgement.confidence, "low")
        self.assertIn("人物生死", judgement.confidence_reason)

    def test_public_figure_death_claim_with_first_party_obituary_is_high_confidence(self):
        cards = [
            EvidenceCard(
                id="ev-001",
                source_type="community-post",
                title="张雪峰老师官方账号讣告",
                url="https://weibo.com/status/1",
                summary="张雪峰老师官方账号发布讣告，确认因心源性猝死抢救无效去世。",
                adapter="mediacrawler",
                metadata={"platform": "weibo", "author": "张雪峰老师"},
            ),
            EvidenceCard(
                id="ev-002",
                source_type="web-page",
                title="主流媒体报道",
                url="https://news.example.test/a",
                summary="报道称张雪峰老师官方账号发布讣告。",
                adapter="trafilatura",
            ),
        ]

        judgement = judge_claim("张雪峰死了吗", cards)

        self.assertEqual(judgement.confidence, "high")
        self.assertIn("一手", judgement.confidence_reason)


if __name__ == "__main__":
    unittest.main()
