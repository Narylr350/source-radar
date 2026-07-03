import contextlib
import io
import sys
import unittest
from unittest.mock import patch


class McpAutostartTests(unittest.TestCase):
    def test_autostart_uses_backend_lifecycle_when_searxng_unhealthy(self):
        from source_radar.mcp import server

        mcp_server_tests = sys.modules.get("tests.test_mcp_server")
        global_patch = getattr(mcp_server_tests, "_patch_ensure", None)
        if global_patch is not None:
            global_patch.stop()

        try:
            server._searxng_last_autostart_time = 0.0
            server._searxng_last_autostart_error = ""
            server._searxng_last_autostart_result = "skipped"

            with patch("source_radar.mcp.server._searxng_search_ready", return_value=(False, "upstream down")):
                with patch("source_radar.mcp.server._ensure_backend_ready", return_value=True) as ensure:
                    with patch("source_radar.engine.run_engine_start") as start:
                        with contextlib.redirect_stderr(io.StringIO()):
                            ok, detail = server._ensure_searxng_for_search()

            self.assertTrue(ok)
            self.assertEqual(detail, "")
            ensure.assert_called_once_with("searxng")
            start.assert_not_called()
            self.assertEqual(server._searxng_last_autostart_result, "ok")
        finally:
            if global_patch is not None:
                global_patch.start()

    def test_autostart_reports_lifecycle_failure_detail(self):
        from source_radar.mcp import server

        mcp_server_tests = sys.modules.get("tests.test_mcp_server")
        global_patch = getattr(mcp_server_tests, "_patch_ensure", None)
        if global_patch is not None:
            global_patch.stop()

        try:
            server._searxng_last_autostart_time = 0.0
            server._searxng_last_autostart_error = ""
            server._searxng_last_autostart_result = "skipped"

            with patch("source_radar.mcp.server._searxng_search_ready", return_value=(False, "still down")):
                with patch("source_radar.mcp.server._ensure_backend_ready", return_value=False):
                    with contextlib.redirect_stderr(io.StringIO()):
                        ok, detail = server._ensure_searxng_for_search()

            self.assertFalse(ok)
            self.assertIn("still down", detail)
            self.assertEqual(server._searxng_last_autostart_result, "failed")
        finally:
            if global_patch is not None:
                global_patch.start()


if __name__ == "__main__":
    unittest.main()
