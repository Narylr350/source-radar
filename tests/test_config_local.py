import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from source_radar.config import (
    clear_openai_config,
    get_config_path,
    load_openai_config,
    save_openai_config,
)
from source_radar.llm import OpenAIResponsesProvider


class LocalConfigTests(unittest.TestCase):
    def test_openai_config_round_trip_uses_local_user_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                path = get_config_path()
                save_openai_config(
                    api_key="local-key",
                    endpoint="http://127.0.0.1:9317/",
                    model="gpt-5.4",
                )

                loaded = load_openai_config()

        self.assertEqual(path, pathlib.Path(directory) / "config.json")
        self.assertEqual(loaded["api_key"], "local-key")
        self.assertEqual(loaded["endpoint"], "http://127.0.0.1:9317/")
        self.assertEqual(loaded["model"], "gpt-5.4")

    def test_provider_reads_local_config_without_environment_key(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
                save_openai_config(
                    api_key="local-key",
                    endpoint="http://127.0.0.1:9317/",
                    model="gpt-5.4",
                )
                provider = OpenAIResponsesProvider.from_environment()

        self.assertEqual(provider.status, "configured")
        self.assertEqual(provider.model, "gpt-5.4")
        self.assertEqual(provider.endpoint, "http://127.0.0.1:9317/v1/responses")

    def test_clear_openai_config_removes_local_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                save_openai_config("local-key", "http://127.0.0.1:9317/", "gpt-5.4")
                clear_openai_config()

                self.assertEqual(load_openai_config(), {})

    def test_config_file_is_json(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                save_openai_config("local-key", "http://127.0.0.1:9317/", "gpt-5.4")
                payload = json.loads(get_config_path().read_text(encoding="utf-8"))

        self.assertEqual(payload["openai"]["model"], "gpt-5.4")


if __name__ == "__main__":
    unittest.main()
