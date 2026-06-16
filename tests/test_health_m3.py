import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from source_radar.acquisition import AcquisitionResult
from source_radar.health import build_health_report, probe_adapter
from source_radar.models import HealthReport, ProbeResult
from source_radar.reporting import (
    render_health_json,
    render_health_markdown,
)


class M3HealthTests(unittest.TestCase):
    def test_probe_web_adapter_reports_ok_with_local_page(self):
        with tempfile.TemporaryDirectory() as directory:
            page = pathlib.Path(directory) / "page.html"
            page.write_text(
                "<html><head><title>Probe Page</title></head>"
                "<body><p>Probe evidence content.</p></body></html>",
                encoding="utf-8",
            )

            result = probe_adapter("web", url=page.as_uri())

        self.assertEqual(result.adapter, "web")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.source_type, "web-page")
        self.assertEqual(result.items_found, 1)

    def test_probe_missing_url_reports_needs_input(self):
        result = probe_adapter("official")

        self.assertEqual(result.adapter, "official")
        self.assertEqual(result.status, "needs-input")
        self.assertEqual(result.reason, "missing-url")

    def test_probe_empty_page_reports_no_evidence(self):
        result = probe_adapter(
            "web",
            url="https://example.test/empty",
            html="<html><head><title>Empty</title></head><body></body></html>",
        )

        self.assertEqual(result.status, "no-evidence")
        self.assertEqual(result.items_found, 0)
        self.assertEqual(result.reason, "no-usable-items")

    def test_health_report_summarizes_all_adapters(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {
                "SOURCE_RADAR_CONFIG_DIR": directory,
            }):
                report = build_health_report()

        adapters = [probe.adapter for probe in report.probes]
        self.assertEqual(adapters, [
            "fixture",
            "web",
            "official",
            "github",
            "github-search",
            "search",
            "search-baidu",
            "trafilatura",
            "crawl4ai",
            "searxng",
            "mediacrawler",
        ])
        self.assertEqual(report.summary["total"], "11")
        self.assertIn(report.summary.get("disabled", "0"), ("0", "1", "2"))
        counted = sum(
            int(value)
            for key, value in report.summary.items()
            if key != "total"
        )
        self.assertEqual(counted, 11)

    def test_health_renderers_are_machine_and_human_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                report = build_health_report()
        payload = json.loads(render_health_json(report))
        markdown = render_health_markdown(report)

        self.assertEqual(payload["summary"]["total"], "11")
        self.assertIn("fixture", markdown)
        self.assertIn("search", markdown)
        self.assertIn("needs-input", markdown)

    def test_probe_provider_reports_acquisition_readiness(self):
        class FakeProvider:
            provider = "search"
            provider_type = "search"

            def collect(self, request):
                return AcquisitionResult(
                    provider="search",
                    provider_type="search",
                    status="ok",
                    reason="configured",
                    message="Provider is ready.",
                )

        result = probe_adapter("search", query="claim", providers=[FakeProvider()])

        self.assertEqual(result.adapter, "search")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.reason, "configured")
        self.assertEqual(result.details["provider_type"], "search")

    def test_probe_propagates_bridge_degraded_diagnostics(self):
        class FakeSearxngProvider:
            provider = "searxng"
            provider_type = "external-bridge"

            def collect(self, request):
                return AcquisitionResult(
                    provider="searxng",
                    provider_type="external-bridge",
                    status="no-evidence",
                    reason="no-usable-items",
                    message="No usable items.",
                    fix="等待 CAPTCHA 解除",
                    warnings=["CAPTCHA 暂停: google"],
                    diagnostics={"captcha_engines": "google"},
                )

        result = probe_adapter("searxng", query="test", providers=[FakeSearxngProvider()])

        self.assertEqual(result.status, "no-evidence")
        self.assertEqual(result.details["fix"], "等待 CAPTCHA 解除")
        self.assertIn("google", result.details["captcha_engines"])

    def test_health_markdown_shows_fix_hint_for_degraded_probe(self):
        report = HealthReport(
            status="degraded",
            checked_at="2026-01-01T00:00:00",
            summary={"total": "1", "no-evidence": "1"},
            probes=[
                ProbeResult(
                    adapter="searxng",
                    status="no-evidence",
                    reason="no-usable-items",
                    message="No items.",
                    checked_at="2026-01-01T00:00:00",
                    details={"fix": "等待 CAPTCHA 解除", "captcha_engines": "google"},
                ),
            ],
        )
        markdown = render_health_markdown(report)

        self.assertIn("fix: 等待 CAPTCHA 解除", markdown)
        self.assertIn("captcha_engines: google", markdown)


if __name__ == "__main__":
    unittest.main()
