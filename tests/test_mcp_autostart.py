import sys
import unittest
from unittest.mock import patch


class McpAutostartTests(unittest.TestCase):
    def _mcp_server_global_patch(self):
        module = sys.modules.get("tests.test_mcp_server") or sys.modules.get("test_mcp_server")
        return getattr(module, "_patch_ensure", None)

    def test_autostart_uses_backend_lifecycle_when_searxng_unhealthy(self):
        from source_radar.mcp import server

        global_patch = self._mcp_server_global_patch()
        if global_patch is not None:
            global_patch.stop()

        try:
            with patch("source_radar.mcp.server._searxng_search_ready", return_value=(False, "upstream down")):
                with patch("source_radar.mcp.server._ensure_backend_ready", return_value=True) as ensure:
                    with patch("source_radar.engine.run_engine_start") as start:
                        ok, detail = server._ensure_searxng_for_search()

            self.assertTrue(ok)
            self.assertEqual(detail, "")
            ensure.assert_called_once_with("searxng")
            start.assert_not_called()
        finally:
            if global_patch is not None:
                global_patch.start()

    def test_autostart_reports_lifecycle_failure_detail(self):
        from source_radar.mcp import server

        global_patch = self._mcp_server_global_patch()
        if global_patch is not None:
            global_patch.stop()

        try:
            with patch("source_radar.mcp.server._searxng_search_ready", return_value=(False, "still down")):
                with patch("source_radar.mcp.server._ensure_backend_ready", return_value=False):
                    ok, detail = server._ensure_searxng_for_search()

            self.assertFalse(ok)
            self.assertIn("still down", detail)
        finally:
            if global_patch is not None:
                global_patch.start()


if __name__ == "__main__":
    unittest.main()
