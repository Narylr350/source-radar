# PROJECT

## Goal

`source-radar` 从 bridge-first 多服务采集包装器升级为本地 CLI / MCP 的统一后端管理与采集内核；并建立状态演进退役协议，确保每次模式切换都明确定义旧模式的死亡条件、入口删除清单、测试失效清单和文档降级清单。

核心要解决：降低多层 bridge 转化带来的状态错位、错误失真和启动不稳定；优先统一下载、源码 checkout、runtime/cache、后端生命周期和真实诊断；保持现有 CLI/MCP 用户入口兼容。中文平台 native/local-source 是后续迁移方向，不再优先于安装、下载、runtime 和 lifecycle 稳定性。

## Users and Scenarios

- 个人研究者、开发者、AI agent 使用者。
- 通过 CLI 或 MCP 搜资料、找观点、找教程、汇总中文社区经验、核验消息和项目真伪。
- 用户网络环境不稳定，需要依赖下载、源码 clone、浏览器运行时可缓存、可恢复、可离线复用。
- AI agent 调用 MCP 时，需要看到每个 backend 的真实状态、失败原因和修复建议。

## MVP

当前阶段 MVP = "稳固内核 + 退役协议"。

必须保持兼容的入口：

- `ask`
- `verify`
- `research`
- `mcp`
- `engine install/status/start/stop`
- MCP `source_status`
- MCP `search_chinese_platforms`

已落地的 MVP 基础：

- 最小 `AcquisitionKernel` seam。
- 最小 `BackendRegistry`。
- `BackendLifecycleManager.ensure_ready` 统一随用随起入口。
- `EngineInstaller`：下载 manifest、repair、cleanup 诊断。
- `.source-radar/` runtime 收敛（engines/downloads/runtime/pids/logs/cache/browser-profiles/crawl4ai/sessions/tmp）。
- `external/` fallback 已移除；SearXNG / MediaCrawler 只认 `.source-radar/engines/.../source`。
- `source_status` 展示 lifecycle 诊断和 installer repair 动作。
- SearXNG / MediaCrawler MCP 自动启动已接入 lifecycle seam。
- B站 `community.bilibili` native 视频搜索切片作为 native/local-source 迁移示范。

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

- 不在退役协议定义清楚前新增模式切换。
- 不在安装、下载、runtime、lifecycle 稳定前继续扩张中文平台 native 切片。
- 不一次性重写所有中文平台。
- 不一次性删除旧 bridge。
- 不破坏 CLI/MCP 入口。
- 不做 Web/Desktop UI。
- 不做远程 SaaS 分发优先。
- 不绕过登录、验证码或访问控制。
- 不把 LLM 结论伪装成事实裁定。
- 不把安装系统做成通用包管理器。
- 不随主仓库分发第三方源码；第三方源码走本地 clone/cache。
- 不恢复旧 `docs/tasks` 流水账和旧 roadmap 作为日常事实源。

## Seed Tasks

1. 定义状态演进退役协议：在 `.ai/CONSTRAINTS.md` 写明每次模式切换必须输出的退役清单（旧模式死亡条件、入口删除清单、测试失效清单、文档降级清单）；审计当前 `_ask_legacy` / `bridge` / `external/` 残留，明确每个的死亡条件。
2. lifecycle/installer edge case 加固：补测试覆盖 cooling_down 恢复、repair 失败重试、download 断点复用、idle timeout 与 prewarm 冲突等 edge case。
3. `_ask_legacy` thin wrapper 化：改成薄转发到 canonical 采集/证据/trace 管线，删除独立 ask 状态机，同步处理旧测试。
4. `source-radar bridge` 退役边界定义：明确 `bridge` 命令何时删除、哪些测试必须失效、文档如何降级；评估是否能被 `engine start` + native/local-source adapter 替代。
5. source_status 观测性收尾：确保所有 backend 状态（cooling_down / repair_failed / download_partial / idle_stopped）都有结构化诊断，不再临时构造后丢失。
