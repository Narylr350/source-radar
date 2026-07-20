# CONSTRAINTS

## Constraints and Working Rules

- Git 是任务状态事实源：开工先核验分支、status、最近 commit 和当前 diff。
- `.ai/PROJECT.md`、`.ai/TECH.md`、`.ai/CONSTRAINTS.md`、`.ai/VALIDATION.md` 是当前长期基线。
- README 是用户入口说明，必须依据已落地源码更新，不提前宣传计划能力。
- 旧 `docs/tasks`、roadmap、design/plan 和 handoff 不是当前事实源。
- 其他 AI、工具或旧交接的结论必须用源码、Git diff、测试或黑盒验证核验。

## Architecture Boundary

- 当前中文平台目标是直接接入 MediaCrawler 固定版本本地源码，删除 source-radar HTTP bridge；不是在 source-radar 中重写 MediaCrawler。
- MediaCrawler 负责平台 endpoint、签名、登录、Cookie、搜索、详情、评论和平台风控实现。
- source-radar 负责 adapter、MCP、registry、installer、lifecycle、状态、缓存和证据转换。
- 不得以“native 化”为名在 source-radar 中复制 MediaCrawler 已存在的平台协议实现，除非用户明确决定彻底替代该平台的上游实现。
- local-source adapter 必须形成单一边界；调用方不得散落 import MediaCrawler 内部模块或修改其全局配置。
- 如需 patch 固定 checkout，patch 必须版本固定、可审计、可重放，并记录适用 commit。

## Canonical Path and No Legacy Fallback

- 每项能力只能有一条 canonical 内部路径。
- local-source 路径完成后，同一迁移必须删除对应 native 重写、HTTP bridge、旧配置、旧测试和旧文档。
- 不保留 `local-source → BilibiliNativeBackend` fallback。
- 不保留 `local-source → MediaCrawlerBridgeBackend` fallback。
- 目标路径缺失或失败时明确返回 not-installed、needs-input、unsupported 或 backend-failed，不偷偷调用旧路径。
- 允许公开入口作为薄转发保留，但不得保留独立状态机、错误语义或采集实现。
- “fallback”如表示不同能力的显式降级，必须可观测并由当前功能需求证明；不得用来掩盖未完成迁移。

## MediaCrawler Source Rules

- MediaCrawler checkout 位于 `.source-radar/engines/mediacrawler/source`。
- checkout 必须固定 commit/version，并有 metadata；不得默认跟随上游 HEAD。
- MediaCrawler 源码、其 `.venv`、浏览器数据、数据库和输出文件不得进入 source-radar Git。
- source-radar 不依赖用户手工 clone 到任意绝对路径。
- 安装包、源码压缩包和 wheel 统一进入 `.source-radar/downloads`。
- 浏览器登录态统一进入 `.source-radar/browser-profiles` 或 adapter 明确定义的受控路径。
- 不自动删除 browser profile、Cookie、session 或昂贵下载。
- 普通 search/status 不得隐式执行 install；大型安装只允许显式 MCP/CLI 操作。

## Backend and Lifecycle Rules

- 需要启动、停止、保温、idle stop 或失败重试的 backend 必须接入 `BackendLifecycleManager`。
- adapter、MCP handler 和 provider 不得私自建立第二套 lifecycle。
- readiness 不得只检查端口；local-source backend 应检查 checkout、commit、依赖、运行目录、session 和最小能力。
- 状态至少保留 `reason`、`message`、`retryable`、`fix`、`warnings`、`diagnostics`。
- `fix` 优先表达可由 MCP 执行的动作，不给外部 AI 返回依赖项目绝对路径的伪命令。
- start/install/status/stop 的状态语义必须来自同一 registry/lifecycle 事实源。

## MCP Rules

- MCP schema 和 description 必须反映当前真实实现。
- 机器判断不得依赖重新解析自然语言结果。
- 平台 capability、实际 backend、缓存来源和错误类别必须结构化可见。
- install 只能显式调用；start 是否自动执行由 backend policy 决定并可通过 MCP 开关控制。
- 新增或修改 MCP 工具时同时验证 `tools/list`、handler 和真实 transport。
- 外部 AI 不需要知道仓库目录、Python 模块入口或 `uv run` 命令。

## State Evolution Retirement Checklist

每次模式切换必须同步处理：

1. 旧模式死亡条件。
2. 入口删除清单。
3. 测试删除或改写清单。
4. 配置和状态字段删除清单。
5. README/MCP schema/基线文档同步清单。
6. grep 或语义搜索证明无调用方残留。

说不清谁在调用、为何保留、何时删除的内部旧路径，视为迁移未完成。

## Current Retirement Ledger

### Bilibili independent native search

- 当前文件：`app/source_radar/backends/community/bilibili.py`。
- 当前用途：绕过 MediaCrawler，直接调用 B站非 WBI 搜索 endpoint。
- 定位：已验证 MCP native 路由的过渡实现，不是目标架构。
- 死亡条件：Bilibili search/detail/comments/session-status 已通过 MediaCrawler local-source adapter 和 MCP 验证。
- 删除项：`BilibiliNativeBackend`、专用路由、专用 fallback 禁止测试及相关描述；改写为 local-source contract 测试。
- 不允许：扩展该类实现 WBI、详情、评论或登录，以免继续复制 MediaCrawler。

### MediaCrawler HTTP bridge

- 当前残留：`MediaCrawlerBridgeBackend`、`ExternalBridgeProvider("mediacrawler")`、bridge CLI、bridge port、BridgeHealth 和 engine bridge 启动链。
- 死亡条件：所有仍声明支持的中文平台均通过 local-source adapter 到达 MediaCrawler 源码。
- 删除项：HTTP adapter host、bridge CLI、bridge endpoint 配置、端口检查、provider、health、测试和文档。
- 不允许：为了 local-source 迁移再增加 bridge v2 或另一套长期 IPC 协议。

### `external/`

- 已退役，不参与运行。
- 旧 checkout 自动迁移逻辑仅作为有明确删除计划的安装迁移代码存在，不得成为运行 fallback。

## Runtime and Secrets

- Cookie、API key、登录态、browser profile、本地 checkout、runtime、pid、日志和缓存不得 staged/committed/pushed。
- `.source-radar/` 是统一本地运行根目录。
- `.venv/` 是 source-radar 开发环境，不是 engine checkout。
- 临时文件进入 `.source-radar/tmp` 或系统临时目录，用完删除。

## Editing Rules

- 只改当前任务必要内容，不顺手重构无关代码。
- 优先使用 JetBrains/结构化文件工具编辑；shell 保留给 Git、构建、测试和无结构化工具覆盖的诊断。
- 删除当前修改造成的未使用代码，不清理无关死代码。
- 每一行修改都应能追溯到当前任务。

## AI Responsibility

- AI 用于适合语义判断的搜索规划、质量评估、证据充分性和综合。
- 确定性脚本负责可重复的协议边界、状态机、安装、缓存和验证。
- AI-first 是模块设计选择，不是所有项目功能的全局铁律。
