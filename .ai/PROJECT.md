# PROJECT

## Goal

优化 source-radar 常驻服务（主要是 SearXNG）的冷启动体验：MCP server 启动时后台预热，空闲时自动停止。既避免首次搜索的冷启动等待（实测 SearXNG 12s），又避免服务长期常驻占用资源。

## Users and Scenarios

个人研究者、开发者、AI agent 使用者。场景：搜资料、找观点/案例/教程、核验中文互联网消息（产品/政策/人物/GitHub 项目信息）、通过 MCP 让外部 AI 调用搜索与抓取能力。

## MVP

"冷启动优化"= 以下条件同时成立：

1. MCP server 启动时后台异步预热 SearXNG，不阻塞工具列表返回
2. MCP server 空闲 N 分钟后自动停止它启动的 SearXNG（释放进程/内存）
3. 预热后首次搜索走热路径（2-3s），不再等 12s 冷启动
4. 空闲停止后下次调用能重新预热/随用随起，行为可靠
5. 现有测试通过 + smoke test 通过（ask + MCP web_search 不回归）

## Inputs and Outputs

- 输入：问题/断言/URL/平台查询；AI provider 配置；bridge endpoint 与 cookie 配置；空闲阈值配置
- 输出：证据卡、综合分析/核验报告（Markdown/JSON）、MCP 工具结果、health/probe/status 状态

## Non-goals

- 不改 agent 的多轮编排层（`_adaptive_collect` 的控制流不动）
- 不改 MCP 协议（7 个工具接口不变）
- 不做 crawl4ai 浏览器实例池优化（浏览器冷启动 3s 是另一类问题，不属服务预热范畴）
- MediaCrawler 空闲停止可选（同机制可复用），非本轮必须——它 5.5s 且按需使用
- 不做 Web/Desktop UI
- 不绕过登录/验证码/访问控制，不做大规模监控
- 不 vendor MediaCrawler/SearXNG/Firecrawl 源码
- 不把 LLM 结论伪装成事实裁定
- 不引入新框架

## Tech Direction

已有技术栈不变。冷启动优化方向：

- 运行时：Python 3.11+（`requires-python = ">=3.11,<3.14"`）
- 包管理：uv + setuptools，`app/` 单应用（`single-app`）
- 测试：标准库 `unittest`
- 空闲监控由长生命周期的 MCP server 承担（asyncio 定时器），CLI 短生命周期不管理空闲停止
- 预热用后台 asyncio task，不阻塞 MCP stdio 初始化和工具列表
- 服务启停复用现有 `engine start/stop` + `_ensure_searxng_for_search` 逻辑，不新建启停实现
- 已完成的采集层统一（agent/MCP 共享 dispatch_search + fetch_with_fallback + _providers 注册表）保持不变

## Constraints and Working Rules

- 凭据（API key / cookie / 登录态）只进本地配置（`.source-radar/` 或环境变量），不得 staged/committed/pushed
- SearXNG 是真实搜索的必选基础设施，通过 bridge 接入，不 vendor 源码
- 外部集成遵守许可证边界：MediaCrawler 非商业（external bridge）、Firecrawl AGPL-3.0（bridge/API only）、Trafilatura GPL-3.0（optional extra，不进入核心组合包分发）
- 健康检查统一走 `BridgeHealth`（`health.py`），不得在 engine.py / mcp/server.py / bridge.py / acquisition.py 中新建独立健康检查逻辑
- `_http_ok` 统一定义在 `runtime.py`，engine.py import 它，不得复制
- 采集层已统一：agent.py / mcp/server.py 不得新建独立的搜索/抓取/缓存逻辑，共享 acquisition 层入口
- 服务启停不新建实现，复用 engine 层现有逻辑
- 设计文档用项目现有结构（`docs/tasks/` 或 `docs/engineering/`），不用外来目录约定（如 `docs/superpowers/`）
- 已接入执行层 skill：
  - `tdd` / `test-driven-development`：修 bug 或写功能时，先写测试再写实现（red-green-refactor）
  - `systematic-debugging`：遇 bug/测试失败/异常行为时，先系统诊断再提修复方案
- 其余执行层 skill 未接入

## Validation

- 回归测试：`.venv\Scripts\python.exe -m unittest <关键子集> -v`
- 关键子集：`tests.test_mcp_server tests.test_acquisition_m5 tests.test_agent_flow tests.test_stability_regression tests.test_engine_searxng tests.test_mcp_autostart tests.test_parallel_fetch`
- 冷启动实测基线：SearXNG 冷启动 12s / 就绪后搜索 2-3s / MediaCrawler 5.5s / crawl4ai 3s / trafilatura 0.7s
- Smoke test：MCP server 启动后不查询等待 → 确认 SearXNG 被预热；空闲 N 分钟 → 确认 SearXNG 停止；再查询 → 确认能重新起
- 验证环境不可用时处理：AI 先尝试启动/设环境变量（可逆），不行再提示用户；测试默认用 fixture/mock，不依赖真实平台

## Seed Tasks

1. MCP server 启动时后台异步预热 SearXNG：用 asyncio task 调 `_ensure_searxng_for_search`，不阻塞 stdio 初始化和工具列表返回
2. MCP server 空闲计时器：记录最后一次工具调用时间，空闲超过阈值自动停止 SearXNG
3. 空闲阈值可配（环境变量或 config，默认 10 分钟），预热开关可配（复用 `_searxng_autostart_enabled`）
4. 验证冷启动→预热→空闲停止→重新预热全链路，确认停止后重启可靠、无端口/状态残留
