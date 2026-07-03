"""Test BackendLifecycleManager.ensure_ready — unified lazy-start."""
import unittest
from unittest.mock import patch, MagicMock
from source_radar.backends.registry import BackendRegistry, BackendRecord, BackendInstall, BackendDiagnostics
from source_radar.backends.lifecycle import BackendLifecycleManager


def _make_registry():
    return BackendRegistry([
        BackendRecord(
            key="search.searxng", engine_key="searxng", name="SearXNG",
            backend_type="service", lifecycle_policy="warm",
            install=BackendInstall(source="local-source"),
            start_budget_seconds=45, idle_timeout_seconds=300,
        ),
        BackendRecord(
            key="community.mediacrawler", engine_key="mediacrawler", name="MediaCrawler",
            backend_type="legacy-bridge", lifecycle_policy="on-demand",
            install=BackendInstall(source="local-source"),
            start_budget_seconds=45, idle_timeout_seconds=180,
        ),
    ])


class EnsureReadyTest(unittest.TestCase):
    def test_ensure_ready_when_already_ready(self):
        """If backend is already ready, ensure_ready does nothing."""
        reg = _make_registry()
        mgr = BackendLifecycleManager(reg)
        reg.get("searxng").lifecycle_state = "ready"
        reg.get("searxng").ready = True
        result = mgr.ensure_ready("searxng")
        self.assertTrue(result)

    def test_ensure_ready_starts_stopped_backend(self):
        """If backend is stopped, ensure_ready tries to start it."""
        reg = _make_registry()
        mgr = BackendLifecycleManager(reg)
        with patch("source_radar.backends.lifecycle.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("source_radar.health.BridgeHealth.check") as mock_health:
                mock_health.return_value = MagicMock(status="ok")
                result = mgr.ensure_ready("searxng")
        self.assertTrue(result)
        mock_run.assert_called_once()

    def test_ensure_ready_returns_false_on_start_failure(self):
        """If start fails, ensure_ready returns False and records failure."""
        reg = _make_registry()
        mgr = BackendLifecycleManager(reg)
        with patch("source_radar.backends.lifecycle.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr=b"fail")
            with patch("source_radar.health.BridgeHealth.check") as mock_health:
                mock_health.return_value = MagicMock(status="error")
                result = mgr.ensure_ready("searxng")
        self.assertFalse(result)
        self.assertEqual(reg.get("searxng").lifecycle_state, "cooling_down")
        self.assertEqual(reg.get("searxng").status, "failed")

    def test_ensure_ready_respects_cooldown(self):
        """If backend is in cooldown, ensure_ready returns False without starting."""
        reg = _make_registry()
        mgr = BackendLifecycleManager(reg)
        import time
        now = time.time()
        reg.get("searxng").cooling_down_until = now + 60
        reg.get("searxng").lifecycle_state = "cooling_down"
        with patch("source_radar.backends.lifecycle.subprocess.run") as mock_run:
            result = mgr.ensure_ready("searxng")
        self.assertFalse(result)
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
