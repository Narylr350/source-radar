# PROJECT

## Goal

统一 source-radar 的采集层入口：搜索和抓取逻辑收敛到 acquisition 层单一实现，agent 和 MCP 都调它，消除 7 处重复实现。保持 agent 的多轮编排层（`_adaptive_collect`），只统一底层采集调用。

## Users and Scenarios

个人研究者、开发者、AI agent 使用者。场景：搜资料、找观点/案例/教程、核验中文互联网消息（产品/政策/人物/GitHub 项目信息）、通过 MCP 让外部 AI 调用搜索与抓取能力。

## MVP

"采集层统一"= 以下条件同时成立：

1. 搜索统一：agent `run_tool` 和 MCP 都调 `dispatch_search`，删除 `_search_searxng_first`
2. 抓取统一：`_collect_with_fallback` 从 MCP server 移到 acquisition 层，agent 和 MCP 都调
3. provider 统一：MCP 不再临时 new provider，用 `default_providers()` 或注册表
4. 缓存统一：采集层入口处理缓存，MCP 各 handler 不再单独写缓存逻辑
5. 领域知识归位：`_CRAWL4AI_DOMAINS` 移到 `Crawl4AIProvider`
6. 现有测试通过 + smoke test 通过（ask + MCP web_search 不回归）

## Inputs and Outputs

- 输入：问题/断言/URL/平台查询；AI provider 配置；bridge endpoint 与 cookie 配置
- 输出：证据卡、综合分析/核验报告（Markdown/JSON）、MCP 工具结果、health/probe/status 状态

## Non-goals

- 不改 agent 的多轮编排层（`_adaptive_collect` 的控制流不动）
- 不改 MCP 协议（7 个工具接口不变）
- 不做 Web/Desktop UI
- 不绕过登录/验证码/访问控制，不做大规模监控
- 不 vendor MediaCrawler/SearXNG/Firecrawl 源码
- 不把 LLM 结论伪装成事实裁定
- 不引入新框架
- 不做"agent 调 MCP 工具接口"的激进重构（保持 agent 直接调 acquisition 层）

## Tech Direction

已有技术栈不变。统一方向：

- 运行时：Python 3.11+（`requires-python = ">=3.11,<3.14"`）
- 包管理：uv + setuptools，`app/` 单应用（`single-app`）
- 测试：标准库 `unittest`
- 外部能力通过 bridge/API/本地服务接入（SearXNG 必选 websearch、MediaCrawler 可选中文社区、trafilatura/crawl4ai 本地网页提取）
- MCP server stdio 模式，7 个工具
- acquisition 层提供单一采集入口（搜索 + 抓取 + 缓存 + provider 注册）
- agent `run_tool` 委托 acquisition 层入口，不再自己实现 fallback 链
- MCP handler 委托 acquisition 层入口，不再临时 new provider 或写缓存
- `_CRAWL4AI_DOMAINS` 等领域知识归入对应 provider 类

## Constraints and Working Rules

- 凭据（API key / cookie / 登录态）只进本地配置（`.source-radar/` 或环境变量），不得 staged/committed/pushed
- SearXNG 是真实搜索的必选基础设施，通过 bridge 接入，不 vendor 源码
- 外部集成遵守许可证边界：MediaCrawler 非商业（external bridge）、Firecrawl AGPL-3.0（bridge/API only）、Trafilatura GPL-3.0（optional extra，不进入核心组合包分发）
- 健康检查统一走 `BridgeHealth`（`health.py`），不得在 engine.py / mcp/server.py / bridge.py / acquisition.py 中新建独立健康检查逻辑
- `_http_ok` 统一定义在 `runtime.py`，engine.py import 它，不得复制
- 改 bridge/health/dispatch_search 注意：状态口径必须跨 config show / probe / source_status / MCP 工具一致
- 设计文档用项目现有结构（`docs/tasks/` 或 `docs/engineering/`），不用外来目录约定（如 `docs/superpowers/`）
- 采集层统一后，不得在 agent.py 或 mcp/server.py 中新建独立的搜索/抓取/缓存逻辑
- 已接入执行层 skill：
  - `tdd` / `test-driven-development`：修 bug 或写功能时，先写测试再写实现（red-green-refactor）
  - `systematic-debugging`：遇 bug/测试失败/异常行为时，先系统诊断再提修复方案
- 其余执行层 skill 未接入

## Validation

- 回归测试：`.venv\Scripts\python.exe -m unittest <关键子集> -v`
- 关键子集：`tests.test_health_m3 tests.test_mcp_server tests.test_acquisition_m5 tests.test_bridge_runner tests.test_json_contract tests.test_engine_searxng tests.test_mcp_autostart tests.test_agent_flow tests.test_stability_regression`
- Smoke test：`ask "测试问题"` + MCP `web_search` 不回归
- 重复检查：grep 确认 `_search_searxng_first`、`_collect_with_fallback`（MCP 私有版）、`_CRAWL4AI_DOMAINS`（server 层）已删除
- 验证环境不可用时处理：AI/bridge 需凭据或外部进程——AI 先尝试启动/设环境变量（可逆），不行再提示用户；测试默认用 fixture，不依赖真实平台

## Seed Tasks

1. 统一搜索入口：删除 `_search_searxng_first`，`run_tool` 直接调 `dispatch_search`，解决 provider 实例来源差异（注入 vs 新建）
2. 统一抓取入口：`_collect_with_fallback` 移到 acquisition 层，`_CRAWL4AI_DOMAINS` 移入 `Crawl4AIProvider`，agent 和 MCP 都调
3. 统一 provider 实例化 + 缓存：MCP handler 不再临时 new provider 或单独写缓存，统一走 acquisition 层入口
4. 修复 GitHub 搜索/抓取分散：统一 `search_issues`/`collect` 接口，`fetch_github_file` 复用 acquisition 层 API 调用
