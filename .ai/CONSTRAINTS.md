# CONSTRAINTS

## Constraints and Working Rules

- Git 是任务状态事实源：每轮开工先核验 `git status`、最近 commit 和当前 diff。
- `.ai/PROJECT.md`、`.ai/TECH.md`、`.ai/CONSTRAINTS.md`、`.ai/VALIDATION.md` 是当前长期基线。
- 旧 `docs/tasks` 流水账、旧 roadmap、旧 design/plan、旧 compose plans 不再作为当前事实源；有历史价值的只作归档参考。
- 当结构、架构或 domain ownership 变化时，只更新仍保留且相关的 canonical docs。
- 不恢复“每次完成都必须更新所有 docs/tasks 索引”的旧流程。
- 收到其他 AI agents、tools 或 handoff 报告时，必须用源码、Git diff、测试或黑盒验证核验。

## Repository and Documentation Ownership

- 当前目标、MVP、Non-goals、Seed Tasks：`.ai/PROJECT.md`
- 技术方向：`.ai/TECH.md`
- 工作规则和 skill 接入：`.ai/CONSTRAINTS.md`
- 验证规则：`.ai/VALIDATION.md`
- 用户入口说明：`README.md`
- 架构、技术栈、backend/runtime 合约：`.ai/TECH.md` 和 `.ai/CONSTRAINTS.md`

## Runtime and Secrets

- 凭据、cookie、登录态、API key、本地源码 checkout、runtime cache 不得 staged/committed/pushed。
- `.source-radar/` 是本地配置、runtime、engine、downloads、logs、pids、cache 根目录；不得提交其中运行态内容。
- `.venv/` 是项目开发/运行环境，不是 backend engine checkout，不迁入 `.source-radar/`。
- 不自动删除 `external/`、browser profiles、cookies/login state、本地 checkout/runtime cache；这些可能含登录态或昂贵下载。
- 新增 engine/backend 的下载、源码 checkout、runtime、日志、pid、缓存路径必须走统一 `.source-radar/` runtime 约定。
- 下载包、wheel cache、源码压缩包、engine checkout、pid、日志、runtime cache 不得散落到多个临时位置；优先进入 `.source-radar/downloads`、`.source-radar/engines`、`.source-radar/runtime`、`.source-radar/pids`、`.source-radar/logs`。
- `external/` 只作为迁移期 legacy fallback；新实现不得继续把它当作主安装位置。

## Backend Rules

- 需要启动、停止、保温、idle stop、失败重试的 backend 必须接入 `BackendLifecycleManager`。
- 不得在 MCP、agent、provider 或 bridge 内部私自实现随用随起、常驻、stop 或 fallback 状态机。
- 使用频繁或启动慢的 backend 优先使用 `warm` / `always-on` 策略；低频 backend 才使用 `on-demand`。
- lifecycle 必须记录启动失败、冷却、最近错误和可执行修复建议，供 `source_status` 或 engine status 展示。
- readiness 不能只测端口；必须尽量测真实能力，例如 import、cookie 状态、输出目录可写、最小请求、上游 JSON 可用或最近错误。
- 后端错误必须保留结构化 reason、message、retryable、fix、warnings、diagnostics 和 fallback 信息。
- 旧 MediaCrawler bridge 迁移期保留为 fallback，不作为新能力的主要架构方向。

## Editing Rules

- 优先最小改动，避免顺手重构。
- 小改文档/代码优先用 `apply_patch`。
- 不为一次性代码创建抽象；不添加未要求的灵活性。
- 删除因当前改动变得未使用的导入、变量、函数；不要清理无关死代码。
- 每一行更改都应能追溯到当前任务。

## Skill Integration

已确认接入执行层 skill：

- `superpowers:systematic-debugging`：用于后端空结果、cookie、限流、安装失败和不稳定行为诊断。
- `mattpocock-skills:codebase-design`：用于采集内核、backend seam、installer/lifecycle 边界设计。
- `superpowers:test-driven-development`：用于新增 backend、installer、registry、lifecycle 或修 bug，先写失败测试。

已确认接入 finish 层 skill：

- `superpowers:requesting-code-review`：用于提交/合并前按 diff 做代码质量检查，检查计划对齐、测试、架构、错误处理和生产可用性。

## Environment Handling

- 验证环境不可用时，AI 先尝试可逆修复；需要凭据、全局安装、管理员权限时再提示用户。
- 代理工具实测不等价于目标工具实测；不能用 curl/probe/browser evaluate 结论冒充目标工具实际结果。
