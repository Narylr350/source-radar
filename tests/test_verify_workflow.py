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

        self.assertIn("# Verification Report", rendered)
        self.assertIn("ev-001", rendered)
        self.assertIn("Summary judgement.", rendered)


if __name__ == "__main__":
    unittest.main()
