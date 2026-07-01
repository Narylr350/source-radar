# PROJECT

## Goal

source-radar 是本地 CLI / 采集引擎，把中文互联网与通用 web/GitHub 来源采集成可审计证据卡，供内置 AI 或外部 AI 做综合分析、核验和研究。当前目标：持续优化项目结构、提高外部采集链路稳定性，让常用查询能稳定返回可用结果，使工具自己愿意用。

## Users and Scenarios

个人研究者、开发者、AI agent 使用者。场景：搜资料、找观点/案例/教程、核验中文互联网消息（产品/政策/人物/GitHub 项目信息）、通过 MCP 让外部 AI 调用搜索与抓取能力。

## MVP

当前阶段"能用"= 三件事同时成立：
1. 常用查询（ask/verify/research、MCP web_search/fetch）稳定可返回，不因 bridge 探测误判或上游降级而阻塞或空返。
2. 外部 bridge/provider（SearXNG / MediaCrawler）失败时可降级且可解释：状态口径一致、降级路径明确、错误可恢复。
3. 采集链路 seam 更深、更少透传：健康检查、搜索分发、bridge 调用收敛到少数深模块，减少分散逻辑。

## Inputs and Outputs

- 输入：问题/断言/URL/平台查询；AI provider 配置（endpoint/key/model）；bridge endpoint 与 cookie 配置。
- 输出：证据卡、综合分析/核验报告（Markdown/JSON）、MCP 工具结果、health/probe/status 状态。

## Non-goals

- 不做 Web/Desktop UI。
- 不绕过登录/验证码/访问控制，不做大规模监控。
- 不 vendor MediaCrawler/SearXNG/Firecrawl 源码。
- 不把 LLM 结论伪装成事实裁定。
- 本轮不做新功能扩展，只做结构降复杂和稳定性。

## Tech Direction

- 运行时：Python 3.11+（`requires-python = ">=3.11,<3.14"`）。
- 包管理：uv + setuptools，`app/` 单应用（`single-app`）。
- 测试：标准库 `unittest`，`.venv\Scripts\python.exe -m unittest discover -s tests -v`。
- 外部能力通过 bridge/API/本地服务接入（SearXNG 必选 websearch、MediaCrawler 可选中文社区、trafilatura/crawl4ai 本地网页提取）。
- MCP server 已作为 stdio 模式提供 7 个工具。
- 不引入新框架；重构在现有栈内做，目标是让现有 seam 更深而非换栈。

## Constraints and Working Rules

- 凭据（API key / cookie / 登录态）只进本地配置（`.source-radar/` 或环境变量），不得 staged/committed/pushed。
- SearXNG 是真实搜索的必选基础设施，通过 bridge 接入，不 vendor 源码。
- 外部集成遵守许可证边界：MediaCrawler 非商业（external bridge）、Firecrawl AGPL-3.0（bridge/API only）、Trafilatura GPL-3.0（optional extra，不进入核心组合包分发）。
- 健康检查统一走 `BridgeHealth`（`health.py`），不得在 engine.py / mcp/server.py / bridge.py / acquisition.py 中新建独立健康检查逻辑。
- `_http_ok` 统一定义在 `runtime.py`，engine.py import 它，不得复制。
- 改 bridge/health/dispatch_search 注意：状态口径必须跨 config show / probe / source_status / MCP 工具一致。
- 未接入外部执行层 skill（本轮默认）。

## Validation

- 主验证：`.venv\Scripts\python.exe -m unittest discover -s tests -v`（当前 160+ 核心测试；全量 discover 超 300s 时用关键子集）。
- 关键子集：`tests.test_health_m3 tests.test_mcp_server tests.test_acquisition_m5 tests.test_bridge_runner tests.test_json_contract tests.test_engine_searxng tests.test_mcp_autostart tests.test_agent_flow`。
- bridge/采集验证：`probe --source searxng/mediacrawler --query "test"`、`health --format markdown`、`config show`。
- 真实 smoke：`ask "测试问题"`、MCP `web_search`/`fetch_search_results` 跑常用查询，确认不阻塞且返回相关结果。
- 稳定性回归：用黑盒用例复现"常用查询稳定可返回"作为基线，结构改动后重跑。
- AI 配置验证：`config test-ai`。
- 验证环境不可用时处理：AI/bridge 需凭据或外部进程——AI 先尝试启动/设环境变量（可逆），不行再提示用户；测试默认用 fixture，不依赖真实平台。

## Seed Tasks

1. ~~抽取统一 `BridgeHealth` 模块，收敛 4 处分散健康检查~~ ✅ 已完成（commit `0a1c01f`）。根因 1（config show 误报 unavailable）已修复。
2. ~~`dispatch_search` 对 degraded SearXNG 增加质量门控 fallback~~ ✅ 已完成（commit `6ddeb74`）。根因 2 已修复。
3. 抽取 `ToolCallRecorder` 深模块，拆 agent.py 420 行 `_adaptive_collect` 方法，消除 8 处 tool-call dict 重复构造（候选 2）。
4. ~~MediaCrawler MCP 调用加 120s timeout，collect timeout 200→120s~~ ✅ 已完成（commit `17fa7e2`）。根因 3 已修复。
5. ~~用黑盒用例建立稳定性回归基线~~ ✅ 已完成（commit `a0c9daf`）。4 个回归测试锁定三个根因不回退。
