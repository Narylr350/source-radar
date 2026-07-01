"""Test quality assessor doesn't misjudge relevant results as low quality."""
import unittest
from source_radar.acquisition import (
    AcquisitionResult, CandidateSource, _assess_quality,
    _assess_semantic_mismatch, _assess_language, _assess_key_platform_missing,
)


class MethodAnswersMissingTest(unittest.TestCase):
    """method-answers-missing should not independently set score=low."""

    def test_method_intent_with_relevant_docs_not_low(self):
        """Query 'Python asyncio 教程' + official docs results (no tutorial words) should NOT be low."""
        results = [
            {"title": "asyncio --- 异步I/O — Python 3.11 文档", "snippet": "asyncio is a library to write concurrent code using async/await"},
            {"title": "使用asyncio - 廖雪峰", "snippet": "asyncio是Python 3.4版本引入的标准库"},
            {"title": "Python asyncio event loop", "snippet": "coroutine event loop async await"},
            {"title": "asyncio documentation", "snippet": "asyncio provides infrastructure for writing concurrent code"},
            {"title": "Python异步编程", "snippet": "asyncio模块提供了使用协程构建并发应用的工具"},
        ]
        qa = _assess_semantic_mismatch("Python asyncio 教程", results)
        # Even if method-answers-missing fires, score should NOT be low (results are relevant)
        if qa and "method-answers-missing" in (qa.signals or []):
            self.assertNotEqual(qa.score, "low",
                "method-answers-missing alone should not set low when results are semantically relevant")

    def test_method_intent_zero_responses_still_not_independently_low(self):
        """Even with 0 method-response hits, if coverage is good, should not be low."""
        results = [
            {"title": "asyncio coroutine", "snippet": "python asyncio coroutine event loop"},
            {"title": "asyncio task", "snippet": "python asyncio task schedule"},
            {"title": "asyncio gather", "snippet": "python asyncio gather concurrent"},
            {"title": "asyncio sleep", "snippet": "python asyncio sleep coroutine"},
            {"title": "asyncio run", "snippet": "python asyncio run main"},
        ]
        qa = _assess_semantic_mismatch("Python asyncio 教程", results)
        if qa and "method-answers-missing" in (qa.signals or []):
            self.assertNotEqual(qa.score, "low",
                "method-answers-missing with good coverage should not be low")


class LanguageMismatchTest(unittest.TestCase):
    """Chinese tech query returning English official docs should not be language-mismatch."""

    def test_chinese_tech_query_english_docs_not_mismatch(self):
        """'Python asyncio 教程' returning English docs.python.org should not trigger language-mismatch."""
        results = [
            {"title": "asyncio — async IO", "snippet": "asyncio is a library"},
            {"title": "Python asyncio", "snippet": "event loop coroutine"},
            {"title": "asyncio tutorial", "snippet": "concurrent programming"},
            {"title": "async docs", "snippet": "async await python"},
            {"title": "asyncio guide", "snippet": "python 3.11 asyncio"},
        ]
        qa = _assess_language("Python asyncio 教程", results)
        if qa:
            self.assertNotEqual(qa.score, "low",
                "Chinese tech query with English official docs should not be low")


class KeyPlatformMissingTest(unittest.TestCase):
    """'官方'/'声明' in tech context should not trigger news query classification."""

    def test_official_docs_not_news_query(self):
        """'Python 官方文档' should not trigger key-platform-missing."""
        results = [
            {"url": "https://docs.python.org/3/", "title": "Python docs"},
            {"url": "https://docs.python.org/3/library/asyncio.html", "title": "asyncio"},
        ]
        qa = _assess_key_platform_missing("Python 官方文档", results)
        self.assertIsNone(qa, "'官方' in tech context should not trigger news classification")

    def test_type_declaration_not_news_query(self):
        """'TypeScript type 声明' should not trigger key-platform-missing."""
        results = [
            {"url": "https://www.typescriptlang.org/docs/", "title": "TS docs"},
        ]
        qa = _assess_key_platform_missing("TypeScript type 声明", results)
        self.assertIsNone(qa, "'声明' in tech context should not trigger news classification")


if __name__ == "__main__":
    unittest.main()
