"""P2 quality fixes: domain-concentration whitelist + event-confirmation scope."""
import unittest
from source_radar.acquisition import (
    _assess_domain_concentration, _assess_event_confirmation,
)


class DomainConcentrationWhitelistTest(unittest.TestCase):
    """Authoritative doc domains should not trigger domain-concentration."""

    def test_docs_python_org_concentration_not_flagged(self):
        """4 results from docs.python.org should not trigger domain-concentration."""
        results = [
            {"url": "https://docs.python.org/3/library/asyncio.html"},
            {"url": "https://docs.python.org/3/tutorial/index.html"},
            {"url": "https://docs.python.org/3/reference/index.html"},
            {"url": "https://docs.python.org/3/howto/index.html"},
            {"url": "https://example.com/other"},
        ]
        qa = _assess_domain_concentration(results)
        self.assertIsNone(qa, "Authoritative doc domain concentration should not be flagged")

    def test_stackoverflow_concentration_not_flagged(self):
        """4 results from stackoverflow.com should not trigger domain-concentration."""
        results = [
            {"url": "https://stackoverflow.com/questions/1"},
            {"url": "https://stackoverflow.com/questions/2"},
            {"url": "https://stackoverflow.com/questions/3"},
            {"url": "https://stackoverflow.com/questions/4"},
            {"url": "https://example.com/other"},
        ]
        qa = _assess_domain_concentration(results)
        self.assertIsNone(qa, "Stack Overflow concentration should not be flagged")

    def test_low_quality_domain_still_flagged(self):
        """4 results from a random ad site should still trigger domain-concentration."""
        results = [
            {"url": "https://random-ads.example.com/page1"},
            {"url": "https://random-ads.example.com/page2"},
            {"url": "https://random-ads.example.com/page3"},
            {"url": "https://random-ads.example.com/page4"},
            {"url": "https://other.com/page"},
        ]
        qa = _assess_domain_concentration(results)
        self.assertIsNotNone(qa, "Non-authoritative domain concentration should still be flagged")
        self.assertIn("domain-concentration", qa.signals)


class EventConfirmationScopeTest(unittest.TestCase):
    """'怎么了' should only trigger event check with a person name, not for tech queries."""

    def test_python_怎么了_not_event_query(self):
        """'Python 怎么了' should not trigger event-confirmation (no person entity)."""
        results = [
            {"title": "Python 4.0 roadmap", "snippet": "future of Python"},
            {"title": "Python news", "snippet": "latest updates"},
        ]
        qa = _assess_event_confirmation("Python 怎么了", results)
        self.assertIsNone(qa, "'怎么了' without person entity should not trigger event check")

    def test_person_怎么了_still_event_query(self):
        """'张雪峰 怎么了' should still trigger event-confirmation."""
        results = [
            {"title": "张雪峰近况", "snippet": "最新动态"},
        ]
        qa = _assess_event_confirmation("张雪峰 怎么了", results)
        self.assertIsNotNone(qa, "'怎么了' with person name should trigger event check")


if __name__ == "__main__":
    unittest.main()
