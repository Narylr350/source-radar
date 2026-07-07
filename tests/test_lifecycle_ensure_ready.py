"""Test BackendLifecycleManager.ensure_ready — unified lazy-start."""
import pathlib
import subprocess
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
            backend_type="service", lifecycle_policy="on-demand",
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

    def test_ensure_ready_uses_project_root_as_subprocess_cwd(self):
        """Lifecycle subprocess must run in the registry's project root."""
        reg = _make_registry()
        root = pathlib.Path("D:/repo/source-radar")
        mgr = BackendLifecycleManager(reg, project_root=root)
        with patch("source_radar.backends.lifecycle.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("source_radar.health.BridgeHealth.check") as mock_health:
                mock_health.return_value = MagicMock(status="ok")
                result = mgr.ensure_ready("searxng")
        self.assertTrue(result)
        self.assertEqual(mock_run.call_args.kwargs["cwd"], str(root))
        mock_health.assert_called_once_with("searxng", project_root=root)

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

    def test_ensure_ready_respects_searxng_specific_autostart_disable(self):
        """The old SearXNG-specific switch remains compatible for SearXNG."""
        reg = _make_registry()
        mgr = BackendLifecycleManager(reg)
        with patch.dict("os.environ", {"SOURCE_RADAR_SEARXNG_AUTOSTART": "0"}, clear=False):
            with patch("source_radar.backends.lifecycle.subprocess.run") as mock_run:
                result = mgr.ensure_ready("searxng")
        self.assertFalse(result)
        mock_run.assert_not_called()

    def test_ensure_ready_recovers_after_cooldown_expires(self):
        """After cooldown expires, ensure_ready retries the start."""
        reg = _make_registry()
        mgr = BackendLifecycleManager(reg)
        import time
        now = time.time()
        # Cooldown expired in the past
        reg.get("searxng").cooling_down_until = now - 1
        reg.get("searxng").lifecycle_state = "cooling_down"
        with patch("source_radar.backends.lifecycle.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("source_radar.health.BridgeHealth.check") as mock_health:
                mock_health.return_value = MagicMock(status="ok")
                result = mgr.ensure_ready("searxng")
        self.assertTrue(result)
        mock_run.assert_called_once()
        self.assertEqual(reg.get("searxng").lifecycle_state, "ready")
        self.assertIsNone(reg.get("searxng").cooling_down_until)

    def test_ensure_ready_fails_when_health_check_unhealthy_after_start(self):
        """If start succeeds but health check returns error, record start-timeout failure."""
        reg = _make_registry()
        mgr = BackendLifecycleManager(reg)
        with patch("source_radar.backends.lifecycle.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("source_radar.health.BridgeHealth.check") as mock_health:
                mock_health.return_value = MagicMock(status="error")
                result = mgr.ensure_ready("searxng")
        self.assertFalse(result)
        mock_run.assert_called_once()
        self.assertEqual(reg.get("searxng").lifecycle_state, "cooling_down")
        self.assertEqual(reg.get("searxng").diagnostics.reason, "start-timeout")
        self.assertIn("error", reg.get("searxng").diagnostics.message)

    def test_ensure_ready_handles_subprocess_timeout(self):
        """If subprocess.run raises TimeoutExpired, record start-failed."""
        reg = _make_registry()
        mgr = BackendLifecycleManager(reg)
        with patch("source_radar.backends.lifecycle.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="engine", timeout=45)
            result = mgr.ensure_ready("searxng")
        self.assertFalse(result)
        self.assertEqual(reg.get("searxng").lifecycle_state, "cooling_down")
        self.assertEqual(reg.get("searxng").diagnostics.reason, "start-failed")

    def test_expire_idle_then_ensure_ready_restarts(self):
        """After idle timeout stops a ready backend, ensure_ready can restart it."""
        reg = _make_registry()
        mgr = BackendLifecycleManager(reg)
        import time
        now = time.time()
        # Backend was ready with warm lease that has expired
        backend = reg.get("searxng")
        backend.ready = True
        backend.lifecycle_state = "ready"
        backend.warm_lease_until = now - 1
        # Expire idle
        mgr.expire_idle(now=now)
        self.assertFalse(backend.ready)
        self.assertEqual(backend.lifecycle_state, "cooling_down")
        # ensure_ready should restart it (no active cooldown)
        with patch("source_radar.backends.lifecycle.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("source_radar.health.BridgeHealth.check") as mock_health:
                mock_health.return_value = MagicMock(status="ok")
                result = mgr.ensure_ready("searxng")
        self.assertTrue(result)
        self.assertEqual(backend.lifecycle_state, "ready")


if __name__ == "__main__":
    unittest.main()
