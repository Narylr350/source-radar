import json
import unittest

from source_radar.search_planner import (
    SearchAttempt,
    SearchPlan,
    build_planner_prompt,
    clean_query,
    plan_search,
)


class CleanQueryTests(unittest.TestCase):
    def test_strips_whitespace(self):
        self.assertEqual(clean_query("  hello world  "), "hello world")

    def test_collapses_multiple_spaces(self):
        self.assertEqual(clean_query("hello   world"), "hello world")

    def test_fullwidth_to_halfwidth(self):
        self.assertEqual(clean_query("ｈｅｌｌｏ"), "hello")

    def test_url_decode(self):
        self.assertEqual(clean_query("hello%20world"), "hello world")

    def test_empty_string(self):
        self.assertEqual(clean_query(""), "")

    def test_whitespace_only(self):
        self.assertEqual(clean_query("   "), "")


class SearchAttemptTests(unittest.TestCase):
    def test_defaults(self):
        attempt = SearchAttempt(query="test")
        self.assertEqual(attempt.site, "")
        self.assertEqual(attempt.engine, "bing")
        self.assertEqual(attempt.reason, "")
        self.assertEqual(attempt.platform, "")
        self.assertEqual(attempt.page, 1)

    def test_custom_fields(self):
        attempt = SearchAttempt(
            query="test query",
            site="zhihu.com",
            engine="google",
            reason="community source",
            platform="tieba,bili",
            page=2,
        )
        self.assertEqual(attempt.site, "zhihu.com")
        self.assertEqual(attempt.engine, "google")
        self.assertEqual(attempt.reason, "community source")
        self.assertEqual(attempt.platform, "tieba,bili")
        self.assertEqual(attempt.page, 2)


class SearchPlanTests(unittest.TestCase):
    def test_defaults(self):
        plan = SearchPlan(original_query="test")
        self.assertEqual(plan.attempts, [])
        self.assertEqual(plan.strategy_notes, "")

    def test_with_attempts(self):
        attempt = SearchAttempt(query="q1", site="zhihu.com")
        plan = SearchPlan(original_query="test", attempts=[attempt], strategy_notes="try community")
        self.assertEqual(len(plan.attempts), 1)
        self.assertEqual(plan.strategy_notes, "try community")


class PlanSearchTests(unittest.TestCase):
    def test_valid_json_single_attempt(self):
        llm_response = json.dumps({
            "attempts": [{"query": "Python 异步编程", "site": "", "reason": "general"}],
            "strategy_notes": "broad search",
        })
        plan = plan_search("Python async programming", llm_response=llm_response)
        self.assertEqual(plan.original_query, "Python async programming")
        self.assertEqual(len(plan.attempts), 1)
        self.assertEqual(plan.attempts[0].query, "Python 异步编程")
        self.assertEqual(plan.strategy_notes, "broad search")

    def test_valid_json_multiple_attempts(self):
        llm_response = json.dumps({
            "attempts": [
                {"query": "q1", "site": "zhihu.com", "reason": "community"},
                {"query": "q2", "site": "", "reason": "broad"},
            ],
            "strategy_notes": "try community first",
        })
        plan = plan_search("test query", llm_response=llm_response)
        self.assertEqual(len(plan.attempts), 2)
        self.assertEqual(plan.attempts[0].site, "zhihu.com")
        self.assertEqual(plan.attempts[0].engine, "bing")

    def test_parses_platform_and_page(self):
        llm_response = json.dumps({
            "attempts": [
                {"query": "q1", "site": "", "reason": "r", "platform": "tieba,bili", "page": 2},
                {"query": "q2", "site": "zhihu.com", "reason": "r2"},
            ],
            "strategy_notes": "multi-platform",
        })
        plan = plan_search("test", llm_response=llm_response)
        self.assertEqual(len(plan.attempts), 2)
        self.assertEqual(plan.attempts[0].platform, "tieba,bili")
        self.assertEqual(plan.attempts[0].page, 2)
        self.assertEqual(plan.attempts[1].platform, "")
        self.assertEqual(plan.attempts[1].page, 1)

    def test_invalid_json_fallback(self):
        plan = plan_search("test query", llm_response="not json")
        self.assertEqual(len(plan.attempts), 1)
        self.assertEqual(plan.attempts[0].query, "test query")
        self.assertEqual(plan.attempts[0].site, "")
        self.assertEqual(plan.attempts[0].engine, "bing")
        self.assertIn("fallback", plan.strategy_notes.lower())

    def test_no_response_fallback(self):
        plan = plan_search("  messy  query  ")
        self.assertEqual(len(plan.attempts), 1)
        self.assertEqual(plan.attempts[0].query, "messy query")

    def test_cleans_query_in_fallback(self):
        plan = plan_search("  hello%20world  ")
        self.assertEqual(plan.attempts[0].query, "hello world")


class BuildPlannerPromptTests(unittest.TestCase):
    def test_basic_prompt(self):
        prompt = build_planner_prompt("Python async")
        self.assertIn("Python async", prompt)

    def test_includes_retry_context(self):
        failed = [SearchAttempt(query="q1", site="zhihu.com", reason="no results")]
        top = [{"title": "Result 1", "url": "https://example.com", "snippet": "text"}]
        prompt = build_planner_prompt("test", failed_attempts=failed, top_results=top)
        self.assertIn("q1", prompt)
        self.assertIn("zhihu.com", prompt)
        self.assertIn("Result 1", prompt)

    def test_includes_quality_signals(self):
        prompt = build_planner_prompt("test", quality_signals=["good_source", "recent"])
        self.assertIn("good_source", prompt)
        self.assertIn("recent", prompt)
        self.assertIn("Quality signals", prompt)

    def test_no_quality_signals_omitted(self):
        prompt = build_planner_prompt("test")
        self.assertNotIn("Quality signals", prompt)


class TestSourceHint(unittest.TestCase):
    def test_source_hint_field(self):
        a = SearchAttempt(query="vllm CUDA OOM", source_hint="official+github")
        self.assertEqual(a.source_hint, "official+github")

    def test_source_hint_default_empty(self):
        a = SearchAttempt(query="test")
        self.assertEqual(a.source_hint, "")

    def test_plan_search_parses_source_hint(self):
        response = json.dumps({
            "attempts": [
                {"query": "vllm CUDA OOM", "source_hint": "official+github", "reason": "need docs"},
            ],
            "strategy_notes": "technical error"
        })
        plan = plan_search("vllm报CUDA OOM", llm_response=response)
        self.assertEqual(plan.attempts[0].source_hint, "official+github")

    def test_plan_search_missing_source_hint_defaults_empty(self):
        response = json.dumps({
            "attempts": [{"query": "test", "reason": "r"}],
            "strategy_notes": "s"
        })
        plan = plan_search("test", llm_response=response)
        self.assertEqual(plan.attempts[0].source_hint, "")

    def test_planner_prompt_includes_source_hint(self):
        from source_radar.search_planner import _PLANNER_SYSTEM
        self.assertIn("source_hint", _PLANNER_SYSTEM)
        self.assertIn("official+github", _PLANNER_SYSTEM)
        self.assertIn("authoritative", _PLANNER_SYSTEM)
        self.assertIn("benchmark", _PLANNER_SYSTEM)

    def test_planner_prompt_includes_event_confirmation(self):
        from source_radar.search_planner import _PLANNER_SYSTEM
        self.assertIn("event_confirmation", _PLANNER_SYSTEM)
        self.assertIn("讣告", _PLANNER_SYSTEM)

    def test_planner_prompt_event_confirmation_example(self):
        from source_radar.search_planner import _PLANNER_SYSTEM
        self.assertIn("event_confirmation", _PLANNER_SYSTEM)
        # Should have example with 讣告 query
        self.assertIn("讣告", _PLANNER_SYSTEM)

    def test_planner_prompt_entity_protection(self):
        from source_radar.search_planner import _PLANNER_SYSTEM
        self.assertIn("Exact entity protection", _PLANNER_SYSTEM)


if __name__ == "__main__":
    unittest.main()
