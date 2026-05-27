import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from source_radar.config import (
    clear_openai_config,
    clear_provider_config,
    get_config_path,
    load_openai_config,
    load_provider_config,
    save_openai_config,
    save_provider_config,
)
from source_radar.llm import AIProvider


class LocalConfigTests(unittest.TestCase):
    def test_openai_config_round_trip_uses_local_user_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                path = get_config_path()
                save_openai_config(
                    api_key="local-key",
                    endpoint="http://127.0.0.1:8000/",
                    model="test-model",
                )

                loaded = load_openai_config()

        self.assertEqual(path, pathlib.Path(directory) / "config.json")
        self.assertEqual(loaded["api_key"], "local-key")
        self.assertEqual(loaded["endpoint"], "http://127.0.0.1:8000/")
        self.assertEqual(loaded["model"], "test-model")

    def test_provider_reads_local_config_without_environment_key(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
                save_openai_config(
                    api_key="local-key",
                    endpoint="http://127.0.0.1:8000/",
                    model="test-model",
                )
                provider = AIProvider.from_environment()

        self.assertEqual(provider.status, "configured")
        self.assertEqual(provider.model, "test-model")
        self.assertEqual(provider.endpoint, "http://127.0.0.1:8000/v1/responses")

    def test_clear_openai_config_removes_local_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                save_openai_config("local-key", "http://127.0.0.1:8000/", "test-model")
                clear_openai_config()

                self.assertEqual(load_openai_config(), {})

    def test_config_file_is_json(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                save_openai_config("local-key", "http://127.0.0.1:8000/", "test-model")
                payload = json.loads(get_config_path().read_text(encoding="utf-8"))

        self.assertEqual(payload["openai"]["model"], "test-model")

    def test_provider_config_round_trip_uses_local_user_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                save_provider_config(
                    "firecrawl",
                    endpoint="http://127.0.0.1:3002",
                    enabled=True,
                )
                loaded = load_provider_config("firecrawl")

        self.assertEqual(loaded["endpoint"], "http://127.0.0.1:3002")
        self.assertEqual(loaded["enabled"], "true")

    def test_clear_provider_config_removes_bridge_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                save_provider_config("firecrawl", endpoint="http://127.0.0.1:3002")
                clear_provider_config("firecrawl")

                self.assertEqual(load_provider_config("firecrawl"), {})


if __name__ == "__main__":
    unittest.main()
