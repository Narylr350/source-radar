# PROJECT

## Goal

让 source-radar 在真实环境下稳定可用：常用查询（ask/verify、MCP web_search/fetch）能返回相关结果，不因 bridge 降级或超时而阻塞或空返。先验证现有功能在真实环境下的稳定性，再考虑结构优化。

## Users and Scenarios

个人研究者、开发者、AI agent 使用者。场景：搜资料、找观点/案例/教程、核验中文互联网消息（产品/政策/人物/GitHub 项目信息）、通过 MCP 让外部 AI 调用搜索与抓取能力。

## MVP

当前阶段"能用"= 常用查询在真实环境下稳定可返回，不阻塞不空返：

1. `ask "测试问题"` 在 SearXNG degraded 环境下不阻塞，返回相关结果
2. MCP `web_search` / `fetch_search_results` 不阻塞，返回相关结果
3. 失败时可降级且可解释（fallback 到 Bing、timeout 保护）

验证方式：真实 smoke test（非 mock），在当前真实环境状态下运行。

## Inputs and Outputs

- 输入：问题/断言/URL/平台查询；AI provider 配置；bridge endpoint 与 cookie 配置
- 输出：证据卡、综合分析/核验报告（Markdown/JSON）、MCP 工具结果、health/probe/status 状态

## Non-goals

- 不做 Web/Desktop UI
- 不绕过登录/验证码/访问控制，不做大规模监控
- 不 vendor MediaCrawler/SearXNG/Firecrawl 源码
- 不把 LLM 结论伪装成事实裁定
- 本轮不做结构优化（ToolCallRecorder 等纯结构重构推迟到稳定性达标后）

## Tech Direction

已有技术栈，不换：

- 运行时：Python 3.11+（`requires-python = ">=3.11,<3.14"`）
- 包管理：uv + setuptools，`app/` 单应用（`single-app`）
- 测试：标准库 `unittest`
- 外部能力通过 bridge/API/本地服务接入（SearXNG 必选 websearch、MediaCrawler 可选中文社区、trafilatura/crawl4ai 本地网页提取）
- MCP server stdio 模式，7 个工具
- 不引入新框架；重构在现有栈内做，目标是让现有 seam 更深而非换栈

## Constraints and Working Rules

- 凭据（API key / cookie / 登录态）只进本地配置（`.source-radar/` 或环境变量），不得 staged/committed/pushed
- SearXNG 是真实搜索的必选基础设施，通过 bridge 接入，不 vendor 源码
- 外部集成遵守许可证边界：MediaCrawler 非商业（external bridge）、Firecrawl AGPL-3.0（bridge/API only）、Trafilatura GPL-3.0（optional extra，不进入核心组合包分发）
- 健康检查统一走 `BridgeHealth`（`health.py`），不得在 engine.py / mcp/server.py / bridge.py / acquisition.py 中新建独立健康检查逻辑
- `_http_ok` 统一定义在 `runtime.py`，engine.py import 它，不得复制
- 改 bridge/health/dispatch_search 注意：状态口径必须跨 config show / probe / source_status / MCP 工具一致
- SearXNG 当前 degraded（baidu/duckduckgo/sogou CAPTCHA）是真实验证环境，不视为环境故障
- 设计文档用项目现有结构（`docs/tasks/` 或 `docs/engineering/`），不用外来目录约定（如 `docs/superpowers/`）
- 已接入执行层 skill：
  - `tdd` / `test-driven-development`：修 bug 或写功能时，先写测试再写实现（red-green-refactor）
  - `systematic-debugging`：遇 bug/测试失败/异常行为时，先系统诊断再提修复方案
- 其余执行层 skill 未接入

## Validation

- 主验证：真实 smoke test — `ask "测试问题"`、MCP `web_search`/`fetch_search_results`，在当前真实环境（SearXNG degraded）下运行，确认不阻塞且返回相关结果
- 回归基线：`.venv\Scripts\python.exe -m unittest <关键子集> -v`
- 关键子集：`tests.test_health_m3 tests.test_mcp_server tests.test_acquisition_m5 tests.test_bridge_runner tests.test_json_contract tests.test_engine_searxng tests.test_mcp_autostart tests.test_agent_flow tests.test_stability_regression`
- bridge/采集验证：`probe --source searxng/mediacrawler --query "test"`、`health --format markdown`、`config show`
- AI 配置验证：`config test-ai`
- 验证环境不可用时处理：AI/bridge 需凭据或外部进程——AI 先尝试启动/设环境变量（可逆），不行再提示用户；测试默认用 fixture，不依赖真实平台

## Seed Tasks

1. 跑真实 smoke test 验证稳定性：`ask "测试问题"` + MCP `web_search`/`fetch_search_results`，在 SearXNG degraded 环境下确认不阻塞且返回相关结果。记录通过/失败和具体问题。
2. 稳定性达标后：结构优化（ToolCallRecorder 拆 agent.py 420 行 `_adaptive_collect` 方法，消除 8 处 tool-call dict 重复构造）。
