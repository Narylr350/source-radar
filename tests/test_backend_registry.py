import asyncio
import pathlib
import tempfile
import unittest
from unittest.mock import patch


class BackendRegistryTests(unittest.TestCase):
    def test_default_registry_records_backend_contract_fields(self):
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            registry = build_default_registry(pathlib.Path(directory))
            searxng = registry.get("search.searxng")

        self.assertEqual(searxng.backend_type, "service")
        self.assertEqual(searxng.lifecycle_policy, "warm")
        self.assertEqual(searxng.lifecycle_state, "stopped")
        self.assertFalse(searxng.ready)
        self.assertGreater(searxng.start_budget_seconds, 0)
        self.assertGreater(searxng.idle_timeout_seconds, 0)
        self.assertIn(".source-radar", searxng.install.target_path)
        self.assertEqual(searxng.install.legacy_path, "external/searxng")

    def test_registry_snapshot_is_structured_for_cli_and_mcp_status(self):
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            snapshot = build_default_registry(pathlib.Path(directory)).snapshot()

        keys = {item["key"] for item in snapshot}
        self.assertIn("search.searxng", keys)
        self.assertIn("community.mediacrawler", keys)
        searxng = next(item for item in snapshot if item["key"] == "search.searxng")
        self.assertEqual(searxng["backend_type"], "service")
        self.assertEqual(searxng["lifecycle_policy"], "warm")
        self.assertIn("install", searxng)
        self.assertIn("diagnostics", searxng)


class BackendLifecycleManagerTests(unittest.TestCase):
    def test_ready_warm_backend_enters_cooling_down_after_idle_timeout(self):
        from source_radar.backends.lifecycle import BackendLifecycleManager
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            registry = build_default_registry(pathlib.Path(directory))
            manager = BackendLifecycleManager(registry)
            manager.mark_ready("search.searxng", now=100.0)
            manager.expire_idle(now=100.0 + registry.get("search.searxng").idle_timeout_seconds + 1)
            searxng = registry.get("search.searxng")

        self.assertEqual(searxng.lifecycle_state, "cooling_down")
        self.assertFalse(searxng.ready)
        self.assertEqual(searxng.diagnostics.reason, "idle-timeout")
        self.assertIn("fallback", searxng.fallback)

    def test_failure_opens_cooling_down_window_with_diagnostics(self):
        from source_radar.backends.lifecycle import BackendLifecycleManager
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            registry = build_default_registry(pathlib.Path(directory))
            manager = BackendLifecycleManager(registry)
            manager.record_failure(
                "community.mediacrawler",
                reason="start-timeout",
                message="启动超时",
                fix="运行 engine status 查看详情",
                now=10.0,
                cooldown_seconds=30,
            )
            backend = registry.get("community.mediacrawler")

        self.assertEqual(backend.lifecycle_state, "cooling_down")
        self.assertEqual(backend.status, "failed")
        self.assertFalse(backend.ready)
        self.assertEqual(backend.cooling_down_until, 40.0)
        self.assertEqual(backend.diagnostics.reason, "start-timeout")
        self.assertEqual(backend.diagnostics.fix, "运行 engine status 查看详情")


class BackendStatusIntegrationTests(unittest.TestCase):
    def test_engine_list_includes_registry_metadata(self):
        from source_radar import engine

        with patch("source_radar.engine._check_library", return_value=("ready", "已安装")):
            with patch("source_radar.engine._check_service", return_value=("stopped", "服务未启动")):
                with patch("source_radar.engine._check_searxng_engine", return_value=("stopped", "SearXNG 已安装")):
                    engines = engine.list_engines()

        searxng = next(item for item in engines if item["key"] == "searxng")
        self.assertEqual(searxng["backend_key"], "search.searxng")
        self.assertEqual(searxng["backend_type"], "service")
        self.assertEqual(searxng["lifecycle_policy"], "warm")
        self.assertEqual(searxng["lifecycle_state"], "stopped")
        self.assertIn("install", searxng)

    def test_source_status_includes_backend_registry_snapshot(self):
        from source_radar.mcp.server import handle_source_status
        from source_radar.models import HealthStatus

        def fake_check(name):
            return HealthStatus(
                name=name,
                status="missing",
                reason="endpoint-unresolved",
                message="missing",
            )

        async def run():
            return await handle_source_status({})

        with patch("source_radar.health.BridgeHealth.check", side_effect=fake_check):
            with patch("source_radar.cache.cache_status", return_value={"entry_count": 0, "total_bytes": 0}):
                with patch("source_radar.engine._check_library", return_value=("ready", "已安装")):
                    with patch("source_radar.engine._check_service", return_value=("stopped", "服务未启动")):
                        with patch("source_radar.engine._check_searxng_engine", return_value=("stopped", "SearXNG 未启动")):
                            result = asyncio.run(run())

        text = result.content[0].text
        self.assertIn("backend_registry:", text)
        self.assertIn("search.searxng", text)
        self.assertIn("policy=warm", text)
        self.assertIn("type=service", text)


if __name__ == "__main__":
    unittest.main()
