# PROJECT

## Goal

统一 source-radar 的 AI 调用层：ask/verify/research 三个模式各自的 prompt 构建、日期注入、模型调用收敛到 llm.py 单一入口。消除 7 处重复的 prompt 构建，让通用改进（日期/语言/证据载荷）只改一处。

## Users and Scenarios

个人研究者、开发者、AI agent 使用者。场景：搜资料、找观点/案例/教程、核验中文互联网消息（产品/政策/人物/GitHub 项目信息）、通过 MCP 让外部 AI 调用搜索与抓取能力。

## MVP

"AI 调用层统一"= 以下条件同时成立：

1. 日期注入统一：7 处 `today = datetime.now()` 收敛到 `_call_model` 或公共 prompt 前缀
2. 模型调用统一：7 处各自调 `_call_model` 收敛到单一入口（含错误处理/重试）
3. evidence payload 构建统一：多处重复的 `evidence_payload` 构建收敛到公共函数
4. 中文指令统一：所有 prompt 的语言指令在一处维护
5. 现有测试通过 + smoke test 通过（ask/verify/research 不回归）

## Inputs and Outputs

- 输入：问题/断言/URL/平台查询；AI provider 配置；bridge endpoint 与 cookie 配置；空闲阈值配置
- 输出：证据卡、综合分析/核验报告（Markdown/JSON）、MCP 工具结果、health/probe/status 状态

## Non-goals

- 不改 agent 的多轮编排层（`_adaptive_collect` 和 research 采集循环的控制流不动）
- 不改 MCP 协议（7 个工具接口不变）
- 不做 crawl4ai 浏览器实例池优化
- 不做 Web/Desktop UI
- 不绕过登录/验证码/访问控制，不做大规模监控
- 不 vendor MediaCrawler/SearXNG/Firecrawl 源码
- 不把 LLM 结论伪装成事实裁定
- 不引入新框架

## Tech Direction

已有技术栈不变。AI 调用层统一方向：

- 运行时：Python 3.11+（`requires-python = ">=3.11,<3.14"`）
- 包管理：uv + setuptools，`app/` 单应用（`single-app`）
- 测试：标准库 `unittest`
- llm.py 提供单一 AI 调用入口（日期注入 + 模型调用 + 错误处理）
- 各模式（ask/verify/research）只提供 prompt 模板和结果解析，不重复调模型
- 已完成的采集层统一和冷启动优化保持不变

## Constraints and Working Rules

- 凭据（API key / cookie / 登录态）只进本地配置（`.source-radar/` 或环境变量），不得 staged/committed/pushed
- SearXNG 是真实搜索的必选基础设施，通过 bridge 接入，不 vendor 源码
- 外部集成遵守许可证边界：MediaCrawler 非商业、Firecrawl AGPL-3.0、Trafilatura GPL-3.0
- 健康检查统一走 `BridgeHealth`（`health.py`）
- `_http_ok` 统一定义在 `runtime.py`
- 采集层已统一：agent.py / mcp/server.py 不得新建独立的搜索/抓取/缓存逻辑
- 服务启停不新建实现，复用 engine 层现有逻辑
- AI 调用统一后，不得在各模式中新建独立的日期注入/模型调用/prompt 前缀逻辑
- 设计文档用项目现有结构（`docs/tasks/` 或 `docs/engineering/`），不用外来目录约定
- 已接入执行层 skill：`tdd`/`test-driven-development`、`systematic-debugging`
- 其余执行层 skill 未接入

## Validation

- 回归测试：`.venv\Scripts\python.exe -m unittest <关键子集> -v`
- 关键子集：`tests.test_mcp_server tests.test_acquisition_m5 tests.test_agent_flow tests.test_stability_regression tests.test_quality tests.test_quality_fixes tests.test_quality_p2 tests.test_prewarm tests.test_idle_watchdog tests.test_parallel_fetch tests.test_unified_search tests.test_unified_fetch tests.test_unified_providers tests.test_unified_github`
- Smoke test：`ask`/`verify`/`research` 不回归
- 重复检查：grep 确认 `today = datetime.now` 在 llm.py 中只出现一次

## Seed Tasks

1. 抽取统一 AI 调用入口：`_call_model` 加日期注入前缀，7 处调用改为传 prompt body 而非完整 prompt
2. 统一 evidence payload 构建：多处重复的 `_evidence_payload_with_budget` 收敛
3. 统一中文指令和 prompt 前缀：所有 prompt 的公共部分（日期/语言/角色）在一处维护
