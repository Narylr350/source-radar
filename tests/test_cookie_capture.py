import pathlib
import tempfile
import unittest

from source_radar.cookie_capture import (
    PLATFORM_COOKIE_CONFIG,
    _local_env_path,
    read_local_env,
    write_local_env,
)


class CookieCaptureHelpersTests(unittest.TestCase):
    def test_platform_config_covers_all_cookie_envs(self):
        from source_radar.bridge import PLATFORM_COOKIE_ENVS

        for platform, env_name in PLATFORM_COOKIE_ENVS.items():
            with self.subTest(platform=platform):
                self.assertIn(platform, PLATFORM_COOKIE_CONFIG)
                self.assertEqual(PLATFORM_COOKIE_CONFIG[platform]["env"], env_name)

    def test_platform_config_has_required_fields(self):
        for platform, config in PLATFORM_COOKIE_CONFIG.items():
            with self.subTest(platform=platform):
                self.assertIn("name", config)
                self.assertIn("env", config)
                self.assertIn("login_url", config)
                self.assertTrue(config["login_url"].startswith("https://"))

    def test_read_local_env_empty_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = read_local_env(root=tmp)
            self.assertEqual(result, {})

    def test_read_local_env_parses_key_value_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = pathlib.Path(tmp) / ".source-radar"
            src_dir.mkdir(parents=True)
            env_file = src_dir / "local.env"
            env_file.write_text(
                "SOURCE_RADAR_XHS_COOKIE=test_cookie_value\n"
                "FIRECRAWL_TRANSPORT=mcp\n"
                "# comment line\n"
                "\n"
                "FIRECRAWL_API_KEY=\n",
                encoding="utf-8",
            )
            result = read_local_env(root=tmp)
            self.assertEqual(result["SOURCE_RADAR_XHS_COOKIE"], "test_cookie_value")
            self.assertEqual(result["FIRECRAWL_TRANSPORT"], "mcp")
            self.assertNotIn("FIRECRAWL_API_KEY", result)

    def test_write_local_env_creates_file_and_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_local_env({"KEY_A": "val_a", "KEY_B": "val_b"}, root=tmp)
            path = _local_env_path(tmp)
            self.assertTrue(path.exists())
            content = path.read_text(encoding="utf-8")
            self.assertIn("KEY_A=val_a", content)
            self.assertIn("KEY_B=val_b", content)

    def test_write_local_env_preserves_existing_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_local_env({"KEEP_ME": "keep_value"}, root=tmp)
            write_local_env({"NEW_KEY": "new_value"}, root=tmp)
            result = read_local_env(root=tmp)
            self.assertEqual(result["KEEP_ME"], "keep_value")
            self.assertEqual(result["NEW_KEY"], "new_value")

    def test_write_local_env_overwrites_existing_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_local_env({"KEY": "old"}, root=tmp)
            write_local_env({"KEY": "new"}, root=tmp)
            result = read_local_env(root=tmp)
            self.assertEqual(result["KEY"], "new")
