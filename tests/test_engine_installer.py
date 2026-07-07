import json
import pathlib
import tempfile
import unittest


class EngineInstallerTests(unittest.TestCase):
    def test_prepare_layout_uses_source_radar_downloads_engines_and_metadata(self):
        from source_radar.backends.installer import EngineInstaller
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            installer = EngineInstaller(build_default_registry(root), root)
            plan = installer.prepare_layout("search.searxng")

            self.assertEqual(plan.backend_key, "search.searxng")
            self.assertEqual(plan.engine_key, "searxng")
            self.assertEqual(plan.source_path, root / ".source-radar" / "engines" / "searxng" / "source")
            self.assertEqual(plan.venv_path, root / ".source-radar" / "engines" / "searxng" / "source" / ".venv")
            self.assertEqual(plan.metadata_path, root / ".source-radar" / "engines" / "searxng" / "metadata.json")
            self.assertEqual(plan.downloads_root, root / ".source-radar" / "downloads")
            self.assertTrue((root / ".source-radar" / "downloads" / "archives").is_dir())
            self.assertTrue((root / ".source-radar" / "downloads" / "wheels").is_dir())
            self.assertTrue((root / ".source-radar" / "downloads" / "manifests").is_dir())
            self.assertTrue(plan.engine_dir.is_dir())

    def test_resolve_source_ignores_external_checkout_and_requires_target(self):
        from source_radar.backends.installer import EngineInstaller
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            registry = build_default_registry(root)
            installer = EngineInstaller(registry, root)
            legacy = root / "external" / "MediaCrawler"
            legacy.mkdir(parents=True)

            resolved = installer.resolve_source("community.mediacrawler")

            target = root / ".source-radar" / "engines" / "mediacrawler" / "source"
            self.assertEqual(resolved.path, target)
            self.assertEqual(resolved.reason, "missing")

            target.mkdir(parents=True)
            resolved = installer.resolve_source("community.mediacrawler")

            self.assertEqual(resolved.path, target)
            self.assertEqual(resolved.reason, "target")

    def test_write_metadata_records_backend_download_paths_without_legacy(self):
        from source_radar.backends.installer import EngineInstaller
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            installer = EngineInstaller(build_default_registry(root), root)

            metadata = installer.write_metadata(
                "search.searxng",
                source="local-source",
                version="2026.7.3",
                commit="abc123",
                archive_name="searxng-2026.7.3.zip",
            )

            path = root / ".source-radar" / "engines" / "searxng" / "metadata.json"
            self.assertTrue(path.is_file())
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved, metadata)
            self.assertEqual(saved["backend_key"], "search.searxng")
            self.assertEqual(saved["engine_key"], "searxng")
            self.assertEqual(saved["source"], "local-source")
            self.assertEqual(saved["version"], "2026.7.3")
            self.assertEqual(saved["commit"], "abc123")
            self.assertIn(".source-radar/downloads/archives/searxng-2026.7.3.zip", saved["archive_path"])
            self.assertIn(".source-radar/engines/searxng/source/.venv", saved["venv_path"])

    def test_write_metadata_ignores_external_checkout(self):
        from source_radar.backends.installer import EngineInstaller
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            legacy = root / "external" / "MediaCrawler"
            legacy.mkdir(parents=True)
            installer = EngineInstaller(build_default_registry(root), root)

            metadata = installer.write_metadata("community.mediacrawler", source="local-source")

            self.assertIn(".source-radar/engines/mediacrawler/source", metadata["source_path"])
            self.assertIn(".source-radar/engines/mediacrawler/source", metadata["target_path"])
            self.assertNotIn("external/MediaCrawler", metadata["source_path"])

    def test_record_download_manifest_uses_unified_download_cache(self):
        from source_radar.backends.installer import EngineInstaller
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            installer = EngineInstaller(build_default_registry(root), root)

            manifest = installer.record_download(
                "search.searxng",
                filename="searxng-2026.7.3.zip",
                url="https://example.invalid/searxng.zip",
                status="failed",
                reason="network-timeout",
            )

            manifest_path = root / ".source-radar" / "downloads" / "manifests" / "searxng-2026.7.3.zip.json"
            self.assertTrue(manifest_path.is_file())
            saved = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(saved, manifest)
            self.assertEqual(saved["backend_key"], "search.searxng")
            self.assertEqual(saved["status"], "failed")
            self.assertEqual(saved["reason"], "network-timeout")
            self.assertIn(".source-radar/downloads/archives/searxng-2026.7.3.zip", saved["archive_path"])

    def test_install_diagnostics_reads_metadata_and_download_manifests(self):
        from source_radar.backends.installer import EngineInstaller
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            installer = EngineInstaller(build_default_registry(root), root)
            installer.write_metadata(
                "search.searxng",
                source="local-source",
                version="2026.7.3",
                commit="abc123",
            )
            installer.record_download(
                "search.searxng",
                filename="searxng-2026.7.3.zip",
                url="https://example.invalid/searxng.zip",
                status="failed",
                reason="network-timeout",
            )

            diagnostics = installer.install_diagnostics("search.searxng")

        self.assertEqual(diagnostics["metadata"]["commit"], "abc123")
        self.assertEqual(diagnostics["metadata"]["source"], "local-source")
        self.assertEqual(diagnostics["downloads"][0]["filename"], "searxng-2026.7.3.zip")
        self.assertEqual(diagnostics["downloads"][0]["status"], "failed")
        self.assertEqual(diagnostics["downloads"][0]["reason"], "network-timeout")

    def test_repair_plan_uses_failed_manifest_for_retry_and_cached_archive_for_reuse(self):
        from source_radar.backends.installer import EngineInstaller
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            installer = EngineInstaller(build_default_registry(root), root)
            installer.record_download(
                "search.searxng",
                filename="searxng-failed.zip",
                url="https://example.invalid/failed.zip",
                status="failed",
                reason="network-timeout",
            )
            installer.record_download(
                "search.searxng",
                filename="searxng-cached.zip",
                url="https://example.invalid/cached.zip",
                status="downloaded",
            )
            cached_archive = root / ".source-radar" / "downloads" / "archives" / "searxng-cached.zip"
            cached_archive.write_text("cached", encoding="utf-8")

            plan = installer.repair_plan("search.searxng")

        retry = next(action for action in plan["actions"] if action["action"] == "retry-download")
        reuse = next(action for action in plan["actions"] if action["action"] == "reuse-archive")
        self.assertEqual(retry["filename"], "searxng-failed.zip")
        self.assertEqual(retry["reason"], "network-timeout")
        self.assertEqual(reuse["filename"], "searxng-cached.zip")
        self.assertIn(".source-radar/downloads/archives/searxng-cached.zip", reuse["archive_path"])

    def test_cleanup_plan_lists_failed_download_manifests_without_deleting(self):
        from source_radar.backends.installer import EngineInstaller
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            installer = EngineInstaller(build_default_registry(root), root)
            installer.record_download(
                "search.searxng",
                filename="searxng-failed.zip",
                url="https://example.invalid/failed.zip",
                status="failed",
                reason="network-timeout",
            )

            plan = installer.cleanup_plan("search.searxng")
            manifest = root / ".source-radar" / "downloads" / "manifests" / "searxng-failed.zip.json"
            self.assertTrue(manifest.exists())

        self.assertEqual(plan["candidates"][0]["filename"], "searxng-failed.zip")
        self.assertEqual(plan["candidates"][0]["status"], "failed")

    def test_repair_plan_does_not_reuse_failed_or_empty_archive_paths(self):
        from source_radar.backends.installer import EngineInstaller
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            installer = EngineInstaller(build_default_registry(root), root)
            failed = installer.record_download(
                "search.searxng",
                filename="searxng-failed.zip",
                url="https://example.invalid/failed.zip",
                status="failed",
                reason="partial",
            )
            (root / failed["archive_path"]).write_text("partial", encoding="utf-8")
            manifest = root / ".source-radar" / "downloads" / "manifests" / "empty.json"
            manifest.write_text(json.dumps({
                "backend_key": "search.searxng",
                "filename": "empty.zip",
                "status": "downloaded",
                "archive_path": "",
            }), encoding="utf-8")

            plan = installer.repair_plan("search.searxng")

        reused = [action["filename"] for action in plan["actions"] if action["action"] == "reuse-archive"]
        self.assertNotIn("searxng-failed.zip", reused)
        self.assertNotIn("empty.zip", reused)

    def test_repair_plan_source_exists_download_failed_only_retries(self):
        """When source dir exists but a download failed, repair should only retry-download, not install-source."""
        from source_radar.backends.installer import EngineInstaller
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            installer = EngineInstaller(build_default_registry(root), root)
            # Source dir exists — no install-source needed
            (root / ".source-radar" / "engines" / "searxng" / "source").mkdir(parents=True)
            installer.record_download(
                "search.searxng",
                filename="searxng-failed.zip",
                url="https://example.invalid/failed.zip",
                status="failed",
                reason="network-timeout",
            )

            plan = installer.repair_plan("search.searxng")

        actions = [a["action"] for a in plan["actions"]]
        self.assertIn("retry-download", actions)
        self.assertNotIn("install-source", actions)

    def test_record_download_overwrites_same_filename_manifest(self):
        """Re-recording a download with the same filename updates the manifest (resume/retry scenario)."""
        from source_radar.backends.installer import EngineInstaller
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            installer = EngineInstaller(build_default_registry(root), root)

            installer.record_download(
                "search.searxng",
                filename="searxng-2026.7.3.zip",
                url="https://example.invalid/searxng.zip",
                status="failed",
                reason="network-timeout",
            )
            installer.record_download(
                "search.searxng",
                filename="searxng-2026.7.3.zip",
                url="https://example.invalid/searxng.zip",
                status="downloaded",
            )

            manifest_path = root / ".source-radar" / "downloads" / "manifests" / "searxng-2026.7.3.zip.json"
            saved = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(saved["status"], "downloaded")
        self.assertEqual(saved["reason"], "")


class EngineInstallerCliIntegrationTests(unittest.TestCase):
    def test_engine_status_suggests_start_for_installed_stopped_service(self):
        from unittest.mock import patch
        from source_radar import engine

        stopped = [
            {
                "key": "searxng",
                "name": "SearXNG",
                "type": "service",
                "status": "stopped",
                "detail": "SearXNG 已安装，未启动",
            }
        ]

        with patch("source_radar.engine.list_engines", return_value=stopped):
            text = engine.run_engine_status()

        self.assertIn("source-radar engine start searxng", text)
        self.assertNotIn("engine install --searxng", text)

    def test_setup_plan_uses_lightweight_import_discovery_for_optional_libraries(self):
        from unittest.mock import patch
        from source_radar import engine

        with patch("source_radar.config.load_openai_config", return_value={}):
            with patch("source_radar.health.BridgeHealth.resolve", return_value=""):
                with patch("source_radar.engine.importlib.util.find_spec", return_value=None):
                    with patch("source_radar.engine.importlib.import_module") as import_module:
                        plan = engine.setup_plan()

        import_module.assert_not_called()
        missing = {
            item.get("key"): item
            for item in plan["optional_inputs"]
            if item.get("key") == "engines"
        }
        self.assertIn("engines", missing)

    def test_searxng_install_clones_into_source_radar_engine_source(self):
        from unittest.mock import MagicMock, patch
        from source_radar import engine

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            failed = MagicMock(returncode=1, stderr="network down")

            with patch("source_radar.engine._root", return_value=root):
                with patch("source_radar.engine.subprocess.run", return_value=failed) as run:
                    result = engine.run_engine_install_searxng()

            clone_cmd = run.call_args_list[0].args[0]
            self.assertEqual(clone_cmd[-1], str(root / ".source-radar" / "engines" / "searxng" / "source"))
            self.assertIn(".source-radar", result)
            self.assertIn("engines", result)

    def test_community_install_clones_mediacrawler_into_source_radar_engine_source(self):
        from unittest.mock import MagicMock, patch
        from source_radar import engine

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            failed = MagicMock(returncode=1)

            with patch("source_radar.engine._root", return_value=root):
                with patch("source_radar.engine.subprocess.run", return_value=failed) as run:
                    result = engine.run_engine_install(core=False, browser=False, community=True, searxng=False)

            clone_cmd = next(call.args[0] for call in run.call_args_list if call.args[0][:2] == ["git", "clone"])
            self.assertEqual(clone_cmd[-1], str(root / ".source-radar" / "engines" / "mediacrawler" / "source"))
            self.assertIn(".source-radar", result)
            self.assertIn("engines", result)

    def test_community_install_records_failed_clone_manifest(self):
        from unittest.mock import MagicMock, patch
        from source_radar import engine

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            failed = MagicMock(returncode=1, stderr="network down")

            with patch("source_radar.engine._root", return_value=root):
                with patch("source_radar.engine.subprocess.run", return_value=failed):
                    engine.run_engine_install(core=False, browser=False, community=True, searxng=False)

            manifest = root / ".source-radar" / "downloads" / "manifests" / "MediaCrawler-git-clone.json"
            saved = json.loads(manifest.read_text(encoding="utf-8"))

        self.assertEqual(saved["backend_key"], "community.mediacrawler")
        self.assertEqual(saved["filename"], "MediaCrawler-git-clone")
        self.assertIn("github.com", saved["url"])
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["reason"], "git-clone-failed")

    def test_community_install_records_successful_clone_manifest(self):
        from unittest.mock import MagicMock, patch
        from source_radar import engine

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            ok = MagicMock(returncode=0, stderr="")

            with patch("source_radar.engine._root", return_value=root):
                with patch("source_radar.engine.subprocess.run", return_value=ok):
                    with patch("source_radar.engine._run_required"):
                        with patch("source_radar.engine._patch_mediacrawler_no_console", return_value="OK patched"):
                            engine.run_engine_install(core=False, browser=False, community=True, searxng=False)

            manifest = root / ".source-radar" / "downloads" / "manifests" / "MediaCrawler-git-clone.json"
            saved = json.loads(manifest.read_text(encoding="utf-8"))

        self.assertEqual(saved["backend_key"], "community.mediacrawler")
        self.assertEqual(saved["filename"], "MediaCrawler-git-clone")
        self.assertIn("github.com", saved["url"])
        self.assertEqual(saved["status"], "downloaded")

    def test_searxng_install_records_failed_clone_manifest(self):
        from unittest.mock import MagicMock, patch
        from source_radar import engine

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            failed = MagicMock(returncode=1, stderr="network down")

            with patch("source_radar.engine._root", return_value=root):
                with patch("source_radar.engine.subprocess.run", return_value=failed):
                    engine.run_engine_install_searxng()

            manifest = root / ".source-radar" / "downloads" / "manifests" / "searxng-git-clone.json"
            saved = json.loads(manifest.read_text(encoding="utf-8"))

        self.assertEqual(saved["backend_key"], "search.searxng")
        self.assertEqual(saved["filename"], "searxng-git-clone")
        self.assertIn("github.com", saved["url"])
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["reason"], "git-clone-failed")

    def test_searxng_install_records_successful_clone_manifest(self):
        from unittest.mock import MagicMock, patch
        from source_radar import engine

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            ok = MagicMock(returncode=0, stderr="")

            def fake_run(args, **kwargs):
                if args[:2] == [".venv", "never"]:
                    raise AssertionError("unreachable")
                return ok

            with patch("source_radar.engine._root", return_value=root):
                with patch("source_radar.engine.subprocess.run", side_effect=fake_run):
                    engine.run_engine_install_searxng()

            manifest = root / ".source-radar" / "downloads" / "manifests" / "searxng-git-clone.json"
            saved = json.loads(manifest.read_text(encoding="utf-8"))

        self.assertEqual(saved["backend_key"], "search.searxng")
        self.assertEqual(saved["filename"], "searxng-git-clone")
        self.assertIn("github.com", saved["url"])
        self.assertEqual(saved["status"], "downloaded")

    def test_install_source_dir_ignores_legacy_checkout_for_new_installs(self):
        from unittest.mock import patch
        from source_radar import engine

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            legacy = root / "external" / "searxng"
            legacy.mkdir(parents=True)

            with patch("source_radar.engine._root", return_value=root):
                source_dir = engine._engine_install_source_dir("searxng")

        self.assertEqual(source_dir, root / ".source-radar" / "engines" / "searxng" / "source")

    def test_engine_status_shows_install_metadata_and_download_manifest(self):
        from unittest.mock import patch
        from source_radar import engine
        from source_radar.backends.installer import EngineInstaller
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            installer = EngineInstaller(build_default_registry(root), root)
            (root / ".source-radar" / "engines" / "searxng" / "source").mkdir(parents=True)
            installer.write_metadata("search.searxng", source="local-source", commit="abc123")
            installer.record_download(
                "search.searxng",
                filename="searxng-2026.7.3.zip",
                url="https://example.invalid/searxng.zip",
                status="failed",
                reason="network-timeout",
            )

            with patch("source_radar.engine._root", return_value=root):
                with patch("source_radar.engine._check_library", return_value=("ready", "已安装")):
                    with patch("source_radar.engine._searxng_health_check", return_value={"status": "error"}):
                        with patch("source_radar.engine._http_ok", return_value=False):
                            text = engine.run_engine_status()

        self.assertIn("install: source=local-source commit=abc123", text)
        self.assertIn("source_path=.source-radar/engines/searxng/source", text)
        self.assertIn("download: searxng-2026.7.3.zip status=failed reason=network-timeout", text)

    def test_engine_status_ignores_live_external_source(self):
        from unittest.mock import patch
        from source_radar import engine
        from source_radar.backends.installer import EngineInstaller
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            legacy = root / "external" / "searxng"
            legacy.mkdir(parents=True)
            installer = EngineInstaller(build_default_registry(root), root)
            installer.write_metadata("search.searxng", source="local-source", commit="abc123")
            metadata_path = root / ".source-radar" / "engines" / "searxng" / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["source_path"] = ".source-radar/engines/searxng/source"
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

            with patch("source_radar.engine._root", return_value=root):
                with patch("source_radar.engine._check_library", return_value=("ready", "已安装")):
                    with patch("source_radar.engine._searxng_health_check", return_value={"status": "error"}):
                        with patch("source_radar.engine._http_ok", return_value=False):
                            text = engine.run_engine_status()

        self.assertIn("source_path=.source-radar/engines/searxng/source", text)
        self.assertNotIn("external/searxng", text)
        self.assertNotIn("legacy=true", text)
        self.assertIn("SearXNG 未安装", text)

    def test_searxng_status_requires_target_source_even_if_port_responds(self):
        from unittest.mock import patch
        from source_radar import engine

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            external = root / "external" / "searxng"
            external.mkdir(parents=True)

            with patch("source_radar.engine._root", return_value=root):
                with patch("source_radar.engine._searxng_health_check", return_value={"status": "ok"}):
                    with patch("source_radar.engine._http_ok", return_value=True):
                        status, detail = engine._check_searxng_engine(engine.ENGINES["searxng"])

        self.assertEqual(status, "missing")
        self.assertIn(".source-radar", detail)

    def test_engine_repair_and_cleanup_show_retry_reuse_and_dry_run_candidates(self):
        from unittest.mock import patch
        from source_radar import engine
        from source_radar.backends.installer import EngineInstaller
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            installer = EngineInstaller(build_default_registry(root), root)
            installer.record_download(
                "search.searxng",
                filename="searxng-failed.zip",
                url="https://example.invalid/failed.zip",
                status="failed",
                reason="network-timeout",
            )
            installer.record_download(
                "search.searxng",
                filename="searxng-cached.zip",
                url="https://example.invalid/cached.zip",
                status="downloaded",
            )
            cached_archive = root / ".source-radar" / "downloads" / "archives" / "searxng-cached.zip"
            cached_archive.write_text("cached", encoding="utf-8")

            with patch("source_radar.engine._root", return_value=root):
                repair = engine.run_engine_repair("searxng")
                cleanup = engine.run_engine_cleanup("searxng", dry_run=True)
                cleanup_not_supported = engine.run_engine_cleanup("searxng", dry_run=False)

        self.assertIn("retry-download searxng-failed.zip", repair)
        self.assertIn("reuse-archive searxng-cached.zip", repair)
        self.assertIn("cleanup dry-run", cleanup)
        self.assertIn("searxng-failed.zip", cleanup)
        self.assertIn("only dry-run cleanup is supported", cleanup_not_supported)

    def test_engine_list_snapshot_includes_repair_actions(self):
        from unittest.mock import patch
        from source_radar import engine
        from source_radar.backends.installer import EngineInstaller
        from source_radar.backends.registry import build_default_registry

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            installer = EngineInstaller(build_default_registry(root), root)
            installer.record_download(
                "search.searxng",
                filename="searxng-failed.zip",
                url="https://example.invalid/failed.zip",
                status="failed",
                reason="network-timeout",
            )

            with patch("source_radar.engine._root", return_value=root):
                with patch("source_radar.engine._check_library", return_value=("ready", "已安装")):
                    with patch("source_radar.engine._searxng_health_check", return_value={"status": "error"}):
                        with patch("source_radar.engine._http_ok", return_value=False):
                            snapshot = engine.list_engines()

        searxng = next(item for item in snapshot if item["key"] == "searxng")
        action = next(item for item in searxng["repair_actions"] if item["action"] == "retry-download")
        self.assertEqual(action["filename"], "searxng-failed.zip")
        self.assertEqual(action["reason"], "network-timeout")


if __name__ == "__main__":
    unittest.main()
