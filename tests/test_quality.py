import unittest

from source_radar.models import AcquisitionTrace, QualityAssessment
from source_radar.acquisition import AcquisitionResult


class TestQualityAssessment(unittest.TestCase):
    def test_fields(self):
        qa = QualityAssessment(
            score="high",
            signals=["official-source", "recent"],
            reason="Authoritative source with recent data.",
            suggestions=[],
        )
        self.assertEqual(qa.score, "high")
        self.assertEqual(qa.signals, ["official-source", "recent"])
        self.assertIn("Authoritative", qa.reason)
        self.assertEqual(qa.suggestions, [])

    def test_frozen(self):
        qa = QualityAssessment(
            score="low",
            signals=["stale"],
            reason="Old content.",
            suggestions=["Find newer source."],
        )
        with self.assertRaises(AttributeError):
            qa.score = "high"  # type: ignore[misc]

    def test_ordering_low_medium_high(self):
        self.assertLess(
            QualityAssessment(score="low", signals=[], reason="", suggestions=[]),
            QualityAssessment(score="medium", signals=[], reason="", suggestions=[]),
        )
        self.assertLess(
            QualityAssessment(score="medium", signals=[], reason="", suggestions=[]),
            QualityAssessment(score="high", signals=[], reason="", suggestions=[]),
        )


class TestAcquisitionResultQuality(unittest.TestCase):
    def test_default_none(self):
        result = AcquisitionResult(
            provider="test",
            provider_type="builtin-adapter",
            status="ok",
            reason="items-found",
            message="ok",
        )
        self.assertIsNone(result.quality)

    def test_set_quality(self):
        qa = QualityAssessment(
            score="medium",
            signals=["community-source"],
            reason="Community forum.",
            suggestions=["Cross-check with official docs."],
        )
        result = AcquisitionResult(
            provider="test",
            provider_type="builtin-adapter",
            status="ok",
            reason="items-found",
            message="ok",
            quality=qa,
        )
        self.assertEqual(result.quality.score, "medium")


class TestAcquisitionTraceQuality(unittest.TestCase):
    def test_default_none(self):
        trace = AcquisitionTrace(
            provider="test",
            provider_type="builtin-adapter",
            status="ok",
            reason="items-found",
            message="ok",
        )
        self.assertIsNone(trace.quality)

    def test_set_quality(self):
        qa = QualityAssessment(
            score="low",
            signals=["unverified"],
            reason="No corroboration.",
            suggestions=["Find additional sources."],
        )
        trace = AcquisitionTrace(
            provider="test",
            provider_type="builtin-adapter",
            status="ok",
            reason="items-found",
            message="ok",
            quality=qa,
        )
        self.assertEqual(trace.quality.score, "low")


if __name__ == "__main__":
    unittest.main()
