import asyncio
import unittest
from unittest.mock import patch


class AcquisitionKernelTests(unittest.TestCase):
    def test_search_delegates_to_injected_dispatcher(self):
        from source_radar.acquisition import AcquisitionKernel, AcquisitionResult

        calls = {}

        def fake_search(query, *, limit, site, page, providers=None):
            calls.update({
                "query": query,
                "limit": limit,
                "site": site,
                "page": page,
                "providers": providers,
            })
            return AcquisitionResult(
                provider="search",
                provider_type="search",
                status="ok",
                reason="candidates-found",
                message="ok",
            )

        kernel = AcquisitionKernel(search_dispatcher=fake_search)
        result = kernel.search("测试", limit=2, site="example.com", page=3)

        self.assertEqual(result.status, "ok")
        self.assertEqual(calls["query"], "测试")
        self.assertEqual(calls["limit"], 2)
        self.assertEqual(calls["site"], "example.com")
        self.assertEqual(calls["page"], 3)

    def test_fetch_delegates_to_injected_dispatcher(self):
        from source_radar.acquisition import AcquisitionKernel, AcquisitionRequest, AcquisitionResult

        calls = {}

        def fake_fetch(request):
            calls["request"] = request
            return AcquisitionResult(
                provider="web",
                provider_type="generic-crawler",
                status="ok",
                reason="items-found",
                message="ok",
            )

        request = AcquisitionRequest(query="", url="https://example.com", limit=1)
        kernel = AcquisitionKernel(fetch_dispatcher=fake_fetch)
        result = kernel.fetch(request)

        self.assertEqual(result.status, "ok")
        self.assertIs(calls["request"], request)


class MCPAcquisitionKernelIntegrationTests(unittest.TestCase):
    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    @patch("source_radar.mcp.server._ensure_searxng_for_search", return_value=(True, ""))
    def test_web_search_uses_acquisition_kernel(self, _mock_ensure, _mock_get, _mock_put):
        from source_radar.acquisition import AcquisitionResult, CandidateSource
        from source_radar.mcp.server import handle_search

        fake_result = AcquisitionResult(
            provider="search",
            provider_type="search",
            status="ok",
            reason="candidates-found",
            message="ok",
            candidates=[
                CandidateSource(
                    title="T",
                    url="https://example.com",
                    snippet="S",
                    provider="search",
                    source_type="search-result",
                ),
            ],
        )

        async def run():
            with patch("source_radar.mcp.server.AcquisitionKernel") as MockKernel:
                MockKernel.return_value.search.return_value = fake_result
                result = await handle_search({"query": "测试", "limit": 1})
                return result, MockKernel

        result, MockKernel = asyncio.run(run())

        self.assertFalse(result.isError)
        self.assertIn("https://example.com", result.content[0].text)
        MockKernel.return_value.search.assert_called_once_with(
            "测试", limit=1, site=None, page=1,
        )


if __name__ == "__main__":
    unittest.main()
