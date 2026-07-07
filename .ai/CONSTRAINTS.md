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
- 不自动删除 browser profiles、cookies/login state、本地 runtime cache；这些可能含登录态或昂贵下载。
- 新增 engine/backend 的下载、源码 checkout、runtime、日志、pid、缓存路径必须走统一 `.source-radar/` runtime 约定。
- 下载包、wheel cache、源码压缩包、engine checkout、pid、日志、runtime cache 不得散落到多个临时位置；优先进入 `.source-radar/downloads`、`.source-radar/engines`、`.source-radar/runtime`、`.source-radar/pids`、`.source-radar/logs`。
- `external/` 不得作为安装、启动、状态检查或采集 fallback；如本机仍存在，仅视为 ignored 历史残留。

## Backend Rules

- 需要启动、停止、保温、idle stop、失败重试的 backend 必须接入 `BackendLifecycleManager`。
- 不得在 MCP、agent、provider 或 bridge 内部私自实现随用随起、常驻或 stop 状态机。
- 使用频繁或启动慢的 backend 优先使用 `warm` / `always-on` 策略；低频 backend 才使用 `on-demand`。
- lifecycle 必须记录启动失败、冷却、最近错误和可执行修复建议，供 `source_status` 或 engine status 展示。
- readiness 不能只测端口；必须尽量测真实能力，例如 import、cookie 状态、输出目录可写、最小请求、上游 JSON 可用或最近错误。
- 后端错误必须保留结构化 reason、message、retryable、fix、warnings 和 diagnostics。
- 不保留历史路径兜底；目标路径缺失就明确 missing，不偷偷回退到历史 checkout。

## State Evolution Rules — 退役协议

- 把 CLI / Skill / MCP / engine / bridge / 状态机 / 工具箱这类变化视为"状态演进"，不是普通功能新增。
- 每次模式切换必须输出退役清单，四项缺一不可：
  1. **旧模式死亡条件**：可观测的退出标志（如"某个入口无调用方""某个测试已删除""某个路径无引用"），不是模糊的"以后删除"。
  2. **入口删除清单**：哪些 CLI / MCP / API 入口必须删除，哪些保留为薄转发。
  3. **测试失效清单**：哪些旧测试必须删除或改写，不能让测试继续保护旧模式。
  4. **文档降级清单**：哪些文档从事实源降级为历史参考，哪些需要同步更新。
- 不能只新增新层然后把旧层留作隐式 fallback；公开用户入口可以兼容保留，但必须薄转发到 canonical 内部路径，不得保留独立采集、启动、状态、错误语义或文档事实源。
- 内部旧路径如果仍存在，必须能说明：谁还在调用、为什么暂时保留、删除条件是什么。说不清的 legacy 视为迁移未完成。
- `bridge` 当前只允许作为 SearXNG / MediaCrawler 等本地 service 的 adapter host，并由 `engine start` / `BackendLifecycleManager` 管理；不得恢复成绕过 registry/lifecycle 的第二套后端状态机。
- 后续处理 `VerificationAgent._ask_legacy`、`source-radar bridge ...` 或其它带 legacy 命名的路径时，优先改成 thin wrapper 或删除；不要继续在其内部新增行为。
- 删除或替换旧状态时，必须同步处理旧测试和旧文档契约，不能让测试继续保护旧模式。

## Legacy Retire Ledger — 当前残留退役清单

每项必须能回答：谁还在调用、为什么保留、死亡条件是什么。说不清的视为迁移未完成。

### 1. `VerificationAgent._ask_legacy`（agent.py:387）— ✅ 已退役

- **状态**：已删除。`ask` 方法统一处理 adaptive 和 explicit source 路径，共享 `_finish_ask` 后采集管线。
- **退役 commit**：本轮 Seed Task 3。
- **测试改写**：`test_v3_hardening.py` 中 3 个测试从 `test_ask_legacy_*` 改名为 `test_ask_explicit_source_*`，验证 canonical 管线等价行为。

### 2. `source-radar bridge` CLI 命令（bridge.py:543-565, cli.py:186,821）

- **当前调用方**：`cli.py:186` 注册 `bridge` 子命令；`cli.py:821` 执行 `run_bridge_from_args`。`engine start` 内部通过 `subprocess.Popen([sr_py, "-m", "source_radar", "bridge", ...])` 调用 bridge CLI 作为子进程启动 adapter host（engine.py:1054-1060 SearXNG, engine.py:1122-1127 MediaCrawler）。
- **为什么保留**：`engine start` 当前通过 subprocess 调用 `source-radar bridge` CLI 子命令来启动 HTTP adapter host，而不是直接调用 `serve_bridge()` 函数。bridge CLI 是 `engine start` 的实现细节，不是用户独立入口。
- **退役 gap**：`engine start` 需要改为直接调用 `serve_bridge(backend, host, port)` 函数（在子进程或线程中），不再通过 `subprocess.Popen` 启动 bridge CLI 子命令。
- **死亡条件**：
  1. `engine start` 不再通过 `subprocess.Popen` 调用 `source-radar bridge` CLI 子命令。
  2. `serve_bridge()` 函数能被 `engine start` 直接调用（子进程内 `import` + 调用，或 threading）。
  3. bridge CLI 子命令无调用方（grep 确认 `cli.py` 中不再注册 `bridge` 子命令）。
- **入口删除清单**：
  - `cli.py`：删除 `bridge` 子命令注册（`add_bridge_subparsers(bridge)`）和 dispatch（`run_bridge_from_args(args)`）。
  - `bridge.py`：删除 `add_bridge_subparsers` / `build_bridge_parser` / `run_bridge_from_args`。保留 `serve_bridge` 函数（`engine start` 直接调用）。
- **测试失效清单**：
  - `test_bridge_runner.py`（13 测试）：验证 `serve_bridge` 和 backend 行为，不依赖 CLI 子命令 → 保留。
  - `test_cli.py` 中 bridge help / bridge provider 相关测试 → 删除或改写为验证 `engine start` 启动 adapter。
  - 其余 bridge 引用测试（`test_health_m3.py` / `test_integrations_m4.py` / `test_agent_flow.py` / `test_stability_regression.py` / `test_runtime_paths.py` / `test_mcp_server.py` / `test_unified_providers.py` / `test_bilibili_backend.py`）→ 这些测试验证的是 BridgeHealth / ExternalBridgeProvider / bridge backend 行为，不是 CLI 子命令 → 保留，直到 bridge backend 本身被 native/local-source adapter 替代。
- **文档降级清单**：
  - `README.md`：移除 `source-radar bridge` 相关说明（如有）。
  - `.ai/TECH.md` Entry Modes 表中 `bridge` 行标记为"待删除——engine start 实现细节"。
- **不在本次删除**：`serve_bridge` 函数、`MediaCrawlerBridgeBackend` / `SearXNGBridgeBackend` 类、`BridgeHealth`。这些是 service adapter 实现，不是 CLI 入口；它们被 native/local-source adapter 替代是后续工作。

### 3. `external/` 路径引用

- **当前调用方**：`cli.py:139` — `uninstall --project` help 文本提及 `external/` 作为清理目标。
- **为什么保留**：本机可能仍有旧 `external/` 残留，`uninstall --project` 仍清理它作为用户友好行为。
- **死亡条件**：`external/` 已不参与安装、启动、状态检查和采集路径（commit `d4e3d1c` 已完成）。`uninstall` 清理 `external/` 是可选的用户友好行为，不阻塞退役。
- **入口删除清单**：无入口需删除。`uninstall --project` help 文本可保留"清理 external/（如有）"或移除。
- **测试失效清单**：`test_engine_searxng.py:110`（测试数据中的旧路径，可保留）；`test_engine_installer.py:93,462` 和 `test_mcp_server.py:1755`（断言 NOT 包含 `external/`，是保护性测试，应保留防止回退）。
- **文档降级清单**：`.ai/TECH.md` 中 `external/` 相关说明已标注"不参与运行路径"，无需进一步降级。

## Editing Rules

- 优先最小改动，避免顺手重构。
- 小改文档/代码优先用 `apply_patch`。
- 不为一次性代码创建抽象；不添加未要求的灵活性。
- 删除因当前改动变得未使用的导入、变量、函数；不要清理无关死代码。
- 每一行更改都应能追溯到当前任务。

## Skill Integration

已确认接入执行层 skill：

- `superpowers:systematic-debugging`：用于后端空结果、cookie、限流、安装失败和不稳定行为诊断。
- `superpowers:test-driven-development`：用于新增 backend、installer、registry、lifecycle 或修 bug，先写失败测试。

已确认接入 finish 层 skill：

- `superpowers:requesting-code-review`：用于提交/合并前按 diff 做代码质量检查，检查计划对齐、测试、架构、错误处理和生产可用性。

## Environment Handling

- 验证环境不可用时，AI 先尝试可逆修复；需要凭据、全局安装、管理员权限时再提示用户。
- 代理工具实测不等价于目标工具实测；不能用 curl/probe/browser evaluate 结论冒充目标工具实际结果。
