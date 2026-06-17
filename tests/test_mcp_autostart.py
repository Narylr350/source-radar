import contextlib
import io
import sys
import unittest
from unittest.mock import patch


class McpAutostartTests(unittest.TestCase):
    def test_autostart_runs_when_bridge_alive_but_searxng_unhealthy(self):
        from source_radar.acquisition import AcquisitionResult
        from source_radar.mcp import server

        mcp_server_tests = sys.modules.get("tests.test_mcp_server")
        global_patch = getattr(mcp_server_tests, "_patch_ensure", None)
        if global_patch is not None:
            global_patch.stop()

        try:
            server._searxng_last_autostart_time = 0.0
            server._searxng_last_autostart_error = ""
            server._searxng_last_autostart_result = "skipped"

            unhealthy = AcquisitionResult(
                provider="searxng",
                provider_type="external-bridge",
                status="error",
                reason="service-unreachable",
                message="upstream down",
            )
            healthy = AcquisitionResult(
                provider="searxng",
                provider_type="external-bridge",
                status="degraded",
                reason="captcha-suspended",
                message="usable with warnings",
            )

            with patch("source_radar.mcp.server.ExternalBridgeProvider") as provider:
                provider.return_value.status.side_effect = [unhealthy, healthy]
                with patch("source_radar.engine.run_engine_start", return_value="started") as start:
                    with contextlib.redirect_stderr(io.StringIO()):
                        ok, detail = server._ensure_searxng_for_search()

            self.assertTrue(ok)
            self.assertEqual(detail, "")
            start.assert_called_once_with("searxng")
        finally:
            if global_patch is not None:
                global_patch.start()


if __name__ == "__main__":
    unittest.main()
