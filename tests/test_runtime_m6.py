import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from source_radar.runtime import local_services_for_query, wants_community_sources


class RuntimeM6Tests(unittest.TestCase):
    def test_detects_community_queries_for_local_services(self):
        self.assertEqual(wants_community_sources("找小红书 AI 工具实测案例"), True)
        self.assertEqual(wants_community_sources("张雪峰死了吗"), True)
        self.assertEqual(wants_community_sources("OpenAI API endpoint usage"), False)

    def test_local_services_starts_and_stops_mediacrawler_processes(self):
        class FakeProcess:
            def __init__(self):
                self.terminated = False

            def poll(self):
                return None

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=5):
                return 0

        processes = []

        def fake_popen(*args, **kwargs):
            process = FakeProcess()
            processes.append((process, args, kwargs))
            return process

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "external" / "MediaCrawler").mkdir(parents=True)
            with patch.dict(os.environ, {"SOURCE_RADAR_XHS_COOKIE": "xhs-cookie"}, clear=True):
                with patch("source_radar.runtime._http_ok", return_value=False):
                    with patch("source_radar.runtime._wait_http", return_value=None):
                        with patch("source_radar.runtime.subprocess.Popen", side_effect=fake_popen):
                            with local_services_for_query(
                                "找小红书 AI 工具实测案例",
                                enabled=True,
                                root=root,
                            ):
                                self.assertEqual(
                                    os.environ["SOURCE_RADAR_MEDIACRAWLER_ENDPOINT"],
                                    "http://127.0.0.1:3003",
                                )

        self.assertEqual(len(processes), 2)
        self.assertTrue(all(process.terminated for process, _, _ in processes))


if __name__ == "__main__":
    unittest.main()
