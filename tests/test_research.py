"""Tests for research command: planner fallback, synthesis error, max-rounds lock."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from source_radar.llm import plan_research, synthesize_research


class ResearchPlanTests(unittest.TestCase):
    def test_plan_falls_back_on_bad_json(self):
        """Planner returns fallback + json-error status when output is not valid JSON."""
        plan, status = plan_research(
            endpoint="http://127.0.0.1:9317/v1/responses",
            headers={"Authorization": "Bearer test"},
            model="test-model",
            query="test query",
            ready_tools=["search", "trafilatura"],
            local_services_enabled=False,
        )
        self.assertEqual(status, "json-error")
        self.assertIn("search_queries", plan)
        self.assertEqual(plan["search_queries"], ["test query"])
        self.assertIn("research_type", plan)

    def test_plan_falls_back_on_empty_queries(self):
        """Planner returns no-queries when search_queries is empty list."""
        with patch("source_radar.llm._call_model", return_value={
            "output": [{"content": [{"text": json.dumps({
                "research_type": "general",
                "subquestions": [{"id": "q1", "question": "test"}],
                "search_queries": [],
            })}]}]}):
            plan, status = plan_research(
                endpoint="http://127.0.0.1:9317/v1/responses",
                headers={},
                model="test",
                query="test",
                ready_tools=["search"],
                local_services_enabled=False,
            )
        self.assertEqual(status, "no-queries")
        self.assertEqual(plan["search_queries"], ["test"])

    def test_synthesis_error_returns_ai_error(self):
        """Synthesis failure returns ai-error status."""
        syn, status = synthesize_research(
            endpoint="http://127.0.0.1:9317/v1/responses",
            headers={},
            model="test",
            query="test",
            evidence=[],
            subquestions=[],
        )
        self.assertEqual(status, "ai-error")
        self.assertIn("gaps", syn)
        self.assertIn("synthesis failed", syn["gaps"][0])


class ResearchReportTests(unittest.TestCase):
    def test_max_rounds_v1_locked(self):
        """--max-rounds is accepted, multi_round_enabled is always False in v1."""
        from source_radar.agent import VerificationAgent
        agent = VerificationAgent()
        report = agent.research("test", max_rounds=3, local_services=False)
        self.assertEqual(report.requested_max_rounds, 3)
        self.assertFalse(report.multi_round_enabled)
        self.assertEqual(report.status, "ai-error")

    def test_research_cli_help_shows_command(self):
        import subprocess
        import sys
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "source_radar", "research", "--help"],
            capture_output=True, encoding="utf-8", errors="replace",
            env=env, check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("research", result.stdout)
        self.assertIn("max-rounds", result.stdout)
