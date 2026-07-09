# PROJECT

## Goal

`source-radar` 从"脚本驱动决策的采集引擎"升级为"AI-first 决策的采集引擎"。所有搜索质量评估、fallback 决策、工具选择、采集评估和错误恢复由 AI 语义判断，脚本规则仅在 AI 不可用时降级使用。

核心要解决：脚本硬编码规则代替 AI 语义判断导致搜索质量评估不准、fallback 决策失误、错误恢复静默吞错。AI 不可用时降级到现有脚本规则，不阻塞核心功能。

## Users and Scenarios

- 个人研究者、开发者、AI agent 使用者。
- 通过 CLI 或 MCP 搜资料、找观点、找教程、汇总中文社区经验、核验消息和项目真伪。
- 用户网络环境不稳定，需要依赖下载、源码 clone、浏览器运行时可缓存、可恢复、可离线复用。
- AI agent 调用 MCP 时，需要看到每个 backend 的真实状态、失败原因和修复建议。

## MVP

当前阶段 MVP = "AI-first 决策改造"。

必须保持兼容的入口：

- `ask` / `verify` / `research`
- `mcp`（stdio + SSE）
- `engine install/status/start/stop`
- MCP `source_status` / `web_search` / `fetch_search_results` / `search_chinese_platforms`

改造范围：
- 搜索质量评估：AI 语义判断替代 8 个硬编码检测器
- 搜索 fallback 决策：AI 判断是否换引擎/改词/重试，替代硬编码 quality gate
- 工具选择：AI 评估采集充分性后决定下一步工具，替代优先级表
- 错误恢复：AI 诊断失败原因并建议修复，替代 `except Exception: pass`
- 脚本规则保留为 fallback：AI 不可用时降级到现有逻辑

已落地的 MVP 基础：
- 最小 `AcquisitionKernel` seam。
- `BackendRegistry` + `BackendLifecycleManager.ensure_ready`。
- `EngineInstaller`：下载 manifest、repair、cleanup 诊断。
- `.source-radar/` runtime 收敛。
- `external/` 已退役并迁移完成。
- SearXNG 已改用 `SearXNGNativeProvider`，直接调 upstream HTTP API，不经 bridge 进程。
- `source_status` 展示 lifecycle 诊断和 installer repair 动作。
- MCP SSE transport 支持。
- 退役协议已定义，`_ask_legacy` 和 `external/` 已退役。

## Inputs and Outputs

输入：

- 用户 query / claim / URL / repo。
- 平台、limit、page、nocache 等采集参数。
- 本地 backend 配置、cookie/API key/登录态引用。
- 后端 lifecycle policy、idle timeout、prewarm、start budget、warm/always-on/on-demand 策略。
- 本地源码路径、clone URL、commit/version、下载缓存路径。

输出：

- `ask` / `verify` / `research` 报告和证据卡。
- MCP 工具文本结果。
- backend registry/status/lifecycle 诊断。
- install/repair/probe 诊断。
- 每个后端的真实失败原因、retryable、fix、warnings、diagnostics。

## Non-goals

- 不在 AI-first 改造完成前新增引擎/平台。
- 不删除脚本 fallback（AI 不可用时仍需要）。
- 不破坏 CLI/MCP 入口。
- 不在退役协议定义清楚前新增模式切换。
- 不一次性重写所有中文平台。
- 不做 Web/Desktop UI。
- 不绕过登录、验证码或访问控制。
- 不把 LLM 结论伪装成事实裁定。
- 不恢复旧 `docs/tasks` 流水账和旧 roadmap 作为日常事实源。

## Seed Tasks

1. 审计代码中所有脚本决策点：列出所有用硬编码规则代替 AI 判断的位置（质量评估、fallback、工具选择、错误恢复），标注每个的影响范围和当前行为。
2. AI-first 搜索质量评估：`_assess_quality` 改为 AI 语义判断，脚本检测器降级为 fallback；AI 判断结果语义相关性、来源质量、覆盖度。
3. AI-first fallback 决策：`dispatch_search` 的 quality gate 改为 AI 判断是否需要换引擎/改词/重试，替代 `score == "low"` 硬编码。
4. AI-first 采集评估：evaluator 的工具选择和充分性判断改为 AI 主导，`_collection_priority` 优先级表降级为 fallback。
5. AI-first 错误恢复：后端失败时 AI 诊断原因并建议修复，替代 `except Exception: pass` 静默吞错。
