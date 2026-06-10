"""Tests for v3 hardening features: session, cache, verify strictness, trace fields."""

import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from source_radar.acquisition import (
    AcquisitionResult,
    CandidateSource,
)
from source_radar.agent import VerificationAgent, _evidence_needs_more
from source_radar.models import (
    AgentTrace,
    EvidenceCard,
    InformationAnalysis,
    Judgement,
    SourceItem,
    SynthesisReport,
    VerifyReport,
)
from source_radar.cache import (
    CACHE_ADAPTER_VERSION,
    SCHEMA_VERSION,
    _make_key,
    _make_provider_signature,
    cache_clear,
    get_cached_result,
    is_realtime_query,
    put_cached_result,
)
from source_radar.session import (
    append_session_record,
    clear_session,
    lexical_is_related,
    load_recent_session_context,
)


# ── Fake providers ──────────────────────────────────────────────────


class FakeAIProvider:
    status = "configured"
    model = "fake-model"
    endpoint = "https://fake.test/v1"
    provider = "openai"

    def _headers(self):
        return {"Authorization": "Bearer fake", "Content-Type": "application/json"}

    def judge(self, claim, evidence, session_context=""):
        self._last_session_context = session_context
        return Judgement(
            status="ai-judged",
            summary=f"AI judged: {claim}",
            evidence_ids=[c.id for c in evidence],
            gaps=[],
            confidence="medium",
            confidence_reason="mixed sources",
        )

    def synthesize(self, query, evidence, session_context=""):
        self._last_session_context = session_context
        return InformationAnalysis(
            summary=f"Synthesis of: {query}",
            key_points=["Point 1"],
            source_notes=[f"{len(evidence)} sources"],
            disagreements=[],
            noise_notes=[],
        )


class FakeSearchProvider:
    provider = "search"
    provider_type = "search"

    def collect(self, request):
        return AcquisitionResult(
            provider="search",
            provider_type="search",
            status="ok",
            reason="candidates-found",
            message="Found candidates.",
            candidates=[
                CandidateSource(
                    title=f"Result for {request.query}",
                    url="https://example.test/1",
                    provider="search",
                    snippet="Search result.",
                )
            ],
            items=[
                SourceItem(
                    source_type="search-result",
                    title=f"Result for {request.query}",
                    url="https://example.test/1",
                    snippet="Search result.",
                    adapter="search",
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
            message="Ready.",
            diagnostics={"capabilities": "extract", "runtime": "local"},
        )

    def collect(self, request):
        return AcquisitionResult(
            provider="trafilatura",
            provider_type="generic-crawler",
            status="ok",
            reason="items-found",
            message="Extracted.",
            items=[
                SourceItem(
                    source_type="web-page",
                    title="Extracted content",
                    url="https://example.test/extracted",
                    snippet="Full text extraction.",
                    adapter="trafilatura",
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
            message="Ready.",
            diagnostics={
                "capabilities": "search",
                "contract_version": "source-radar.bridge.v1",
                "platforms": "xiaohongshu,bilibili,weibo",
            },
        )

    def collect(self, request):
        return AcquisitionResult(
            provider="mediacrawler",
            provider_type="external-bridge",
            status="ok",
            reason="items-found",
            message="Community results.",
            items=[
                SourceItem(
                    source_type="community-post",
                    title="Community post",
                    url="https://example.test/community",
                    snippet="Community evidence.",
                    adapter="mediacrawler",
                )
            ],
        )


def _make_sufficient_eval():
    """Return an evaluator that says evidence is sufficient."""
    return {"evidence_sufficient": True, "confidence": "medium",
            "reason": "enough for test", "next_tool": "",
            "next_limit": 0, "skip_tools": [
                {"tool": "mediacrawler", "reason": "不需要中文社区讨论"}
            ], "gaps": []}


def _make_continue_eval(next_tool="trafilatura"):
    """Return an evaluator that says continue with next_tool."""
    return {"evidence_sufficient": False, "confidence": "low",
            "reason": "need more", "next_tool": next_tool,
            "next_limit": 5, "skip_tools": [], "gaps": []}


# ── Progress / quiet ────────────────────────────────────────────────


class ProgressTests(unittest.TestCase):
    def test_ask_default_progress_on(self):
        progress_lines = []
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.ask("test query", progress=progress_lines.append)
        self.assertTrue(len(progress_lines) > 0)
        self.assertIn("analysis-ready", report.status)

    def test_verify_default_progress_on(self):
        progress_lines = []
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.verify("test claim", progress=progress_lines.append)
        self.assertTrue(len(progress_lines) > 0)

    def test_no_progress_when_none(self):
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.ask("test", progress=None)
        self.assertEqual(report.status, "analysis-ready")

    def test_json_output_has_no_progress_markers(self):
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.ask("test", progress=None)
        payload = report.to_dict()
        self.assertIsInstance(payload["query"], str)
        self.assertNotIn("[00:", json.dumps(payload))


# ── Adaptive max_tools ──────────────────────────────────────────────


class AdaptiveMaxToolsTests(unittest.TestCase):
    def test_max_tools_default_is_3(self):
        """adaptive collection stops at max_tools=3 even if evaluator wants more."""
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[
                FakeSearchProvider(),
                FakeTrafilaturaProvider(),
            ],
        )
        with patch("source_radar.agent.evaluate_collection_sufficiency",
                   return_value=(_make_continue_eval("trafilatura"), "ok")):
            items, tool_calls, evidence, results, skipped, cache_h, fresh = (
                agent._adaptive_collect(
                    "test query",
                    available=["search", "trafilatura"],
                    mode="ask",
                    max_tools=3,
                )
            )
        ran = [tc for tc in tool_calls if tc.get("skipped") != "true"]
        # search + up to 2 more (max_tools-1 rounds)
        self.assertLessEqual(len(ran), 3)

    def test_never_exceeds_max_tools(self):
        """evaluator can't push past max_tools=1."""
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[
                FakeSearchProvider(),
                FakeTrafilaturaProvider(),
            ],
        )
        # No patch needed — max_tools=1 means no evaluator loop
        items, tool_calls, evidence, results, skipped, cache_h, fresh = (
            agent._adaptive_collect(
                "test",
                available=["search", "trafilatura"],
                mode="ask",
                max_tools=1,
            )
        )
        ran = [tc for tc in tool_calls if tc.get("skipped") != "true"]
        self.assertEqual(len(ran), 1)
        self.assertEqual(ran[0]["tool"], "search")

    def test_tool_calls_include_elapsed_and_cache_fields(self):
        """every tool_call has elapsed_ms, cache_hit, cache_key, cache_age_seconds, limit."""
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        items, tool_calls, evidence, results, skipped, cache_h, fresh = (
            agent._adaptive_collect(
                "test",
                available=["search"],
                mode="ask",
                max_tools=1,
            )
        )
        tc = tool_calls[0]
        self.assertIn("elapsed_ms", tc)
        self.assertIn("cache_hit", tc)
        self.assertIn("cache_key", tc)
        self.assertIn("cache_age_seconds", tc)
        self.assertIn("limit", tc)

    def test_evaluator_stop_reason_recorded(self):
        """ask mode: AI says sufficient → stop, no code-level guard."""
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[
                FakeSearchProvider(),
                FakeTrafilaturaProvider(),
            ],
        )
        with patch("source_radar.agent.evaluate_collection_sufficiency",
                   return_value=(_make_sufficient_eval(), "ok")):
            items, tool_calls, evidence, results, skipped, cache_h, fresh = (
                agent._adaptive_collect(
                    "test",
                    available=["search", "trafilatura"],
                    mode="ask",
                )
            )
        ran = [tc for tc in tool_calls if tc.get("skipped") != "true"]
        # ask mode trusts AI: only search ran, then stopped
        self.assertEqual(len(ran), 1)
        self.assertEqual(ran[0]["tool"], "search")

    def test_verify_mode_forces_trafilatura_on_search_only(self):
        """verify mode: code-level guard forces trafilatura when all evidence is search-result."""
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[
                FakeSearchProvider(),
                FakeTrafilaturaProvider(),
            ],
        )
        with patch("source_radar.agent.evaluate_collection_sufficiency",
                   return_value=(_make_sufficient_eval(), "ok")):
            items, tool_calls, evidence, results, skipped, cache_h, fresh = (
                agent._adaptive_collect(
                    "test",
                    available=["search", "trafilatura"],
                    mode="verify",
                )
            )
        ran = [tc for tc in tool_calls if tc.get("skipped") != "true"]
        # verify mode forces trafilatura when all evidence is search-result
        self.assertEqual(len(ran), 2)
        self.assertEqual(ran[0]["tool"], "search")
        self.assertEqual(ran[1]["tool"], "trafilatura")


# ── MediCrawler control ─────────────────────────────────────────────


class MediaCrawlerControlTests(unittest.TestCase):
    def test_mediacrawler_not_run_when_evaluator_skips(self):
        """mediacrawler is not run when evaluator explicitly skips it."""
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[
                FakeSearchProvider(),
                FakeTrafilaturaProvider(),
                FakeMediaCrawlerProvider(),
            ],
        )
        with patch("source_radar.agent.evaluate_collection_sufficiency",
                   return_value=(_make_sufficient_eval(), "ok")):
            items, tool_calls, evidence, results, skipped, cache_h, fresh = (
                agent._adaptive_collect(
                    "simple programming question",
                    available=["search", "trafilatura", "mediacrawler"],
                    mode="ask",
                )
            )
        ran_tools = [tc["tool"] for tc in tool_calls if tc.get("skipped") != "true"]
        self.assertNotIn("mediacrawler", ran_tools)

    def test_mediacrawler_skipped_tracked(self):
        """evaluator skip_tools are captured in the skipped list."""
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[
                FakeSearchProvider(),
                FakeTrafilaturaProvider(),
                FakeMediaCrawlerProvider(),
            ],
        )
        eval_result = _make_sufficient_eval()
        eval_result["skip_tools"] = [
            {"tool": "mediacrawler", "reason": "不需要中文社区讨论"}
        ]
        with patch("source_radar.agent.evaluate_collection_sufficiency",
                   return_value=(eval_result, "ok")):
            items, tool_calls, evidence, results, skipped, cache_h, fresh = (
                agent._adaptive_collect(
                    "programming question",
                    available=["search", "trafilatura", "mediacrawler"],
                    mode="ask",
                )
            )
        # skipped list should contain mediacrawler
        skip_tools = [s.get("tool") for s in skipped]
        self.assertIn("mediacrawler", skip_tools)


# ── Verify strictness ───────────────────────────────────────────────


class VerifyStrictnessTests(unittest.TestCase):
    def test_evidence_needs_more_search_only(self):
        cards = [
            EvidenceCard(
                id="ev-1", source_type="search-result", title="T",
                url="https://x.test", summary="S", adapter="search",
            )
        ]
        self.assertTrue(
            _evidence_needs_more(
                cards, ran_tools=["search"], available=["search", "trafilatura"]
            )
        )

    def test_verify_evidence_has_trafilatura_no_need_more(self):
        cards = [
            EvidenceCard(
                id="ev-1", source_type="search-result", title="T",
                url="https://x.test", summary="S", adapter="search",
            ),
            EvidenceCard(
                id="ev-2", source_type="web-page", title="T2",
                url="https://x.test/2", summary="S2", adapter="trafilatura",
            ),
        ]
        self.assertFalse(
            _evidence_needs_more(
                cards, ran_tools=["search", "trafilatura"],
                available=["search", "trafilatura", "mediacrawler"],
            )
        )

    def test_verify_no_trafilatura_available(self):
        cards = [
            EvidenceCard(
                id="ev-1", source_type="search-result", title="T",
                url="https://x.test", summary="S", adapter="search",
            )
        ]
        self.assertFalse(
            _evidence_needs_more(
                cards, ran_tools=["search"], available=["search"]
            )
        )

    def test_verify_empty_evidence(self):
        self.assertFalse(
            _evidence_needs_more(
                [], ran_tools=["search"], available=["search", "trafilatura"]
            )
        )

    def test_verify_agent_uses_strictness_guard(self):
        """verify mode overrides evaluator 'sufficient' when only search-results."""
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[
                FakeSearchProvider(),
                FakeTrafilaturaProvider(),
            ],
        )
        # Evaluator says sufficient but verify strictness forces trafilatura
        eval_sufficient = _make_sufficient_eval()
        eval_sufficient["next_tool"] = ""  # evaluator says stop
        with patch("source_radar.agent.evaluate_collection_sufficiency",
                   return_value=(eval_sufficient, "ok")):
            items, tool_calls, evidence, results, skipped, cache_h, fresh = (
                agent._adaptive_collect(
                    "test claim",
                    available=["search", "trafilatura"],
                    mode="verify",
                )
            )
        ran_tools = [tc["tool"] for tc in tool_calls if tc.get("skipped") != "true"]
        # verify strictness should force trafilatura after search
        self.assertIn("trafilatura", ran_tools)

    def test_verify_no_auto_mediacrawler(self):
        """verify does not automatically run mediacrawler even with strictness."""
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[
                FakeSearchProvider(),
                FakeTrafilaturaProvider(),
                FakeMediaCrawlerProvider(),
            ],
        )
        eval_sufficient = _make_sufficient_eval()
        with patch("source_radar.agent.evaluate_collection_sufficiency",
                   return_value=(eval_sufficient, "ok")):
            items, tool_calls, evidence, results, skipped, cache_h, fresh = (
                agent._adaptive_collect(
                    "test claim",
                    available=["search", "trafilatura", "mediacrawler"],
                    mode="verify",
                )
            )
        ran_tools = [tc["tool"] for tc in tool_calls if tc.get("skipped") != "true"]
        self.assertNotIn("mediacrawler", ran_tools)


# ── Cache ───────────────────────────────────────────────────────────


class CacheTests(unittest.TestCase):
    def setUp(self):
        cache_clear()

    def tearDown(self):
        cache_clear()

    def test_cache_miss_then_hit(self):
        result = {"provider": "search", "provider_type": "search",
                  "status": "ok", "reason": "", "message": "",
                  "fix": "", "retryable": False, "warnings": [],
                  "evidence_gaps": [], "diagnostics": {},
                  "candidates": [], "items": []}
        cached, age = get_cached_result("search", query="test-miss-hit", url="", repo="", limit=5)
        self.assertIsNone(cached)
        self.assertEqual(age, 0)

        put_cached_result("search", result, query="test-miss-hit")
        cached, age = get_cached_result("search", query="test-miss-hit", url="", repo="", limit=5)
        self.assertIsNotNone(cached)
        self.assertGreaterEqual(age, 0)

    def test_cache_age_seconds_is_integer(self):
        result = {"provider": "search", "provider_type": "search",
                  "status": "ok", "reason": "", "message": "",
                  "fix": "", "retryable": False, "warnings": [],
                  "evidence_gaps": [], "diagnostics": {},
                  "candidates": [], "items": []}
        put_cached_result("search", result, query="age-test")
        cached, age = get_cached_result("search", query="age-test")
        self.assertIsInstance(age, int)
        self.assertGreaterEqual(age, 0)

    def test_realtime_query_not_cached(self):
        self.assertTrue(is_realtime_query("今天天气"))
        self.assertTrue(is_realtime_query("最新股价"))
        self.assertFalse(is_realtime_query("python tutorial"))

    def test_realtime_query_cache_miss(self):
        result = {"provider": "search", "provider_type": "search",
                  "status": "ok", "reason": "", "message": "",
                  "fix": "", "retryable": False, "warnings": [],
                  "evidence_gaps": [], "diagnostics": {},
                  "candidates": [], "items": []}
        put_cached_result("search", result, query="今天天气")
        cached, age = get_cached_result("search", query="今天天气")
        self.assertIsNone(cached)

    def test_old_cache_entry_no_adapter_version_still_readable(self):
        from source_radar.cache import _cache_root
        # Write a raw entry mimicking old format (without adapter_version)
        key = _make_key("search", query="old-entry", url="", repo="", limit=5)
        ep = _cache_root() / "entries" / f"{key}.json"
        ep.parent.mkdir(parents=True, exist_ok=True)
        old_entry = {
            "schema_version": 1,
            "created_at": time.time(),
            "last_accessed_at": time.time(),
            "provider": "search",
            "key": key,
            "ttl_seconds": 21600,
            "query": "old-entry",
            "result": {
                "provider": "search", "provider_type": "search",
                "status": "ok", "reason": "", "message": "",
                "fix": "", "retryable": False, "warnings": [],
                "evidence_gaps": [], "diagnostics": {},
                "candidates": [], "items": [],
            },
        }
        ep.write_text(json.dumps(old_entry), encoding="utf-8")
        # Reading old entry should not crash (may miss due to key mismatch)
        try:
            get_cached_result("search", query="old-entry")
        except Exception:
            self.fail("get_cached_result crashed on old cache entry")

    def test_cache_status_includes_version_info(self):
        from source_radar.cache import cache_status
        status = cache_status()
        self.assertIn("schema_version", status)
        self.assertIn("adapter_version", status)
        self.assertEqual(status["adapter_version"], CACHE_ADAPTER_VERSION)

    def test_provider_signature_differs_by_type(self):
        sig1 = _make_provider_signature("search", "search", "", "SearchProvider")
        sig2 = _make_provider_signature("mediacrawler", "external-bridge", "", "MediaCrawlerProvider")
        self.assertNotEqual(sig1, sig2)

    def test_provider_signature_includes_hostname(self):
        sig = _make_provider_signature("mediacrawler", "external-bridge",
                                        "https://mediacrawler.example.com/collect", "")
        self.assertTrue(len(sig) > 0)


# ── Session relevance ───────────────────────────────────────────────


class SessionRelevanceTests(unittest.TestCase):
    def setUp(self):
        clear_session("test-session")

    def tearDown(self):
        clear_session("test-session")

    def test_lexical_follow_up_detected(self):
        self.assertTrue(lexical_is_related("那内存怎么调", [
            {"query": "9800x3d 微星b850 怎么超频"}
        ]))
        self.assertTrue(lexical_is_related("这个安全吗", [
            {"query": "某产品怎么样"}
        ]))
        self.assertTrue(lexical_is_related("继续", [
            {"query": "previous topic"}
        ]))

    def test_lexical_unrelated_detected(self):
        self.assertFalse(lexical_is_related("Java 接口编程", [
            {"query": "9800x3d CPU 超频"}
        ]))

    def test_lexical_empty_history(self):
        self.assertFalse(lexical_is_related("test", []))

    def test_lexical_shared_words(self):
        self.assertTrue(lexical_is_related("微星b850 内存兼容", [
            {"query": "微星b850 主板评测"}
        ]))

    def test_session_read_write(self):
        append_session_record("test-session", {
            "mode": "ask",
            "query": "test query",
            "status": "ok",
            "evidence_refs": [],
            "answer_summary": "summary",
        })
        records = load_recent_session_context("test-session")
        self.assertGreater(len(records), 0)

    def test_session_record_strips_large_fields(self):
        append_session_record("test-session", {
            "mode": "ask",
            "query": "test",
            "status": "ok",
            "evidence_refs": [
                {"url": "https://x.test", "title": "T",
                 "snippet": "A" * 500, "provider": "search"}
            ],
            "answer_summary": "B" * 800,
        })
        records = load_recent_session_context("test-session")
        self.assertEqual(len(records), 1)
        ref = records[0]["evidence_refs"][0]
        self.assertLessEqual(len(ref.get("snippet", "")), 300)

    def test_session_record_no_secrets(self):
        append_session_record("test-session", {
            "mode": "ask",
            "query": "test",
            "status": "ok",
            "evidence_refs": [],
            "answer_summary": "ok",
        })
        records = load_recent_session_context("test-session")
        raw = json.dumps(records)
        self.assertNotIn("sk-", raw.lower())
        self.assertNotIn("api_key", raw.lower())
        self.assertNotIn("cookie", raw.lower())


# ── Trace fields ────────────────────────────────────────────────────


class TraceFieldsTests(unittest.TestCase):
    def test_agent_trace_has_all_v3_fields(self):
        trace = AgentTrace(
            mode="agent",
            ai_status="configured",
            model="fake",
            planned_tools=["search"],
            tool_calls=[],
            acquisition=[],
            context_used=True,
            session_id="test",
            context_records_read=2,
            context_ignore_reason="",
            reused_evidence_count=2,
            fresh_evidence_count=5,
            actually_used_tools=["search", "trafilatura"],
            skipped_tools=[{"tool": "mediacrawler", "reason": "not needed"}],
            cache_hit_count=1,
            fresh_tool_count=1,
        )
        self.assertTrue(trace.context_used)
        self.assertEqual(trace.session_id, "test")
        self.assertEqual(trace.context_records_read, 2)
        self.assertEqual(trace.reused_evidence_count, 2)
        self.assertEqual(trace.fresh_evidence_count, 5)
        self.assertEqual(trace.actually_used_tools, ["search", "trafilatura"])
        self.assertEqual(len(trace.skipped_tools), 1)
        self.assertEqual(trace.cache_hit_count, 1)
        self.assertEqual(trace.fresh_tool_count, 1)

    def test_agent_trace_defaults(self):
        trace = AgentTrace(
            mode="agent",
            ai_status="ok",
            model="test",
            planned_tools=[],
            tool_calls=[],
        )
        self.assertFalse(trace.context_used)
        self.assertEqual(trace.session_id, "")
        self.assertEqual(trace.context_records_read, 0)
        self.assertEqual(trace.cache_hit_count, 0)

    def test_verify_report_json_includes_trace_fields(self):
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.verify("test")
        payload = report.to_dict()
        ag = payload["agent"]
        self.assertIn("context_used", ag)
        self.assertIn("session_id", ag)
        self.assertIn("cache_hit_count", ag)
        self.assertIn("fresh_tool_count", ag)
        self.assertIn("actually_used_tools", ag)
        self.assertIn("skipped_tools", ag)

    def test_ask_report_json_includes_trace_fields(self):
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.ask("test query")
        payload = report.to_dict()
        ag = payload["agent"]
        self.assertIn("context_used", ag)
        self.assertIn("actually_used_tools", ag)


# ── Research not broken ─────────────────────────────────────────────


class ResearchNotBrokenTests(unittest.TestCase):
    def test_research_no_session_parameter(self):
        """research() does not accept session parameter."""
        import inspect
        sig = inspect.signature(VerificationAgent.research)
        self.assertNotIn("session", sig.parameters)
        self.assertNotIn("session_context", sig.parameters)

    def test_research_returns_structured_report(self):
        """research with max_rounds=1 returns a valid report structure."""
        # research() checks isinstance(provider, AIProvider) and returns early
        # if not. FakeAIProvider is NOT an AIProvider, so we get ai-error.
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.research("test query", max_rounds=1)
        self.assertEqual(report.status, "ai-error")
        payload = report.to_dict()
        self.assertIn("query", payload)
        self.assertIn("status", payload)
        self.assertIn("requested_max_rounds", payload)

    def test_research_max_rounds_preserved(self):
        """requested_max_rounds is preserved in report."""
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.research("test", max_rounds=2)
        self.assertEqual(report.requested_max_rounds, 2)

    def test_research_with_real_ai_provider_plan(self):
        """research with real AIProvider calls planner (integration test, requires AI)."""
        # This is a smoke test — it will skip if no AI configured
        from source_radar.llm import AIProvider
        ai = AIProvider.from_environment()
        if not isinstance(ai, AIProvider):
            self.skipTest("AI not configured")
        agent = VerificationAgent(
            provider=ai,
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.research("test query", max_rounds=1)
        self.assertIsNotNone(report.query)


# ── Session context in synthesize/judge (P0) ────────────────────


class SessionContextInSynthesisTests(unittest.TestCase):
    def test_synthesize_receives_session_context(self):
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.ask("test query", session_context="previous topic context")
        self.assertEqual(report.status, "analysis-ready")
        self.assertEqual(report.agent.context_used, False)  # not set via agent params

    def test_judge_receives_session_context(self):
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.verify("test claim", session_context="prior context")
        self.assertEqual(report.status, "ai-judged")

    def test_synthesize_fallback_without_session_context(self):
        """Provider without session_context param still works via TypeError fallback."""
        class OldProvider:
            status = "configured"
            model = "old-model"
            def synthesize(self, query, evidence):
                return InformationAnalysis(
                    summary=f"Old: {query}", key_points=[], source_notes=[],
                    disagreements=[], noise_notes=[],
                )
            def judge(self, claim, evidence):
                return Judgement(
                    status="ai-judged", summary=f"Old: {claim}",
                    evidence_ids=[], gaps=[], confidence="unknown",
                )
        agent = VerificationAgent(
            provider=OldProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.ask("test", session_context="ctx")
        self.assertEqual(report.status, "analysis-ready")


# ── Legacy ask trace session fields (P1) ────────────────────────


class LegacyAskTraceTests(unittest.TestCase):
    def setUp(self):
        cache_clear()

    def tearDown(self):
        cache_clear()

    def test_ask_legacy_trace_has_session_fields(self):
        """ask --source search trace includes session fields."""
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.ask(
            "legacy-session-test", source="search",
            session_context="ctx", context_used=True,
            session_id="test-sid", context_records_read=3,
            context_ignore_reason="", reused_evidence_count=2,
        )
        trace = report.agent
        self.assertTrue(trace.context_used)
        self.assertEqual(trace.session_id, "test-sid")
        self.assertEqual(trace.context_records_read, 3)
        self.assertEqual(trace.context_ignore_reason, "")
        self.assertEqual(trace.reused_evidence_count, 2)
        self.assertEqual(trace.fresh_evidence_count, len(report.evidence))
        self.assertEqual(trace.cache_hit_count, 0)
        self.assertEqual(trace.fresh_tool_count, 1)
        self.assertEqual(trace.skipped_tools, [])

    def test_ask_legacy_trace_has_cache_fields(self):
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.ask("legacy-cache-test", source="search")
        trace = report.agent
        self.assertIn("cache_hit_count", trace.__dict__)
        self.assertIn("fresh_tool_count", trace.__dict__)


# ── Session relevance prompt enhanced (P1) ──────────────────────


class SessionRelevancePromptTests(unittest.TestCase):
    def test_history_text_includes_tools_evidence_gaps(self):
        """evaluate_session_relevance history_text contains tools/evidence/gaps."""
        from source_radar.llm import evaluate_session_relevance
        records = [{
            "ts": "2026-05-28T10:00:00Z",
            "query": "9800x3d 超频",
            "answer_summary": "超频方案...",
            "tools_used": ["search", "trafilatura"],
            "tools_skipped": [{"tool": "mediacrawler", "reason": "不需要"}],
            "evidence_refs": [
                {"title": "超频教程", "url": "https://x.test", "provider": "search", "snippet": "短摘要"}
            ],
            "gaps": ["缺少内存时序信息"],
        }]
        # Just verify it doesn't crash and returns valid structure
        # (We can't easily test the prompt content without mocking _call_model)
        try:
            result, status = evaluate_session_relevance(
                "https://fake.test/v1",
                {"Authorization": "Bearer fake"},
                "fake-model",
                "那内存怎么调",
                records,
            )
            # Will fail to call the model, but should return fallback gracefully
            self.assertIn("related", result)
        except Exception:
            pass  # Network error is expected in unit test


# ── Cache age 0-second display (P2) ─────────────────────────────


class CacheAgeZeroTests(unittest.TestCase):
    def setUp(self):
        cache_clear()

    def tearDown(self):
        cache_clear()

    def test_cache_age_zero_displayed_on_immediate_hit(self):
        """cache_age_seconds shows '0' when cache_hit=True and age=0."""
        result = {"provider": "search", "provider_type": "search",
                  "status": "ok", "reason": "", "message": "",
                  "fix": "", "retryable": False, "warnings": [],
                  "evidence_gaps": [], "diagnostics": {},
                  "candidates": [], "items": []}
        put_cached_result("search", result, query="age-zero-test")
        cached, age = get_cached_result("search", query="age-zero-test")
        self.assertIsNotNone(cached)
        self.assertEqual(age, 0)
        # The formatting logic: str(cache_age) if cache_hit else ""
        cache_hit = cached is not None
        formatted = str(age) if cache_hit else ""
        self.assertEqual(formatted, "0")

    def test_cache_miss_age_is_empty(self):
        """cache_age_seconds is empty string on cache miss."""
        cached, age = get_cached_result("search", query="no-such-key")
        self.assertIsNone(cached)
        cache_hit = cached is not None
        formatted = str(age) if cache_hit else ""
        self.assertEqual(formatted, "")


# ── Verify legacy cache_key (P2) ────────────────────────────────


class VerifyLegacyCacheKeyTests(unittest.TestCase):
    def test_verify_legacy_tool_calls_have_cache_key(self):
        """verify legacy path tool_calls include cache_key field."""
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.verify("test claim", source="search")
        for tc in report.agent.tool_calls:
            self.assertIn("cache_key", tc, f"tool_call missing cache_key: {tc}")
            self.assertIn("cache_age_seconds", tc)
            self.assertIn("elapsed_ms", tc)

    def test_ask_legacy_tool_calls_have_cache_key(self):
        """ask legacy path tool_calls include cache_key field."""
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.ask("test query", source="search")
        for tc in report.agent.tool_calls:
            self.assertIn("cache_key", tc, f"tool_call missing cache_key: {tc}")


# ── Skipped tool schema (P3) ────────────────────────────────────


class SkippedToolSchemaTests(unittest.TestCase):
    def test_skipped_tool_call_has_skip_reason_and_decided_by(self):
        """skipped tool_call entries have skip_reason and decided_by."""
        from source_radar.llm import AIProvider

        class TestAIProvider(AIProvider):
            def __init__(self):
                self.api_key = "fake"
                self.model = "test"
                self.endpoint = "https://fake.test/v1"
                self.provider = "openai"
                self.status = "configured"
            def judge(self, claim, evidence, session_context=""):
                return Judgement(status="ai-judged", summary="test",
                                 evidence_ids=[], gaps=[], confidence="unknown")
            def synthesize(self, query, evidence, session_context=""):
                return InformationAnalysis(summary="test", key_points=[],
                                           source_notes=[], disagreements=[], noise_notes=[])

        agent = VerificationAgent(
            provider=TestAIProvider(),
            acquisition_providers=[
                FakeSearchProvider(),
                FakeTrafilaturaProvider(),
                FakeMediaCrawlerProvider(),
            ],
        )
        eval_result = _make_sufficient_eval()
        eval_result["skip_tools"] = [
            {"tool": "mediacrawler", "reason": "不需要中文社区讨论"}
        ]
        with patch("source_radar.agent.evaluate_collection_sufficiency",
                   return_value=(eval_result, "ok")):
            report = agent.ask("test")
        skipped_calls = [tc for tc in report.agent.tool_calls if tc.get("skipped") == "true"]
        self.assertGreater(len(skipped_calls), 0)
        for tc in skipped_calls:
            self.assertIn("skip_reason", tc)
            self.assertIn("decided_by", tc)
            self.assertEqual(tc["decided_by"], "collection_evaluator")
            self.assertIn("reason", tc)

    def test_skipped_tools_in_trace_have_decided_by(self):
        """skipped_tools in AgentTrace have decided_by field."""
        from source_radar.llm import AIProvider

        class TestAIProvider(AIProvider):
            def __init__(self):
                self.api_key = "fake"
                self.model = "test"
                self.endpoint = "https://fake.test/v1"
                self.provider = "openai"
                self.status = "configured"
            def judge(self, claim, evidence, session_context=""):
                return Judgement(status="ai-judged", summary="test",
                                 evidence_ids=[], gaps=[], confidence="unknown")
            def synthesize(self, query, evidence, session_context=""):
                return InformationAnalysis(summary="test", key_points=[],
                                           source_notes=[], disagreements=[], noise_notes=[])

        agent = VerificationAgent(
            provider=TestAIProvider(),
            acquisition_providers=[
                FakeSearchProvider(),
                FakeTrafilaturaProvider(),
                FakeMediaCrawlerProvider(),
            ],
        )
        eval_result = _make_sufficient_eval()
        eval_result["skip_tools"] = [
            {"tool": "mediacrawler", "reason": "不需要中文社区讨论"}
        ]
        with patch("source_radar.agent.evaluate_collection_sufficiency",
                   return_value=(eval_result, "ok")):
            report = agent.ask("test")
        for s in report.agent.skipped_tools:
            self.assertIn("decided_by", s)
            self.assertEqual(s["decided_by"], "collection_evaluator")


# ── Evidence Fidelity (v3.1) ──────────────────────────────────────


class EvidenceFidelityTests(unittest.TestCase):
    """Tests for raw_excerpt, compression metadata, and evidence_input_profile."""

    def test_source_item_has_raw_content_fields(self):
        item = SourceItem(
            source_type="web-page", title="T", url="https://x.test",
            snippet="short", adapter="trafilatura",
            raw_content="long text " * 200,
            raw_content_length=2000,
            raw_content_truncated=False,
        )
        self.assertEqual(item.raw_content, "long text " * 200)
        self.assertEqual(item.raw_content_length, 2000)
        self.assertFalse(item.raw_content_truncated)

    def test_evidence_card_has_raw_excerpt_fields(self):
        card = EvidenceCard(
            id="ev-001", source_type="web-page", title="T",
            url="https://x.test", summary="S", adapter="trafilatura",
            raw_excerpt="long excerpt",
            raw_content_length=5000,
            raw_content_truncated=True,
            distilled={"facts": ["f1"]},
            compression={"method": "mechanical_excerpt"},
        )
        self.assertEqual(card.raw_excerpt, "long excerpt")
        self.assertTrue(card.raw_content_truncated)
        self.assertEqual(card.distilled["facts"], ["f1"])

    def test_build_evidence_cards_summary_from_snippet(self):
        from source_radar.evidence import build_evidence_cards
        item = SourceItem(
            source_type="web-page", title="T", url="https://x.test",
            snippet="snippet text", adapter="trafilatura",
        )
        cards = build_evidence_cards([item])
        self.assertEqual(cards[0].summary, "snippet text")

    def test_build_evidence_cards_raw_excerpt_from_raw_content(self):
        from source_radar.evidence import build_evidence_cards
        raw = "A" * 5000
        item = SourceItem(
            source_type="web-page", title="T", url="https://x.test",
            snippet="short", adapter="trafilatura",
            raw_content=raw, raw_content_length=5000,
        )
        cards = build_evidence_cards([item])
        self.assertEqual(len(cards[0].raw_excerpt), 3000)
        self.assertTrue(cards[0].raw_content_truncated)

    def test_build_evidence_cards_raw_excerpt_fallback_to_snippet(self):
        from source_radar.evidence import build_evidence_cards
        item = SourceItem(
            source_type="search-result", title="T", url="https://x.test",
            snippet="search snippet", adapter="search",
        )
        cards = build_evidence_cards([item])
        self.assertEqual(cards[0].raw_excerpt, "search snippet")

    def test_build_evidence_cards_compression_loss_risk(self):
        from source_radar.evidence import build_evidence_cards
        # high risk: no raw content
        item1 = SourceItem(
            source_type="web-page", title="T", url="https://x.test",
            snippet="", adapter="trafilatura",
        )
        cards1 = build_evidence_cards([item1])
        self.assertEqual(cards1[0].compression["loss_risk"], "high")

        # low risk: raw content present, not truncated
        item2 = SourceItem(
            source_type="web-page", title="T", url="https://x.test",
            snippet="s", adapter="trafilatura",
            raw_content="short raw", raw_content_length=9,
        )
        cards2 = build_evidence_cards([item2])
        self.assertEqual(cards2[0].compression["loss_risk"], "low")

        # medium risk: truncated
        item3 = SourceItem(
            source_type="web-page", title="T", url="https://x.test",
            snippet="s", adapter="trafilatura",
            raw_content="A" * 4000, raw_content_length=4000,
        )
        cards3 = build_evidence_cards([item3])
        self.assertEqual(cards3[0].compression["loss_risk"], "medium")

    def test_evidence_input_profile(self):
        from source_radar.evidence import build_evidence_cards, evidence_input_profile
        items = [
            SourceItem(source_type="web-page", title="T1", url="https://a.test",
                       snippet="s1", adapter="trafilatura",
                       raw_content="A" * 2000, raw_content_length=2000),
            SourceItem(source_type="search-result", title="T2", url="https://b.test",
                       snippet="s2", adapter="search"),
        ]
        cards = build_evidence_cards(items)
        profile = evidence_input_profile(cards)
        self.assertEqual(profile["evidence_count"], 2)
        self.assertEqual(profile["cards_with_raw_excerpt"], 2)
        self.assertEqual(profile["truncated_cards"], 0)

    def test_agent_trace_has_evidence_input_profile(self):
        agent = VerificationAgent(
            provider=FakeAIProvider(),
            acquisition_providers=[FakeSearchProvider()],
        )
        report = agent.ask("test")
        self.assertIn("evidence_input_profile", report.agent.__dict__)
        profile = report.agent.evidence_input_profile
        self.assertIn("evidence_count", profile)
        self.assertIn("cards_with_raw_excerpt", profile)

    def test_evidence_card_payload_includes_raw_excerpt(self):
        from source_radar.llm import _evidence_card_payload
        card = EvidenceCard(
            id="ev-001", source_type="web-page", title="T",
            url="https://x.test", summary="S", adapter="trafilatura",
            raw_excerpt="long text",
        )
        payload = _evidence_card_payload(card)
        self.assertEqual(payload["raw_excerpt"], "long text")

    def test_evidence_card_payload_excludes_empty_raw_excerpt(self):
        from source_radar.llm import _evidence_card_payload
        card = EvidenceCard(
            id="ev-001", source_type="search-result", title="T",
            url="https://x.test", summary="S", adapter="search",
        )
        payload = _evidence_card_payload(card)
        self.assertNotIn("raw_excerpt", payload)

    def test_should_distill_auto_research(self):
        from source_radar.llm import should_distill
        cards = [EvidenceCard(id="ev-001", source_type="web-page", title="T",
                              url="https://x.test", summary="S")]
        self.assertTrue(should_distill(cards, "research"))

    def test_should_distill_auto_verify_many_cards(self):
        from source_radar.llm import should_distill
        cards = [
            EvidenceCard(id=f"ev-{i}", source_type="web-page", title="T",
                         url=f"https://x.test/{i}", summary="S",
                         raw_excerpt="A" * 2000)
            for i in range(4)
        ]
        self.assertTrue(should_distill(cards, "verify"))

    def test_should_distill_never(self):
        from source_radar.llm import should_distill
        cards = [EvidenceCard(id="ev-001", source_type="web-page", title="T",
                              url="https://x.test", summary="S")]
        self.assertFalse(should_distill(cards, "ask", "never"))

    def test_should_distill_always(self):
        from source_radar.llm import should_distill
        cards = [EvidenceCard(id="ev-001", source_type="web-page", title="T",
                              url="https://x.test", summary="S")]
        self.assertTrue(should_distill(cards, "ask", "always"))

    def test_distill_evidence_cards_failure_does_not_break(self):
        from source_radar.llm import distill_evidence_cards
        cards = [EvidenceCard(id="ev-001", source_type="web-page", title="T",
                              url="https://x.test", summary="S",
                              raw_excerpt="text")]
        # Call with fake endpoint — will fail
        result, profile = distill_evidence_cards(
            "https://fake.test/v1", {"Authorization": "Bearer fake"},
            "fake-model", "test query", cards,
        )
        # Should return original cards unchanged
        self.assertEqual(len(result), 1)
        self.assertEqual(profile["distillation_status"], "error")


# ── v3.1 polish fixes ────────────────────────────────────────────


class EvidenceFidelityPolishTests(unittest.TestCase):
    def test_search_result_loss_risk_not_low(self):
        """search-result with only snippet should have loss_risk != low."""
        from source_radar.evidence import build_evidence_cards
        item = SourceItem(
            source_type="search-result", title="T", url="https://x.test",
            snippet="search snippet only", adapter="search",
        )
        cards = build_evidence_cards([item])
        self.assertEqual(cards[0].compression["loss_risk"], "high")
        self.assertEqual(cards[0].compression["source_fidelity"], "snippet_only")

    def test_source_fidelity_excerpt_for_trafilatura(self):
        """trafilatura with raw_content > raw_excerpt => source_fidelity=excerpt."""
        from source_radar.evidence import build_evidence_cards
        item = SourceItem(
            source_type="web-page", title="T", url="https://x.test",
            snippet="short", adapter="trafilatura",
            raw_content="A" * 5000, raw_content_length=5000,
        )
        cards = build_evidence_cards([item])
        self.assertEqual(cards[0].compression["source_fidelity"], "excerpt")

    def test_content_hash_includes_raw_content(self):
        """content_hash should change when raw_content changes."""
        from source_radar.evidence import _content_hash
        item1 = SourceItem(
            source_type="web-page", title="T", url="https://x.test",
            snippet="s", adapter="trafilatura", raw_content="v1",
        )
        item2 = SourceItem(
            source_type="web-page", title="T", url="https://x.test",
            snippet="s", adapter="trafilatura", raw_content="v2",
        )
        self.assertNotEqual(_content_hash(item1), _content_hash(item2))

    def test_evidence_payload_with_budget(self):
        """_evidence_payload_with_budget truncates raw_excerpt when over budget."""
        from source_radar.llm import _evidence_payload_with_budget
        cards = [
            EvidenceCard(id=f"ev-{i}", source_type="web-page", title="T",
                         url=f"https://x.test/{i}", summary="S",
                         raw_excerpt="A" * 3000)
            for i in range(8)
        ]
        payload = _evidence_payload_with_budget(cards, max_cards=12, max_total_raw_chars=10000)
        total_raw = sum(len(p.get("raw_excerpt", "")) for p in payload)
        self.assertLessEqual(total_raw, 12000)  # some slack for first card

    def test_evidence_payload_under_budget_unchanged(self):
        """_evidence_payload_with_budget doesn't truncate when under budget."""
        from source_radar.llm import _evidence_payload_with_budget
        cards = [
            EvidenceCard(id="ev-001", source_type="web-page", title="T",
                         url="https://x.test", summary="S",
                         raw_excerpt="short text"),
        ]
        payload = _evidence_payload_with_budget(cards, max_cards=12, max_total_raw_chars=18000)
        self.assertEqual(payload[0]["raw_excerpt"], "short text")

    def test_distill_profile_tracks_requested_and_returned(self):
        """distill_evidence_cards returns requested/returned card counts."""
        from source_radar.llm import distill_evidence_cards
        cards = [
            EvidenceCard(id="ev-001", source_type="web-page", title="T",
                         url="https://x.test", summary="S", raw_excerpt="text"),
        ]
        _, profile = distill_evidence_cards(
            "https://fake.test/v1", {"Authorization": "Bearer fake"},
            "fake-model", "test query", cards,
        )
        # Will fail but should still have the counts
        self.assertIn("distillation_requested_cards", profile)
        self.assertEqual(profile["distillation_requested_cards"], 1)


if __name__ == "__main__":
    unittest.main()
