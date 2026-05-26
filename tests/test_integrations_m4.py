import json
import os
import tempfile
import unittest
from unittest.mock import patch

from source_radar.config import save_provider_config
from source_radar.integrations import (
    audit_integrations,
    build_integration_status_report,
    list_integrations,
)
from source_radar.reporting import (
    render_integration_audit_json,
    render_integration_audit_markdown,
)


class M4IntegrationTests(unittest.TestCase):
    def test_optional_integrations_are_registered_with_license_boundaries(self):
        integrations = list_integrations()

        by_name = {integration.name: integration for integration in integrations}
        self.assertEqual(by_name["mediacrawler"].license, "Non-commercial learning/research")
        self.assertEqual(by_name["mediacrawler"].core_policy, "external-only")
        self.assertEqual(by_name["firecrawl"].license, "AGPL-3.0")
        self.assertEqual(by_name["firecrawl"].core_policy, "bridge-or-api-only")

    def test_license_audit_flags_restricted_integrations(self):
        audit = audit_integrations()

        self.assertEqual(audit.status, "restricted")
        self.assertEqual(audit.summary["total"], "2")
        self.assertEqual(audit.summary["restricted"], "2")
        self.assertTrue(all(item.status == "restricted" for item in audit.items))

    def test_integration_audit_json_is_machine_readable(self):
        payload = json.loads(render_integration_audit_json(audit_integrations()))

        self.assertEqual(payload["summary"]["restricted"], "2")
        self.assertEqual(payload["items"][0]["source"], "external-project")
        self.assertIn("must not be vendored", payload["items"][0]["boundary"])

    def test_integration_audit_markdown_lists_boundaries(self):
        markdown = render_integration_audit_markdown(audit_integrations())

        self.assertIn("# Integration License Audit", markdown)
        self.assertIn("mediacrawler", markdown)
        self.assertIn("bridge-or-api-only", markdown)

    def test_integration_status_reports_disabled_optional_bridges(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                report = build_integration_status_report()

        self.assertEqual(report.status, "disabled")
        self.assertEqual(report.summary["disabled"], "2")

    def test_integration_status_reports_configured_provider_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
                save_provider_config("firecrawl", endpoint="http://127.0.0.1:3002")
                report = build_integration_status_report()

        by_name = {item.name: item for item in report.items}
        self.assertEqual(report.status, "partial")
        self.assertEqual(report.summary["configured"], "1")
        self.assertEqual(by_name["firecrawl"].status, "configured")
        self.assertEqual(by_name["mediacrawler"].status, "disabled")


if __name__ == "__main__":
    unittest.main()
