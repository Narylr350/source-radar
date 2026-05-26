import json
import os
import tempfile
import unittest
from unittest.mock import patch

from source_radar.acquisition import AcquisitionResult
from source_radar.config import save_openai_config, save_provider_config, clear_openai_config, clear_provider_config
from source_radar.health import build_health_report, probe_adapter
from source_radar.integrations import audit_integrations, build_integration_status_report
from source_radar.models import (
    AcquisitionTrace,
    AgentTrace,
    CandidateSource,
    EvidenceCard,
    HealthReport,
    InformationAnalysis,
    Judgement,
    ProbeResult,
    SynthesisReport,
    VerifyReport,
)
from source_radar.reporting import (
    render_health_json,
    render_integration_audit_json,
    render_json,
    render_probe_json,
    render_synthesis_json,
)
from source_radar.cli import run_config_show


class VerifyJsonContractTests(unittest.TestCase):
    """verify JSON output field contract."""

    def test_minimal_report_has_required_keys(self):
        report = VerifyReport(
            claim="test claim",
            status="evidence-found",
            evidence=[],
            judgement=Judgement(
                status="evidence-found",
                summary="Summary.",
                evidence_ids=[],
                gaps=[],
            ),
        )
        payload = json.loads(render_json(report))

        self.assertIsInstance(payload["claim"], str)
        self.assertIsInstance(payload["status"], str)
        self.assertIsInstance(payload["evidence"], list)
        self.assertIsInstance(payload["judgement"], dict)
        self.assertIsNone(payload.get("agent"))

    def test_report_with_agent_trace_has_acquisition_keys(self):
        report = VerifyReport(
            claim="test",
            status="ai-judged",
            evidence=[],
            judgement=Judgement(
                status="ai-judged",
                summary="Summary.",
                evidence_ids=[],
                gaps=[],
                confidence="high",
                confidence_reason="Multiple sources agree.",
            ),
            agent=AgentTrace(
                mode="agent",
                ai_status="configured",
                model="test-model",
                planned_tools=["search", "fixture"],
                tool_calls=[{"tool": "search", "status": "ok"}],
                acquisition=[
                    AcquisitionTrace(
                        provider="search",
                        provider_type="search",
                        status="ok",
                        reason="candidates-found",
                        message="Found candidates.",
                        candidate_count=3,
                        items_found=2,
                        candidates=[
                            CandidateSource(
                                title="Result",
                                url="https://example.test",
                                provider="search",
                                snippet="Snippet text.",
                            )
                        ],
                        fix="",
                        retryable=False,
                        warnings=[],
                        evidence_gaps=[],
                        diagnostics={},
                    )
                ],
            ),
        )
        payload = json.loads(render_json(report))

        agent = payload["agent"]
        self.assertEqual(agent["mode"], "agent")
        self.assertEqual(agent["ai_status"], "configured")
        self.assertIn("search", agent["planned_tools"])

        acq = agent["acquisition"][0]
        for key in (
            "provider", "provider_type", "status", "reason", "message",
            "candidate_count", "items_found", "candidates",
            "fix", "retryable", "warnings", "evidence_gaps", "diagnostics",
        ):
            self.assertIn(key, acq, f"acquisition trace missing key: {key}")

        candidate = acq["candidates"][0]
        for key in ("title", "url", "provider", "snippet", "source_type", "metadata"):
            self.assertIn(key, candidate)

    def test_evidence_card_has_all_keys(self):
        card = EvidenceCard(
            id="ev-001",
            source_type="web-page",
            title="Title",
            url="https://example.test",
            summary="Summary.",
            adapter="trafilatura",
            retrieved_at="2026-01-01T00:00:00Z",
            content_hash="abc123",
            metadata={"author": "test"},
        )
        report = VerifyReport(
            claim="test",
            status="evidence-found",
            evidence=[card],
            judgement=Judgement(
                status="evidence-found",
                summary="Summary.",
                evidence_ids=["ev-001"],
                gaps=[],
            ),
        )
        payload = json.loads(render_json(report))

        evidence = payload["evidence"][0]
        for key in (
            "id", "source_type", "title", "url", "summary",
            "adapter", "retrieved_at", "content_hash", "metadata",
        ):
            self.assertIn(key, evidence, f"evidence card missing key: {key}")

    def test_judgement_default_confidence_is_unknown(self):
        report = VerifyReport(
            claim="test",
            status="evidence-found",
            evidence=[],
            judgement=Judgement(
                status="evidence-found",
                summary="Summary.",
                evidence_ids=[],
                gaps=[],
            ),
        )
        payload = json.loads(render_json(report))
        self.assertEqual(payload["judgement"]["confidence"], "unknown")
        self.assertEqual(payload["judgement"]["confidence_reason"], "")

    def test_acquisition_error_has_all_fields(self):
        """error status preserves fix, retryable, diagnostics through agent trace."""
        report = VerifyReport(
            claim="test",
            status="ai-judged",
            evidence=[],
            judgement=Judgement(
                status="ai-judged",
                summary="Summary.",
                evidence_ids=[],
                gaps=[],
            ),
            agent=AgentTrace(
                mode="agent",
                ai_status="configured",
                model="test-model",
                planned_tools=["mediacrawler"],
                tool_calls=[],
                acquisition=[
                    AcquisitionTrace(
                        provider="mediacrawler",
                        provider_type="external-bridge",
                        status="needs-input",
                        reason="missing-cookies",
                        message="No cookies configured.",
                        fix="source-radar config setup",
                        retryable=False,
                    )
                ],
            ),
        )
        payload = json.loads(render_json(report))
        acq = payload["agent"]["acquisition"][0]
        self.assertEqual(acq["status"], "needs-input")
        self.assertEqual(acq["reason"], "missing-cookies")
        self.assertTrue(acq["fix"])


class SynthesisJsonContractTests(unittest.TestCase):
    """ask JSON output field contract."""

    def test_minimal_synthesis_has_required_keys(self):
        report = SynthesisReport(
            query="test query",
            status="ok",
            evidence=[],
            analysis=InformationAnalysis(
                summary="Summary.",
                key_points=[],
                source_notes=[],
                disagreements=[],
                noise_notes=[],
            ),
        )
        payload = json.loads(render_synthesis_json(report))

        self.assertIsInstance(payload["query"], str)
        self.assertIsInstance(payload["status"], str)
        self.assertIsInstance(payload["evidence"], list)
        self.assertIsInstance(payload["analysis"], dict)
        self.assertIsNone(payload.get("agent"))

        analysis = payload["analysis"]
        for key in ("summary", "key_points", "source_notes", "disagreements", "noise_notes"):
            self.assertIn(key, analysis, f"analysis missing key: {key}")

    def test_synthesis_with_agent_trace_includes_acquisition(self):
        report = SynthesisReport(
            query="test",
            status="ok",
            evidence=[],
            analysis=InformationAnalysis(
                summary="Summary.",
                key_points=["Point 1"],
                source_notes=["Source note"],
                disagreements=[],
                noise_notes=["Noise"],
            ),
            agent=AgentTrace(
                mode="agent",
                ai_status="configured",
                model="test-model",
                planned_tools=["search"],
                tool_calls=[],
                acquisition=[
                    AcquisitionTrace(
                        provider="search",
                        provider_type="search",
                        status="ok",
                        reason="candidates-found",
                        message="Found.",
                        candidate_count=1,
                        items_found=0,
                    )
                ],
            ),
        )
        payload = json.loads(render_synthesis_json(report))

        self.assertIsNotNone(payload["agent"])
        acq = payload["agent"]["acquisition"][0]
        self.assertEqual(acq["provider"], "search")
        self.assertEqual(payload["analysis"]["key_points"], ["Point 1"])
        self.assertEqual(payload["analysis"]["noise_notes"], ["Noise"])


class ProbeJsonContractTests(unittest.TestCase):
    """probe JSON output field contract."""

    def test_ok_probe_has_all_required_keys(self):
        result = ProbeResult(
            adapter="search",
            status="ok",
            reason="configured",
            message="Provider is ready.",
            checked_at="2026-01-01T00:00:00Z",
            source_type="search-result",
            items_found=3,
            details={"provider_type": "search", "candidate_count": "5"},
        )
        payload = json.loads(render_probe_json(result))

        for key in (
            "adapter", "status", "reason", "message", "checked_at",
            "source_type", "items_found", "details",
        ):
            self.assertIn(key, payload, f"probe result missing key: {key}")
        self.assertIsInstance(payload["details"], dict)

    def test_needs_input_probe_has_no_source_type(self):
        result = ProbeResult(
            adapter="web",
            status="needs-input",
            reason="missing-url",
            message="--url is required.",
            checked_at="2026-01-01T00:00:00Z",
        )
        payload = json.loads(render_probe_json(result))
        self.assertEqual(payload["source_type"], "")
        self.assertEqual(payload["items_found"], 0)

    def test_provider_probe_includes_fix_and_retryability(self):
        """Probe from ExternalBridgeProvider.status() surfaces fix info."""
        from source_radar.acquisition import ExternalBridgeProvider

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                result = probe_adapter(
                    "firecrawl",
                    providers=[ExternalBridgeProvider("firecrawl", "SOURCE_RADAR_FIRECRAWL_ENDPOINT")],
                )

        payload = json.loads(render_probe_json(result))

        self.assertIn("status", payload)
        self.assertIn("checked_at", payload)
        self.assertIsInstance(payload["details"], dict)
        self.assertIn("provider_type", payload["details"])
        self.assertEqual(payload["details"]["provider_type"], "external-bridge")


class HealthJsonContractTests(unittest.TestCase):
    """health JSON output field contract."""

    def test_health_report_has_required_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                report = build_health_report()

        payload = json.loads(render_health_json(report))

        self.assertIn("status", payload)
        self.assertIn("checked_at", payload)
        self.assertIn("summary", payload)
        self.assertIn("probes", payload)
        self.assertIsInstance(payload["probes"], list)
        self.assertIn("total", payload["summary"])

        for probe in payload["probes"]:
            for key in (
                "adapter", "status", "reason", "message", "checked_at",
                "source_type", "items_found", "details",
            ):
                self.assertIn(key, probe, f"health probe missing key: {key}")


class IntegrationJsonContractTests(unittest.TestCase):
    """integrations audit JSON output field contract."""

    def test_audit_json_has_required_keys(self):
        payload = json.loads(render_integration_audit_json(audit_integrations()))

        self.assertIn("status", payload)
        self.assertIn("summary", payload)
        self.assertIn("items", payload)
        self.assertIsInstance(payload["items"], list)

        for item in payload["items"]:
            for key in ("name", "source", "license", "core_policy", "status", "boundary", "notice"):
                self.assertIn(key, item, f"integration item missing key: {key}")


class ConfigJsonContractTests(unittest.TestCase):
    """config show JSON output field contract."""

    def test_config_show_has_required_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {
                "SOURCE_RADAR_CONFIG_DIR": directory,
                "FIRECRAWL_TRANSPORT": "",
                "FIRECRAWL_API_KEY": "",
            }):
                save_openai_config(api_key="test-key", endpoint="https://example.test", model="test-model")
                save_provider_config("firecrawl", endpoint="http://127.0.0.1:3002", enabled=True)
                payload = json.loads(run_config_show())

        self.assertIn("openai", payload)
        self.assertIn("providers", payload)
        self.assertIn("bridges", payload)
        self.assertIn("firecrawl", payload["bridges"])
        self.assertIn("mediacrawler", payload["bridges"])
        self.assertIn("configured", payload["openai"])
        self.assertIn("api_key", payload["openai"])
        self.assertIn("endpoint", payload["openai"])
        self.assertIn("model", payload["openai"])
        self.assertIsInstance(payload["providers"], dict)

    def test_config_secrets_are_masked(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                save_openai_config(api_key="sk-1234567890abcdef", endpoint="https://api.openai.com/", model="gpt-4")
                payload = json.loads(run_config_show())

        self.assertNotIn("sk-1234567890abcdef", payload["openai"]["api_key"])
        self.assertIn("...", payload["openai"]["api_key"])

    def test_empty_config_has_no_api_key(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                clear_openai_config()
                payload = json.loads(run_config_show())

        self.assertFalse(payload["openai"]["configured"])
        self.assertEqual(payload["openai"]["api_key"], "")


class ProviderJsonContractTests(unittest.TestCase):
    """External bridge collect JSON contract through the ExternalBridgeProvider path."""

    def test_bridge_collect_error_payload_preserves_diagnostics(self):
        """External bridge error responses keep diagnostics keys as strings."""
        from source_radar.acquisition import ExternalBridgeProvider

        payload = {
            "status": "no-evidence",
            "reason": "no-usable-items",
            "message": "No results.",
            "diagnostics": {"query_hash": "abc", "milliseconds": "1234"},
            "items": [],
        }

        class Response:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps(payload).encode("utf-8")

        with patch.dict(os.environ, {"SOURCE_RADAR_FIRECRAWL_ENDPOINT": "https://bridge.test"}, clear=True):
            with patch("source_radar.acquisition.urlopen", return_value=Response()):
                result = ExternalBridgeProvider(
                    "firecrawl",
                    env_var="SOURCE_RADAR_FIRECRAWL_ENDPOINT",
                ).collect(type("Request", (), {"query": "test", "limit": 5})())

        self.assertEqual(result.diagnostics["query_hash"], "abc")
        self.assertEqual(result.diagnostics["milliseconds"], "1234")

    def test_bridge_collect_success_preserves_all_list_fields(self):
        from source_radar.acquisition import ExternalBridgeProvider

        payload = {
            "status": "ok",
            "reason": "items-found",
            "message": "Found.",
            "warnings": ["Rate limited."],
            "evidence_gaps": ["No login-gated content."],
            "diagnostics": {"source": "firecrawl"},
            "items": [
                {
                    "title": "Bridge Item",
                    "url": "https://example.test/bridge",
                    "snippet": "Bridge evidence.",
                    "source_type": "web-page",
                }
            ],
        }

        class Response:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps(payload).encode("utf-8")

        with patch.dict(os.environ, {"SOURCE_RADAR_FIRECRAWL_ENDPOINT": "https://bridge.test"}, clear=True):
            with patch("source_radar.acquisition.urlopen", return_value=Response()):
                result = ExternalBridgeProvider(
                    "firecrawl",
                    env_var="SOURCE_RADAR_FIRECRAWL_ENDPOINT",
                ).collect(type("Request", (), {"query": "test", "limit": 5})())

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.warnings, ["Rate limited."])
        self.assertEqual(result.evidence_gaps, ["No login-gated content."])
        self.assertFalse(result.retryable)  # success is not retryable


if __name__ == "__main__":
    unittest.main()
