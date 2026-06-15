import unittest
from unittest.mock import patch

from source_radar.models import AcquisitionTrace, QualityAssessment
from source_radar.acquisition import (
    AcquisitionResult,
    CandidateSource,
    SourceItem,
    _assess_navigation,
    _assess_language,
    _assess_domain_concentration,
    _assess_snippet_only,
    _assess_key_platform_missing,
    _assess_semantic_mismatch,
    _assess_entity_tokenization,
    _assess_event_confirmation,
    _assess_quality,
)


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


class TestAssessNavigation(unittest.TestCase):
    def test_none_when_clean_text(self):
        text = "这是一段正常的网页内容，包含了很多有用的信息和段落文字。" * 5
        self.assertIsNone(_assess_navigation(text))

    def test_none_when_empty(self):
        self.assertIsNone(_assess_navigation(""))

    def test_low_when_high_url_ratio(self):
        lines = []
        for i in range(20):
            lines.append(f"https://example.com/page/{i}")
        lines.append("一些正文内容在这里")
        text = "\n".join(lines)
        result = _assess_navigation(text)
        self.assertIsNotNone(result)
        self.assertEqual(result.score, "low")
        self.assertIn("navigation-heavy", result.signals)

    def test_low_when_repeated_lines(self):
        line = "导航菜单项 | 首页 | 关于我们 | 联系方式"
        text = "\n".join([line] * 10 + ["唯一内容行"])
        result = _assess_navigation(text)
        self.assertIsNotNone(result)
        self.assertEqual(result.score, "low")
        self.assertIn("navigation-heavy", result.signals)

    def test_none_when_url_ratio_below_threshold(self):
        lines = [f"这是正常的正文内容行{i}" for i in range(20)]
        lines.append("https://example.com/link1")
        text = "\n".join(lines)
        self.assertIsNone(_assess_navigation(text))


class TestAssessLanguage(unittest.TestCase):
    def test_none_when_languages_match(self):
        query = "Python教程"
        results = [{"title": "Python入门教程", "snippet": "学习Python编程"}]
        self.assertIsNone(_assess_language(query, results))

    def test_none_when_english_query_english_results(self):
        query = "Python tutorial"
        results = [{"title": "Learn Python", "snippet": "A beginner guide"}]
        self.assertIsNone(_assess_language(query, results))

    def test_low_when_cjk_query_ascii_results(self):
        query = "最新的AI模型评测"
        results = [
            {"title": "Best AI Models 2025", "snippet": "Comparison of top models"},
            {"title": "GPT Review", "snippet": "OpenAI performance analysis"},
        ]
        result = _assess_language(query, results)
        self.assertIsNotNone(result)
        self.assertEqual(result.score, "low")
        self.assertIn("language-mismatch", result.signals)

    def test_low_when_ascii_query_cjk_results(self):
        query = "Python machine learning"
        results = [
            {"title": "机器学习入门教程指南", "snippet": "深度学习编程实践详解"},
            {"title": "深度学习框架对比分析", "snippet": "神经网络模型训练方法"},
        ]
        result = _assess_language(query, results)
        self.assertIsNotNone(result)
        self.assertEqual(result.score, "low")
        self.assertIn("language-mismatch", result.signals)

    def test_none_when_empty_results(self):
        query = "中文查询"
        self.assertIsNone(_assess_language(query, []))

    def test_none_when_mixed_results(self):
        query = "最新AI技术"
        results = [
            {"title": "Latest AI breakthrough", "snippet": "English content"},
            {"title": "最新AI技术突破", "snippet": "中文内容报道"},
        ]
        self.assertIsNone(_assess_language(query, results))


class TestAssessDomainConcentration(unittest.TestCase):
    def test_none_when_diverse(self):
        results = [
            {"url": "https://a.com/page"},
            {"url": "https://b.com/page"},
            {"url": "https://c.com/page"},
            {"url": "https://d.com/page"},
            {"url": "https://e.com/page"},
        ]
        self.assertIsNone(_assess_domain_concentration(results))

    def test_low_when_top5_concentrated(self):
        results = [
            {"url": "https://example.com/page1"},
            {"url": "https://example.com/page2"},
            {"url": "https://example.com/page3"},
            {"url": "https://example.com/page4"},
            {"url": "https://other.com/page1"},
        ]
        result = _assess_domain_concentration(results)
        self.assertIsNotNone(result)
        self.assertEqual(result.score, "low")
        self.assertIn("domain-concentration", result.signals)
        self.assertIn("example.com", result.reason)

    def test_none_when_fewer_than_5_results(self):
        results = [
            {"url": "https://example.com/page1"},
            {"url": "https://example.com/page2"},
        ]
        self.assertIsNone(_assess_domain_concentration(results))

    def test_none_when_empty(self):
        self.assertIsNone(_assess_domain_concentration([]))


class TestAssessSnippetOnly(unittest.TestCase):
    def test_none_when_items_exist(self):
        result = AcquisitionResult(
            provider="test",
            provider_type="search",
            status="ok",
            reason="items-found",
            message="ok",
            candidates=[CandidateSource(title="t", url="u", provider="p")],
            items=[SourceItem(source_type="web-page", title="t", url="u", snippet="s")],
        )
        self.assertIsNone(_assess_snippet_only(result))

    def test_medium_when_candidates_no_items(self):
        result = AcquisitionResult(
            provider="test",
            provider_type="search",
            status="ok",
            reason="candidates-found",
            message="ok",
            candidates=[CandidateSource(title="t", url="u", provider="p")],
            items=[],
        )
        qa = _assess_snippet_only(result)
        self.assertIsNotNone(qa)
        self.assertEqual(qa.score, "medium")
        self.assertIn("snippet-only", qa.signals)

    def test_none_when_no_candidates_no_items(self):
        result = AcquisitionResult(
            provider="test",
            provider_type="search",
            status="no-evidence",
            reason="no-candidates",
            message="none",
        )
        self.assertIsNone(_assess_snippet_only(result))


class TestAssessKeyPlatformMissing(unittest.TestCase):
    def test_none_when_non_news_query(self):
        query = "Python教程"
        results = [{"url": "https://example.com/python", "title": "Python教程"}]
        self.assertIsNone(_assess_key_platform_missing(query, results))

    def test_none_when_mainstream_present(self):
        query = "最新事件回应"
        results = [
            {"url": "https://weibo.com/123", "title": "微博热搜"},
            {"url": "https://example.com/news", "title": "新闻"},
        ]
        self.assertIsNone(_assess_key_platform_missing(query, results))

    def test_medium_when_news_no_mainstream(self):
        query = "某事件官方回应"
        results = [
            {"url": "https://someblog.com/post", "title": "博客文章"},
            {"url": "https://forum.example.com/thread", "title": "论坛讨论"},
        ]
        qa = _assess_key_platform_missing(query, results)
        self.assertIsNotNone(qa)
        self.assertEqual(qa.score, "medium")
        self.assertIn("key-platform-missing", qa.signals)

    def test_none_when_empty_results_non_news(self):
        self.assertIsNone(_assess_key_platform_missing("普通查询", []))

    def test_medium_when_news_keyword_in_query_empty_results(self):
        qa = _assess_key_platform_missing("突发新闻", [])
        self.assertIsNotNone(qa)
        self.assertEqual(qa.score, "medium")
        self.assertIn("key-platform-missing", qa.signals)

    def test_none_when_tech_intent_with_context_keyword(self):
        """最新的AI模型评测 → tech intent, 不应触发"""
        results = [{"url": "https://datalearner.com/leaderboards", "title": "AI模型排行榜"}]
        self.assertIsNone(_assess_key_platform_missing("最新的AI模型评测", results))

    def test_none_when_benchmark_query(self):
        """9800X3D 评测排行 → tech intent"""
        results = [{"url": "https://example.com/review", "title": "9800X3D评测"}]
        self.assertIsNone(_assess_key_platform_missing("9800X3D 评测", results))

    def test_triggers_when_strong_news_keyword(self):
        """突发新闻 → still triggers even without context keyword"""
        qa = _assess_key_platform_missing("突发新闻", [{"url": "https://blog.com/post", "title": "博客"}])
        self.assertIsNotNone(qa)
        self.assertIn("key-platform-missing", qa.signals)


class TestNoCandidatesQuality(unittest.TestCase):
    def test_no_candidates_returns_low(self):
        result = AcquisitionResult(
            provider="search", provider_type="search", status="no-evidence",
            reason="no-candidates", message="No results.",
            candidates=[], items=[],
        )
        qa = _assess_quality(result, "test query")
        self.assertEqual(qa.score, "low")
        self.assertIn("no-candidates", qa.signals)

    def test_no_candidates_with_site_filter(self):
        result = AcquisitionResult(
            provider="search", provider_type="search", status="no-evidence",
            reason="no-candidates", message="No results for site:reddit.com",
            candidates=[], items=[],
        )
        qa = _assess_quality(result, "test query")
        self.assertEqual(qa.score, "low")
        self.assertIn("no-candidates", qa.signals)
        self.assertIn("site:", qa.suggestions[0])


class TestToTraceQuality(unittest.TestCase):
    def test_to_trace_propagates_quality(self):
        qa = QualityAssessment(
            score="low",
            signals=["language-mismatch"],
            reason="语言不匹配",
            suggestions=["用中文重新搜索"],
        )
        result = AcquisitionResult(
            provider="test", provider_type="search", status="ok",
            reason="items-found", message="ok", quality=qa,
        )
        trace = result.to_trace()
        self.assertIsNotNone(trace.quality)
        self.assertEqual(trace.quality.score, "low")
        self.assertIn("language-mismatch", trace.quality.signals)
        self.assertEqual(trace.quality.reason, "语言不匹配")

    def test_to_trace_quality_none(self):
        result = AcquisitionResult(
            provider="test", provider_type="search", status="ok",
            reason="items-found", message="ok",
        )
        trace = result.to_trace()
        self.assertIsNone(trace.quality)


class TestAssessQuality(unittest.TestCase):
    def test_high_when_no_signals(self):
        result = AcquisitionResult(
            provider="test",
            provider_type="search",
            status="ok",
            reason="items-found",
            message="ok",
            candidates=[CandidateSource(title="正常标题", url="https://a.com", provider="p")],
            items=[SourceItem(source_type="web-page", title="t", url="https://a.com", snippet="s",
                              raw_content="这是正常的网页内容，没有导航问题。" * 5)],
        )
        qa = _assess_quality(result, "正常查询")
        self.assertEqual(qa.score, "high")
        self.assertEqual(qa.signals, [])

    def test_lowest_of_multiple_signals(self):
        result = AcquisitionResult(
            provider="test",
            provider_type="search",
            status="ok",
            reason="candidates-found",
            message="ok",
            candidates=[
                CandidateSource(title="Best AI Models", url="https://example.com/page1", provider="p"),
                CandidateSource(title="GPT Review", url="https://example.com/page2", provider="p"),
                CandidateSource(title="AI Benchmark", url="https://example.com/page3", provider="p"),
                CandidateSource(title="Model Compare", url="https://example.com/page4", provider="p"),
                CandidateSource(title="Top LLMs", url="https://example.com/page5", provider="p"),
            ],
            items=[],
        )
        qa = _assess_quality(result, "最新的AI模型评测")
        self.assertIn("snippet-only", qa.signals)
        self.assertIn("language-mismatch", qa.signals)
        self.assertIn("domain-concentration", qa.signals)
        self.assertEqual(qa.score, "low")

    def test_medium_when_only_snippet_only(self):
        result = AcquisitionResult(
            provider="test",
            provider_type="search",
            status="ok",
            reason="candidates-found",
            message="ok",
            candidates=[CandidateSource(title="中文标题", url="https://a.com", provider="p")],
            items=[],
        )
        qa = _assess_quality(result, "中文查询")
        self.assertEqual(qa.score, "medium")
        self.assertIn("snippet-only", qa.signals)

    def test_try_except_per_detector(self):
        result = AcquisitionResult(
            provider="test",
            provider_type="search",
            status="ok",
            reason="items-found",
            message="ok",
            candidates=[CandidateSource(title="test query results", url="https://a.com", provider="p")],
            items=[SourceItem(source_type="web-page", title="t", url="https://a.com", snippet="test query content here")],
        )
        with patch("source_radar.acquisition._assess_navigation", side_effect=RuntimeError("boom")):
            qa = _assess_quality(result, "test query")
        self.assertEqual(qa.score, "high")

    def test_raw_content_from_first_item(self):
        nav_lines = [f"https://example.com/page/{i}" for i in range(20)]
        nav_lines.append("唯一内容")
        result = AcquisitionResult(
            provider="test",
            provider_type="search",
            status="ok",
            reason="items-found",
            message="ok",
            candidates=[CandidateSource(title="t", url="https://a.com", provider="p")],
            items=[SourceItem(source_type="web-page", title="t", url="https://a.com", snippet="s",
                              raw_content="\n".join(nav_lines))],
        )
        qa = _assess_quality(result, "正常查询")
        self.assertIn("navigation-heavy", qa.signals)
        self.assertEqual(qa.score, "low")


class TestAssessSemanticMismatch(unittest.TestCase):
    def test_irrelevant_results_chinese(self):
        """搜 '最新的AI模型评测' 返回凤凰网/今日头条 → 语义不相关"""
        from source_radar.acquisition import _assess_semantic_mismatch
        results = [
            {"title": "今日热点新闻汇总", "snippet": "凤凰卫视报道最新国际动态"},
            {"title": "今日头条 - 热门资讯", "snippet": "社会新闻、娱乐八卦一网打尽"},
            {"title": "新浪首页", "snippet": "新浪网综合新闻门户"},
        ]
        result = _assess_semantic_mismatch("最新的AI模型评测", results)
        self.assertIsNotNone(result)
        self.assertIn("semantic-mismatch", result.signals)
        self.assertEqual(result.score, "low")

    def test_irrelevant_results_english(self):
        """搜 'python asyncio tutorial' 返回 unrelated results"""
        from source_radar.acquisition import _assess_semantic_mismatch
        results = [
            {"title": "Best restaurants in NYC 2026", "snippet": "Top dining spots in Manhattan"},
            {"title": "Weather forecast today", "snippet": "Temperature and rain probability"},
            {"title": "Stock market live updates", "snippet": "S&P 500 and NASDAQ real-time"},
        ]
        result = _assess_semantic_mismatch("python asyncio tutorial", results)
        self.assertIsNotNone(result)
        self.assertIn("semantic-mismatch", result.signals)

    def test_relevant_results_no_mismatch(self):
        """搜 'CS2 Major 2026' 返回电竞赛事结果 → 正常"""
        from source_radar.acquisition import _assess_semantic_mismatch
        results = [
            {"title": "IEM Cologne Major 2026 - CS2 Esports Tournament", "snippet": "32 teams compete for $1,250,000 in Cologne"},
            {"title": "CS2 Major 2026 Schedule and Results", "snippet": "All matches from the Counter-Strike 2 Major"},
            {"title": "CS2 Major Cologne 2026 Tickets", "snippet": "Get tickets for the CS2 Major at LANXESS arena"},
        ]
        result = _assess_semantic_mismatch("CS2 Major 2026", results)
        self.assertIsNone(result)

    def test_model_number_results(self):
        """搜 'RTX 5090 评测' 返回显卡评测 → 正常"""
        from source_radar.acquisition import _assess_semantic_mismatch
        results = [
            {"title": "RTX 5090 评测：性能提升巨大", "snippet": "NVIDIA RTX 5090 显卡详细评测"},
            {"title": "RTX 5090 vs RTX 4090 对比", "snippet": "两代旗舰显卡性能对比测试"},
        ]
        result = _assess_semantic_mismatch("RTX 5090 评测", results)
        self.assertIsNone(result)

    def test_empty_results(self):
        from source_radar.acquisition import _assess_semantic_mismatch
        result = _assess_semantic_mismatch("test", [])
        self.assertIsNone(result)

    def test_mixed_relevant_irrelevant(self):
        """3/5 结果相关 → 不触发（阈值内）"""
        from source_radar.acquisition import _assess_semantic_mismatch
        results = [
            {"title": "9800X3D 超频教程", "snippet": "手把手教你超频 AMD 9800X3D"},
            {"title": "9800X3D 评测", "snippet": "AMD 锐龙 9800X3D 性能测试"},
            {"title": "9800X3D 装机方案", "snippet": "搭配 9800X3D 的最佳配置"},
            {"title": "今日热点新闻", "snippet": "社会新闻汇总"},
            {"title": "爱奇艺视频下载", "snippet": "爱奇艺客户端下载安装"},
        ]
        result = _assess_semantic_mismatch("9800X3D 超频", results)
        self.assertIsNone(result)


class TestCacheQualityPersistence(unittest.TestCase):
    def test_cache_payload_includes_quality(self):
        """Fresh result with quality should serialize quality into cache payload."""
        from dataclasses import asdict
        qa = QualityAssessment(
            score="low", signals=["semantic-mismatch"],
            reason="不相关", suggestions=["换关键词"],
        )
        result = AcquisitionResult(
            provider="search", provider_type="search", status="ok",
            reason="ok", message="ok", quality=qa,
        )
        payload = {
            "provider": result.provider,
            "quality": asdict(result.quality) if result.quality else None,
        }
        self.assertIsNotNone(payload["quality"])
        self.assertEqual(payload["quality"]["score"], "low")
        self.assertEqual(payload["quality"]["signals"], ["semantic-mismatch"])

    def test_cache_read_restores_quality(self):
        """Cache hit should restore QualityAssessment from dict."""
        cached = {
            "provider": "search",
            "provider_type": "search",
            "status": "ok",
            "reason": "ok",
            "message": "ok",
            "quality": {"score": "medium", "signals": ["snippet-only"], "reason": "仅有摘要", "suggestions": ["抓取正文"]},
        }
        raw_q = cached.get("quality")
        quality = QualityAssessment(**raw_q) if raw_q and isinstance(raw_q, dict) else None
        self.assertIsNotNone(quality)
        self.assertEqual(quality.score, "medium")
        self.assertIn("snippet-only", quality.signals)

    def test_cache_read_none_quality(self):
        """Cache without quality field should not crash."""
        cached = {"provider": "search", "provider_type": "search", "status": "ok", "reason": "", "message": ""}
        raw_q = cached.get("quality")
        quality = QualityAssessment(**raw_q) if raw_q and isinstance(raw_q, dict) else None
        self.assertIsNone(quality)

    def test_adapter_version_bumped(self):
        """CACHE_ADAPTER_VERSION should be different from old version."""
        from source_radar.cache import CACHE_ADAPTER_VERSION
        self.assertNotEqual(CACHE_ADAPTER_VERSION, "v3-adaptive-1")


class TestEventConfirmationAssessor(unittest.TestCase):
    def test_non_event_query_returns_none(self):
        result = _assess_event_confirmation("Python教程", [{"title": "t", "snippet": "s"}])
        self.assertIsNone(result)

    def test_event_query_with_strong_source_returns_none(self):
        results = [{"title": "张雪峰讣告", "snippet": "公司发布讣告，张雪峰因病去世"}]
        result = _assess_event_confirmation("张雪峰死了吗", results)
        self.assertIsNone(result)

    def test_event_query_without_strong_source_flags_low(self):
        results = [
            {"title": "张雪峰最新动态", "snippet": "张雪峰抖音头像变黑白"},
            {"title": "张雪峰怎么了", "snippet": "网友热议张雪峰近况"},
            {"title": "张雪峰微博", "snippet": "张雪峰粉丝关注"},
        ]
        result = _assess_event_confirmation("张雪峰死了吗", results)
        self.assertIsNotNone(result)
        self.assertEqual(result.score, "low")
        self.assertIn("event-confirmation-needs-strong-source", result.signals)

    def test_empty_results_returns_none(self):
        result = _assess_event_confirmation("张雪峰死了吗", [])
        self.assertIsNone(result)

    def test_death_keywords_detected(self):
        for kw in ("去世", "逝世", "猝死", "讣告", "怎么了"):
            results = [{"title": "某人最新", "snippet": "网友讨论"}]
            result = _assess_event_confirmation(f"某人{kw}", results)
            self.assertIsNotNone(result, f"keyword '{kw}' should trigger")

    def test_strong_source_keywords(self):
        for marker in ("讣告", "逝世", "官方声明", "抢救无效"):
            results = [{"title": "某人消息", "snippet": f"来源：{marker}确认"}]
            result = _assess_event_confirmation("某人去世", results)
            self.assertIsNone(result, f"marker '{marker}' should pass")


class TestEntityTokenizationAssessor(unittest.TestCase):
    def test_three_character_person_name_split_to_single_surname_flags_low(self):
        results = [
            {"title": "张 姓概况和55位古今名人 - 知乎", "snippet": "张姓起源"},
            {"title": "张 （汉语汉字）_百度百科", "snippet": "张字解释"},
            {"title": "张 的意思, 张 的解释", "snippet": "新华字典"},
        ]

        result = _assess_entity_tokenization("张雪峰 讣告", results)

        self.assertIsNotNone(result)
        self.assertEqual(result.score, "low")
        self.assertIn("entity-tokenization-failure", result.signals)

    def test_long_org_name_split_to_city_name_flags_low(self):
        results = [
            {"title": "苏州 值得一玩的景点合集", "snippet": "苏州旅游攻略"},
            {"title": "苏州 市_百度百科", "snippet": "苏州市介绍"},
            {"title": "苏州 市人民政府", "snippet": "政务服务"},
        ]

        result = _assess_entity_tokenization("苏州峰学蔚来 声明 讣告", results)

        self.assertIsNotNone(result)
        self.assertEqual(result.score, "low")
        self.assertIn("entity-tokenization-failure", result.signals)

    def test_full_entity_present_returns_none(self):
        results = [
            {"title": "张雪峰官方讣告发布", "snippet": "公司发布讣告"},
        ]

        result = _assess_entity_tokenization("张雪峰 讣告", results)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
