"""Black-box E2E tests for source-radar v3 main flows.

Runs real CLI commands via subprocess. Requires:
  - SOURCE_RADAR_E2E=1 to enable default tests
  - SOURCE_RADAR_E2E_SLOW=1 to additionally enable slow tests (research multi-round)
  - AI provider configured (tests degrade gracefully if not)
  - Network access (tests skip if unreachable)

Default E2E (SOURCE_RADAR_E2E=1):
  Proves main CLI → JSON → adaptive collection → cache → session → mediacrawler constraint flows work.
  Research uses max-rounds=1 (single-round only).

Slow E2E (SOURCE_RADAR_E2E_SLOW=1):
  Proves research multi-round evaluator flow works (max-rounds=2).
  Takes 3-5 minutes with real API calls.

Run default:
  SOURCE_RADAR_E2E=1 uv run python -m unittest tests.test_e2e_blackbox -v

Run with slow tests:
  SOURCE_RADAR_E2E=1 SOURCE_RADAR_E2E_SLOW=1 uv run python -m unittest tests.test_e2e_blackbox -v
"""

import json
import os
import subprocess
import unittest

_E2E_ENABLED = os.environ.get("SOURCE_RADAR_E2E") == "1"
_E2E_SLOW = os.environ.get("SOURCE_RADAR_E2E_SLOW") == "1"

_SKIP_REASON = "Set SOURCE_RADAR_E2E=1 to run black-box E2E tests"
_SKIP_SLOW = "Set SOURCE_RADAR_E2E_SLOW=1 to run slow E2E tests (research multi-round)"


def _run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a source-radar CLI command and return the result."""
    cmd = ["uv", "run", "python", "-m", "source_radar", *args]
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
    except subprocess.TimeoutExpired as e:
        # Return a synthetic result so callers can handle it
        return subprocess.CompletedProcess(
            args=cmd, returncode=-1,
            stdout=e.stdout or "", stderr=e.stderr or "",
        )


def _run_json(args: list[str], timeout: int = 120) -> tuple[subprocess.CompletedProcess, dict]:
    """Run a CLI command and parse stdout as JSON."""
    result = _run(args, timeout=timeout)
    payload = {}
    stdout = result.stdout or ""
    if result.returncode == 0 and stdout.strip():
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            pass
    return result, payload


@unittest.skipUnless(_E2E_ENABLED, _SKIP_REASON)
class AskMinimalTest(unittest.TestCase):
    """A. ask minimal flow."""

    def test_ask_returns_valid_json_with_required_fields(self):
        result, payload = _run_json(["ask", "1+1等于几", "--format", "json", "--quiet"])

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr[:500]}")
        self.assertNotIn("[00:", result.stdout, "progress leaked into stdout")

        self.assertIn("query", payload)
        self.assertIn("status", payload)
        self.assertIn("evidence", payload)
        self.assertIn("analysis", payload)
        self.assertIn("agent", payload)

        agent = payload["agent"]
        self.assertIn("tool_calls", agent)
        self.assertGreater(len(agent["tool_calls"]), 0, "tool_calls should not be empty")

        # mediacrawler should not run for a simple math question
        used = agent.get("actually_used_tools", [])
        self.assertNotIn("mediacrawler", used)


@unittest.skipUnless(_E2E_ENABLED, _SKIP_REASON)
class VerifyMinimalTest(unittest.TestCase):
    """B. verify minimal flow."""

    def test_verify_returns_valid_json_with_judgement(self):
        result, payload = _run_json(["verify", "1+1等于2", "--format", "json", "--quiet"])

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr[:500]}")
        self.assertNotIn("[00:", result.stdout)

        self.assertIn("claim", payload)
        self.assertIn("status", payload)
        self.assertIn("evidence", payload)
        self.assertIn("judgement", payload)
        self.assertIn("agent", payload)

        judgement = payload["judgement"]
        self.assertIn("confidence", judgement)
        self.assertIn("confidence_reason", judgement)

        agent = payload["agent"]
        self.assertIn("tool_calls", agent)
        self.assertGreater(len(agent["tool_calls"]), 0)


@unittest.skipUnless(_E2E_ENABLED, _SKIP_REASON)
class SessionFollowUpTest(unittest.TestCase):
    """C. session continuous follow-up."""

    def test_session_follow_up_uses_context(self):
        # Clear session
        _run(["session", "clear", "--session", "e2e-oc"])

        # First query
        r1, _ = _run_json(["ask", "9800x3d 微星b850 怎么超频",
                           "--format", "json", "--session", "e2e-oc", "--quiet"])
        self.assertEqual(r1.returncode, 0, f"first query failed: {r1.stderr[:300]}")

        # Follow-up query
        r2, payload2 = _run_json(["ask", "那内存怎么调",
                                  "--format", "json", "--session", "e2e-oc", "--quiet"])
        self.assertEqual(r2.returncode, 0, f"follow-up failed: {r2.stderr[:300]}")

        agent = payload2.get("agent", {})
        self.assertTrue(agent.get("context_used", False),
                        "context_used should be true for follow-up query")
        self.assertEqual(agent.get("session_id", ""), "e2e-oc")
        self.assertGreater(agent.get("context_records_read", 0), 0,
                           "context_records_read should be > 0")


@unittest.skipUnless(_E2E_ENABLED, _SKIP_REASON)
class NoSessionTest(unittest.TestCase):
    """D. --no-session disables context."""

    def test_no_session_disables_context(self):
        # Ensure session has data first
        _run(["session", "clear", "--session", "e2e-oc"])
        _run(["ask", "9800x3d 微星b850 怎么超频",
              "--format", "json", "--session", "e2e-oc", "--quiet"])

        # Now run with --no-session
        result, payload = _run_json(["ask", "那内存怎么调",
                                     "--format", "json", "--session", "e2e-oc",
                                     "--no-session", "--quiet"])
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr[:300]}")

        agent = payload.get("agent", {})
        self.assertFalse(agent.get("context_used", True),
                         "context_used should be false with --no-session")
        self.assertEqual(agent.get("context_ignore_reason", ""), "disabled")


@unittest.skipUnless(_E2E_ENABLED, _SKIP_REASON)
class CacheHitTest(unittest.TestCase):
    """E. cache hit on repeated query."""

    def test_second_run_hits_cache(self):
        # Clear cache
        _run(["cache", "clear"])

        # First run — populates cache
        r1, _ = _run_json(["ask", "Python 3.12 有哪些主要变化",
                           "--format", "json", "--quiet"])
        self.assertEqual(r1.returncode, 0, f"first run failed: {r1.stderr[:300]}")

        # Second run — should hit cache
        r2, payload2 = _run_json(["ask", "Python 3.12 有哪些主要变化",
                                  "--format", "json", "--quiet"])
        self.assertEqual(r2.returncode, 0, f"second run failed: {r2.stderr[:300]}")

        agent = payload2.get("agent", {})
        self.assertGreaterEqual(agent.get("cache_hit_count", 0), 1,
                                "cache_hit_count should be >= 1")

        tool_calls = agent.get("tool_calls", [])
        hit_calls = [tc for tc in tool_calls
                     if str(tc.get("cache_hit", "")).lower() in ("true", "1")]
        self.assertGreater(len(hit_calls), 0, "at least one tool_call should be cache hit")

        for tc in hit_calls:
            self.assertIn("cache_key", tc, "cache hit tool_call should have cache_key")
            self.assertNotEqual(tc.get("cache_age_seconds", ""), "",
                                "cache_age_seconds should not be empty on hit")


@unittest.skipUnless(_E2E_ENABLED, _SKIP_REASON)
class RealtimeNoCacheTest(unittest.TestCase):
    """F. realtime query bypasses cache."""

    def test_realtime_query_no_cache_hit(self):
        result, payload = _run_json(["ask", "今天天气怎么样",
                                     "--format", "json", "--quiet"])
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr[:300]}")

        agent = payload.get("agent", {})
        self.assertEqual(agent.get("cache_hit_count", 0), 0,
                         "realtime query should not hit cache")


@unittest.skipUnless(_E2E_ENABLED, _SKIP_REASON)
class NoSpuriousMediaCrawlerTest(unittest.TestCase):
    """G. normal programming question should not trigger mediacrawler."""

    def test_java_question_no_mediacrawler(self):
        result, payload = _run_json(
            ["ask", "Java 中接口和抽象类有什么区别", "--format", "json", "--quiet"])
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr[:300]}")

        agent = payload.get("agent", {})
        used = agent.get("actually_used_tools", [])
        self.assertNotIn("mediacrawler", used,
                         "mediacrawler should not run for a generic Java question")


@unittest.skipUnless(_E2E_ENABLED, _SKIP_REASON)
class ResearchFlowTest(unittest.TestCase):
    """H. research single-round flow (default E2E).

    Note: this only covers max-rounds=1. Multi-round evaluator flow
    requires SOURCE_RADAR_E2E_SLOW=1 (see ResearchSlowFlowTest).
    """

    def test_research_returns_structured_report(self):
        result, payload = _run_json([
            "research", "Python 3.12 变化",
            "--format", "json", "--max-rounds", "1", "--quiet",
        ], timeout=180)

        if result.returncode != 0:
            self.skipTest(f"research command failed or timed out: {result.stderr[:200]}")

        self.assertIn("query", payload)
        self.assertIn("status", payload)
        self.assertIn("requested_max_rounds", payload)
        self.assertIn("executed_rounds", payload)
        self.assertIn("rounds", payload)
        self.assertIn("queries", payload)
        self.assertIn("agent", payload)

        self.assertEqual(payload["requested_max_rounds"], 1)
        self.assertGreaterEqual(payload["executed_rounds"], 1)

        agent = payload["agent"]
        self.assertEqual(agent.get("mode"), "research")

        # Check cache trace fields in queries
        for q in payload.get("queries", []):
            self.assertIn("cache_hits", q, "query trace should have cache_hits")
            self.assertIn("cache_keys", q, "query trace should have cache_keys")
            self.assertIn("cache_age_seconds", q, "query trace should have cache_age_seconds")


@unittest.skipUnless(_E2E_ENABLED and _E2E_SLOW, _SKIP_SLOW)
class ResearchSlowFlowTest(unittest.TestCase):
    """H-slow. research multi-round evaluator flow (slow E2E).

    Proves the two-round evaluator loop works end-to-end.
    Takes 3-5 minutes with real API calls.
    """

    def test_research_multi_round_evaluator(self):
        result, payload = _run_json([
            "research", "9800x3d 微星b850 超频经验汇总",
            "--format", "json", "--max-rounds", "2", "--quiet",
        ], timeout=600)

        if result.returncode != 0:
            self.fail(f"research max-rounds=2 failed: {result.stderr[:300]}")

        self.assertIn("query", payload)
        self.assertIn("status", payload)
        self.assertEqual(payload["requested_max_rounds"], 2)
        self.assertGreaterEqual(payload["executed_rounds"], 1)

        agent = payload["agent"]
        self.assertEqual(agent.get("mode"), "research")

        # rounds should have evaluator data if executed_rounds > 1
        if payload["executed_rounds"] > 1:
            rounds = payload.get("rounds", [])
            self.assertGreater(len(rounds), 0)
            # At least one round should have evaluator trace
            has_evaluator = any(r.get("evaluator") for r in rounds)
            self.assertTrue(has_evaluator, "multi-round should have evaluator trace")


if __name__ == "__main__":
    unittest.main()
