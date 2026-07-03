# PROJECT

## Goal

`source-radar` 当前目标是从 bridge-first 多服务采集包装器，升级为本地 CLI / MCP 的原生采集内核与统一后端管理引擎。

核心要解决：降低多层 bridge 转化带来的状态错位、错误失真和启动不稳定；统一下载、源码 checkout、runtime/cache、后端生命周期和真实诊断；保持现有 CLI/MCP 用户入口兼容。

## Users and Scenarios

- 个人研究者、开发者、AI agent 使用者。
- 通过 CLI 或 MCP 搜资料、找观点、找教程、汇总中文社区经验、核验消息和项目真伪。
- 用户网络环境不稳定，需要依赖下载、源码 clone、浏览器运行时可缓存、可恢复、可离线复用。
- AI agent 调用 MCP 时，需要看到每个 backend 的真实状态、失败原因、fallback 路径和修复建议。

## MVP

当前 MVP 是“统一采集内核 + backend registry/lifecycle + 统一 runtime/cache + 中文平台 native/local-source 垂直切片”。

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
- 最小 `BackendLifecycleManager.ensure_ready`。
- SearXNG / MediaCrawler MCP 自动启动已接入 lifecycle seam。
- B站 `community.bilibili` native 视频搜索切片。
- `.source-radar/` runtime/cache 目标布局已有 canonical docs。
- 旧 MediaCrawler bridge 仍作为 legacy fallback，不立即删除。

## Inputs and Outputs

输入：

- 用户 query / claim / URL / repo。
- 平台、limit、page、nocache 等采集参数。
- 本地 backend 配置、cookie/API key/登录态引用。
- 后端 lifecycle policy、idle timeout、prewarm、start budget。
- 本地源码路径、clone URL、commit/version、缓存路径。

输出：

- `ask` / `verify` / `research` 报告和证据卡。
- MCP 工具文本结果。
- backend registry/status/lifecycle 诊断。
- install/repair/probe 诊断。
- 每个后端的真实失败原因、retryable、fix、warnings、diagnostics、fallback。

## Non-goals

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

1. 修正 `BackendLifecycleManager.ensure_ready` 的通用性：把 SearXNG 专用 autostart 开关改为通用 backend 开关并兼容旧变量；检查 `subprocess.run` 返回码，把 stdout/stderr 摘要写入结构化 diagnostics。
2. 让 lifecycle/registry 状态可复用或持久化：`source_status` 能展示 `ensure_ready` 产生的 `cooling_down`、failure reason 和 diagnostics，而不是每次临时构造后丢失。
3. 落地最小 `EngineInstaller`：统一 `.source-radar/downloads`、`.source-radar/engines`、metadata、local-source checkout/cache 的接口，先覆盖 SearXNG / MediaCrawler。
4. 迁移剩余硬编码 runtime 路径：通过 path helper 收敛 `external/`、cache、logs、pids、browser/crawl4ai runtime，保留非破坏性 legacy fallback。
5. 继续中文社区 native/local-source 垂直切片：优先扩展 B站 detail/comments 或新增知乎，并保持 MediaCrawler fallback。
