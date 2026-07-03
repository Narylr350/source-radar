"""Test BackendLifecycleManager.ensure_ready — unified lazy-start."""
import unittest
from unittest.mock import patch, MagicMock
from source_radar.backends.registry import BackendRegistry, BackendRecord, BackendInstall
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
        """If engine start exits non-zero, ensure_ready records stderr diagnostics."""
        reg = _make_registry()
        mgr = BackendLifecycleManager(reg)
        with patch("source_radar.backends.lifecycle.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=b"out", stderr=b"boom")
            with patch("source_radar.health.BridgeHealth.check") as mock_health:
                result = mgr.ensure_ready("searxng")
        self.assertFalse(result)
        mock_health.assert_not_called()
        self.assertEqual(reg.get("searxng").lifecycle_state, "cooling_down")
        self.assertEqual(reg.get("searxng").status, "failed")
        self.assertEqual(reg.get("searxng").diagnostics.reason, "start-failed")
        self.assertIn("boom", reg.get("searxng").diagnostics.message)

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

    def test_ensure_ready_respects_generic_autostart_disable_for_any_backend(self):
        """The generic backend autostart switch disables non-SearXNG backends too."""
        reg = _make_registry()
        mgr = BackendLifecycleManager(reg)
        with patch.dict("os.environ", {"SOURCE_RADAR_BACKEND_AUTOSTART": "0"}, clear=False):
            with patch("source_radar.backends.lifecycle.subprocess.run") as mock_run:
                result = mgr.ensure_ready("mediacrawler")
        self.assertFalse(result)
        mock_run.assert_not_called()

    def test_ensure_ready_keeps_legacy_searxng_autostart_disable(self):
        """The old SearXNG-specific switch remains compatible for SearXNG."""
        reg = _make_registry()
        mgr = BackendLifecycleManager(reg)
        with patch.dict("os.environ", {"SOURCE_RADAR_SEARXNG_AUTOSTART": "0"}, clear=False):
            with patch("source_radar.backends.lifecycle.subprocess.run") as mock_run:
                result = mgr.ensure_ready("searxng")
        self.assertFalse(result)
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
