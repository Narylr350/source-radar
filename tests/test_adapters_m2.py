import unittest

from source_radar.adapters import (
    collect_github_repo,
    collect_official_page,
    collect_web_page,
)
from source_radar.evidence import build_evidence_cards
from source_radar.judgement import judge_claim


WEB_HTML = """
<!doctype html>
<html>
  <head><title>Example Web Page</title></head>
  <body>
    <main>
      <h1>Example Web Page</h1>
      <p>Source Radar can extract useful text from normal pages.</p>
    </main>
  </body>
</html>
"""


OFFICIAL_HTML = """
<!doctype html>
<html>
  <head><title>Official Product Update</title></head>
  <body>
    <article>
      <h1>Official Product Update</h1>
      <p>The official announcement says the product changed today.</p>
    </article>
  </body>
</html>
"""


GITHUB_PAYLOAD = {
    "full_name": "openai/source-radar-example",
    "description": "Example repository used by source-radar tests.",
    "html_url": "https://github.com/openai/source-radar-example",
    "stargazers_count": 42,
    "forks_count": 3,
    "pushed_at": "2026-05-23T00:00:00Z",
}


class M2AdapterTests(unittest.TestCase):
    def test_web_page_adapter_extracts_source_item(self):
        items = collect_web_page(
            "https://example.test/page",
            html=WEB_HTML,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].adapter, "web")
        self.assertEqual(items[0].source_type, "web-page")
        self.assertEqual(items[0].title, "Example Web Page")
        self.assertIn("normal pages", items[0].snippet)

    def test_official_adapter_marks_official_source_type(self):
        items = collect_official_page(
            "https://example.test/announcements/product",
            html=OFFICIAL_HTML,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].adapter, "official")
        self.assertEqual(items[0].source_type, "official-announcement")
        self.assertEqual(items[0].title, "Official Product Update")

    def test_github_adapter_extracts_repository_metadata(self):
        items = collect_github_repo(
            "openai/source-radar-example",
            payload=GITHUB_PAYLOAD,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].adapter, "github")
        self.assertEqual(items[0].source_type, "github-repository")
        self.assertEqual(items[0].url, "https://github.com/openai/source-radar-example")
        self.assertIn("stars: 42", items[0].snippet)

    def test_evidence_cards_include_adapter_metadata_and_hash(self):
        cards = build_evidence_cards(
            collect_web_page("https://example.test/page", html=WEB_HTML)
        )

        self.assertEqual(cards[0].adapter, "web")
        self.assertEqual(cards[0].source_type, "web-page")
        self.assertEqual(len(cards[0].content_hash), 64)

    def test_judgement_text_reflects_live_adapter_evidence(self):
        cards = build_evidence_cards(
            collect_web_page("https://example.test/page", html=WEB_HTML)
        )

        judgement = judge_claim("Example Web Page", cards)

        self.assertEqual(judgement.status, "evidence-found")
        self.assertNotIn("Fixture", judgement.summary)
        self.assertIn("web", judgement.summary)

    def test_empty_web_page_preserves_no_evidence_behavior(self):
        cards = build_evidence_cards(
            collect_web_page(
                "https://example.test/empty",
                html="<html><head><title>Empty</title></head><body></body></html>",
            )
        )
        judgement = judge_claim("missing claim", cards)

        self.assertEqual(cards, [])
        self.assertEqual(judgement.status, "no-evidence")
        self.assertEqual(judgement.evidence_ids, [])


if __name__ == "__main__":
    unittest.main()
