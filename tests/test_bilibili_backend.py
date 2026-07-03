import asyncio
import unittest
from unittest.mock import patch


class BilibiliNativeBackendTests(unittest.TestCase):
    def test_collect_maps_video_results_to_acquisition_items(self):
        from source_radar.acquisition import AcquisitionRequest
        from source_radar.backends.community.bilibili import BilibiliNativeBackend

        def fake_request_json(url, headers, timeout):
            self.assertIn("keyword=%E5%91%A8%E6%9D%B0%E4%BC%A6", url)
            self.assertIn("User-Agent", headers)
            return {
                "code": 0,
                "data": {
                    "result": [
                        {
                            "title": "<em class=\"keyword\">周杰伦</em> 新歌现场",
                            "arcurl": "https://www.bilibili.com/video/BV123",
                            "description": "现场片段",
                            "author": "音乐号",
                            "pubdate": 1710000000,
                            "play": 1234,
                            "danmaku": 56,
                        }
                    ]
                },
            }

        backend = BilibiliNativeBackend(request_json=fake_request_json)
        result = backend.collect(AcquisitionRequest(query="周杰伦", limit=1, platforms=["bili"]))

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.provider, "bilibili")
        self.assertEqual(result.items[0].title, "周杰伦 新歌现场")
        self.assertEqual(result.items[0].url, "https://www.bilibili.com/video/BV123")
        self.assertEqual(result.items[0].metadata["platform"], "bili")
        self.assertEqual(result.items[0].metadata["author"], "音乐号")
        self.assertIn("missing-cookie", result.warnings[0])

    def test_collect_reports_rate_limit_as_retryable_diagnostic(self):
        from source_radar.acquisition import AcquisitionRequest
        from source_radar.backends.community.bilibili import BilibiliNativeBackend

        backend = BilibiliNativeBackend(request_json=lambda *_args: {"code": -412, "message": "风控"})
        result = backend.collect(AcquisitionRequest(query="周杰伦", limit=1, platforms=["bili"]))

        self.assertEqual(result.status, "error")
        self.assertEqual(result.reason, "rate-limited")
        self.assertTrue(result.retryable)
        self.assertIn("B站风控", result.message)
        self.assertEqual(result.diagnostics["platform"], "bili")

    def test_collect_reports_http_412_as_rate_limit(self):
        from urllib.error import HTTPError

        from source_radar.acquisition import AcquisitionRequest
        from source_radar.backends.community.bilibili import BilibiliNativeBackend

        def raise_412(*_args):
            raise HTTPError("https://api.bilibili.com", 412, "Precondition Failed", {}, None)

        backend = BilibiliNativeBackend(request_json=raise_412)
        result = backend.collect(AcquisitionRequest(query="周杰伦", limit=1, platforms=["bili"]))

        self.assertEqual(result.status, "error")
        self.assertEqual(result.reason, "rate-limited")
        self.assertTrue(result.retryable)
        self.assertIn("B站风控", result.message)

    def test_collect_reports_cookie_expired(self):
        from source_radar.acquisition import AcquisitionRequest
        from source_radar.backends.community.bilibili import BilibiliNativeBackend

        backend = BilibiliNativeBackend(cookie="SESSDATA=expired", request_json=lambda *_args: {"code": -101, "message": "账号未登录"})
        result = backend.collect(AcquisitionRequest(query="周杰伦", limit=1, platforms=["bili"]))

        self.assertEqual(result.status, "needs-input")
        self.assertEqual(result.reason, "cookie-expired")
        self.assertFalse(result.retryable)
        self.assertIn("SOURCE_RADAR_BILI_COOKIE", result.fix)


class BilibiliMCPIntegrationTests(unittest.TestCase):
    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    def test_search_chinese_platforms_prefers_bilibili_native_backend(self, _mock_get, _mock_put):
        from source_radar.acquisition import AcquisitionResult
        from source_radar.mcp.server import handle_search_chinese_platforms
        from source_radar.models import SourceItem

        native_result = AcquisitionResult(
            provider="bilibili",
            provider_type="native",
            status="ok",
            reason="items-found",
            message="ok",
            items=[
                SourceItem(
                    source_type="community-video",
                    title="B站结果",
                    url="https://www.bilibili.com/video/BV123",
                    snippet="摘要",
                    adapter="bilibili",
                    metadata={"platform": "bili", "author": "up"},
                )
            ],
        )

        async def run():
            with patch("source_radar.mcp.server.BilibiliNativeBackend") as MockNative:
                MockNative.return_value.collect.return_value = native_result
                with patch("source_radar.mcp.server._providers", {}):
                    result = await handle_search_chinese_platforms(
                        {"query": "周杰伦", "platforms": ["bili"], "limit": 1}
                    )
                return result, MockNative

        result, MockNative = asyncio.run(run())

        self.assertFalse(result.isError)
        self.assertIn("B站结果", result.content[0].text)
        MockNative.return_value.collect.assert_called_once()

    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    def test_search_chinese_platforms_falls_back_to_bridge_when_native_errors(self, _mock_get, _mock_put):
        from source_radar.acquisition import AcquisitionResult
        from source_radar.mcp.server import handle_search_chinese_platforms
        from source_radar.models import SourceItem

        native_error = AcquisitionResult(
            provider="bilibili",
            provider_type="native",
            status="error",
            reason="rate-limited",
            message="B站风控",
            retryable=True,
        )
        bridge_status = AcquisitionResult(
            provider="mediacrawler",
            provider_type="legacy-bridge",
            status="ok",
            reason="ready",
            message="ready",
        )
        bridge_result = AcquisitionResult(
            provider="mediacrawler",
            provider_type="legacy-bridge",
            status="ok",
            reason="items-found",
            message="ok",
            items=[
                SourceItem(
                    source_type="community-post",
                    title="桥结果",
                    url="https://example.test/1",
                    snippet="fallback",
                    adapter="mediacrawler",
                    metadata={"platform": "bili"},
                )
            ],
        )

        class FakeBridge:
            def status(self):
                return bridge_status

            def collect(self, request):
                return bridge_result

        async def run():
            with patch("source_radar.mcp.server.BilibiliNativeBackend") as MockNative:
                MockNative.return_value.collect.return_value = native_error
                with patch("source_radar.mcp.server._providers", {"mediacrawler": FakeBridge()}):
                    return await handle_search_chinese_platforms(
                        {"query": "周杰伦", "platforms": ["bili"], "limit": 1}
                    )

        result = asyncio.run(run())

        self.assertFalse(result.isError)
        self.assertIn("桥结果", result.content[0].text)


if __name__ == "__main__":
    unittest.main()
