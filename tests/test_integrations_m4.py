import json
import os
import tempfile
import unittest
from unittest.mock import patch

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
        self.assertEqual(by_name["searxng"].license, "AGPL-3.0")
        self.assertEqual(by_name["searxng"].core_policy, "required-bridge")

    def test_license_audit_flags_restricted_integrations(self):
        audit = audit_integrations()

        self.assertEqual(audit.status, "restricted")
        self.assertEqual(audit.summary["total"], "2")
        self.assertEqual(audit.summary["restricted"], "1")
        self.assertEqual(audit.summary["required"], "1")

    def test_integration_audit_json_is_machine_readable(self):
        payload = json.loads(render_integration_audit_json(audit_integrations()))

        self.assertEqual(payload["summary"]["restricted"], "1")
        self.assertEqual(payload["summary"]["required"], "1")
        self.assertEqual(payload["items"][0]["source"], "external-project")
        self.assertIn("must not be vendored", payload["items"][0]["boundary"])

    def test_integration_audit_markdown_lists_boundaries(self):
        markdown = render_integration_audit_markdown(audit_integrations())

        self.assertIn("# Integration License Audit", markdown)
        self.assertIn("mediacrawler", markdown)
        self.assertIn("searxng", markdown)

    def test_integration_status_reports_disabled_optional_bridges(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                report = build_integration_status_report()

        self.assertEqual(report.status, "missing-required")
        self.assertEqual(report.summary["disabled"], "1")
        self.assertEqual(report.summary["required-missing"], "1")


if __name__ == "__main__":
    unittest.main()
