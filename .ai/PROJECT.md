# PROJECT

## Goal

`source-radar` 的新阶段目标是从“AI 友好的多 bridge 采集包装器”升级为“原生采集内核 + 统一后端安装/状态管理”的本地 CLI / MCP 采集引擎。

核心问题：

1. 降低 bridge 带来的多层转化、服务状态错位、错误信息失真和运行不稳定。
2. 统一安装体验，把 pip/uv 下载、源码 clone、本地缓存、服务启动、cookie 检查、probe/status 都收敛到 `engine install/status/repair` 一套机制里。
3. 清理旧工作流和过期文档，让当前工作只受 `.ai/PROJECT.md`、当前对话、Git 事实和少量 canonical docs 约束，不再被历史任务流水账牵引。

## Users and Scenarios

目标用户：

- 个人研究者、开发者、AI agent 使用者。
- 需要搜资料、找观点、找案例、找教程。
- 需要核验中文互联网消息、产品变化、政策变化、人物动态、GitHub 项目真伪。
- 需要通过 CLI 或 MCP 让外部 AI 调用搜索、抓取、中文社区采集能力。

关键场景：

- 用户希望 `ask` / `verify` / `research` / MCP 外部入口保持稳定，但底层采集更可靠。
- 用户网络环境不稳定，希望依赖下载、源码 clone、浏览器运行时安装可缓存、可恢复、可离线复用。
- AI agent 使用 MCP 时，需要看到每个 backend 的真实状态，而不是笼统的 `bridge unreachable` 或“未找到结果”。
- 维护者希望先清理旧 workflow 和过期 docs，避免新架构工作被历史文档误导。

## MVP

第一版 MVP 聚焦“干净基线 + 统一 runtime/cache + 一个中文平台 native/local-source 垂直切片”，不一次性重写所有平台。

MVP 必须同时成立：

1. 外部 CLI/MCP 入口兼容：
   - `ask`
   - `verify`
   - `research`
   - `mcp`
   - `engine install/status/start/stop`
   - `source_status`
   - `search_chinese_platforms`

2. 项目结构先清理干净：
   - 清理或归档不再指导当前工作的旧 workflow、过期任务文档、重复 design/plan。
   - 明确保留的事实源：`.ai/PROJECT.md`、`README.md`、必要 `AGENTS.md`、`docs/context/architecture.md`、`docs/context/tech-stack.md`、必要 `docs/engineering/` 合约。
   - 历史 `docs/tasks` 流水账和旧任务索引不再强制作为日常写回目标；有历史价值的归档，无价值或误导的删除。

3. 统一本地运行态与下载缓存：
   - engine 源码、下载包、wheel cache、浏览器运行时、pid、日志和临时运行数据都收敛到 `.source-radar/` 下的明确子目录。
   - 不再长期依赖散落的 `.venv/`、`external/`、用户全局 cache 或默认 Playwright cache 作为业务后端运行态。

4. 新增统一采集内核：
   - CLI/MCP 调用稳定的 `AcquisitionKernel` 或等价深模块。
   - 调用方不直接感知 bridge、MediaCrawler、SearXNG、clone 路径、cookie 文件、浏览器目录。

5. 新增 backend registry：
   - 记录 backend 类型：native / local-source / service / legacy-bridge。
   - 记录安装状态、版本/commit、本地路径、诊断信息。
   - `source_status` 和 `engine status` 基于 backend registry 输出。

6. 新增 local-source 安装路径：
   - `engine install community` 可安装或定位中文社区采集后端。
   - 支持本地 clone/cache；后续支持本地路径和压缩包安装。
   - 用户不需要手动理解“一会儿 clone、一会儿 pip、一会儿启动 bridge”。

7. 做通第一个中文平台 native/local-source backend 垂直切片：
   - 优先建议 B 站或知乎。
   - `search_chinese_platforms("周杰伦", platforms=[...])` 能返回真实结果，或给出明确诊断。
   - 能区分 cookie 缺失/过期、平台限流、后端异常、真无结果。

8. 旧 MediaCrawler bridge 不立即删除：
   - 第一阶段作为 fallback/legacy。
   - 成功跑通 native/local-source 后再逐步降级或移除。

## Inputs and Outputs

输入：

- 用户 query / claim / URL / repo。
- 平台选择、limit/page/nocache 等采集参数。
- 本地 backend 配置。
- 本地源码路径、clone URL、commit hash、缓存路径。
- cookie/API key/登录态引用。
- AI provider 配置。

输出：

- 证据卡。
- `ask` / `verify` / `research` 报告。
- MCP 工具文本结果。
- backend status。
- install/repair/probe 诊断。
- 每个后端的真实失败原因、fix、retryable、warnings、diagnostics。

## Non-goals

当前阶段不做：

- 不重写所有中文平台。
- 不一次性删除旧 bridge。
- 不改 CLI/MCP 用户入口。
- 不做 Web/Desktop UI。
- 不做大规模监控。
- 不绕过登录、验证码或访问控制。
- 不把 LLM 结论伪装成事实裁定。
- 不把安装系统做成通用包管理器。
- 不优先做远程 SaaS 分发。
- 不为了许可证形式问题阻塞本地源码级接入，但第一阶段仍优先“不随主仓库分发第三方源码”。
- 不在第一轮 cleanup 中重写业务逻辑或迁移所有 backend；第一轮只清理结构和文档事实源，为后续改造准备干净环境。

## Tech Direction

- Runtime 继续 Python 3.11+。
- 包管理继续 uv + setuptools。
- 外部 CLI/MCP contract 尽量不破坏。
- 架构重心从 bridge-first 转向：
  - `AcquisitionKernel`
  - `BackendRegistry`
  - `EngineInstaller`
  - native/local-source backend
- 第三方源码第一阶段通过本地 clone/cache 进入 `.source-radar/engines` 或等价 ignored runtime 目录，不进入主仓库。
- 对于重型服务型后端，例如 SearXNG，仍可保留 service backend。
- 对于中文社区平台，优先从 bridge 迁到 local-source/native backend。
- 旧 bridge 标记为 legacy/fallback，而不是继续作为主要路径。
- `EngineInstaller` 不只是安装命令包装，而是统一下载、缓存、local-source checkout、运行时目录、修复和状态登记的模块。后续 backend 不允许各自发明安装路径。

目标 runtime/cache 形态：

```text
.source-radar/
  engines/
    mediacrawler/
    searxng/
    crawl4ai/
  downloads/
    MediaCrawler-<commit>.zip
    searxng-<version>.zip
    wheels/
  runtime/
    venvs/
    browser-profiles/
    crawl4ai/
  pids/
  logs/
  config.json
```

建议目标代码形态：

```text
app/source_radar/
  acquisition/
    kernel.py
    types.py
    diagnostics.py
    normalization.py
  backends/
    registry.py
    installer.py
    community/
    search/
    web/
    github/
  mcp/
    server.py
```

具体文件名和迁移步骤在实现阶段按现有代码最小改动调整。

## Constraints and Working Rules

- `.ai/PROJECT.md` 是当前长期基线；旧 `docs/tasks` 流水账、旧 roadmap、旧 design/plan 不再自动作为当前事实源。
- 旧工作流必须清理干净，不能继续影响当前工作流；清理前如有冲突，以 `.ai/PROJECT.md` 和用户当前明确指令为准。
- Git 是任务状态事实源：每轮开工先核验 `git status`、最近 commit 和当前 diff。
- 当结构、架构或 domain ownership 变化时，更新少量仍保留的 canonical docs；不要恢复“每次完成都必须更新所有 docs/tasks 索引”的旧流程。
- 凭据、cookie、登录态、API key、本地源码 checkout、runtime cache 不得 staged/committed/pushed。
- 本地源码后端应记录 repo URL、commit/version、本地路径、license/notice 信息，但路径和凭据留在本地配置。
- 任何新增 engine/backend 的下载、源码 checkout、runtime、日志、pid、缓存路径必须走统一 `.source-radar/` runtime 约定；不得新增散落目录。
- AI 收到其他 agent/report/handoff 结论时必须核验源码和测试，不直接相信结论。
- 优先小切片推进：先清理结构，再做统一 runtime/cache，再做 registry/kernel，再做一个平台的 native/local-source backend。
- 已接入执行层 skill：
  - `systematic-debugging`：用于后端空结果、cookie、限流、安装失败诊断。
  - `codebase-design`：用于采集内核和 backend seam 设计。
  - `test-driven-development`：用于新增 backend/installer/registry 时先补 contract tests。
- 验证环境不可用时，AI 先尝试可逆修复；需要凭据、全局安装、管理员权限时再提示用户。

## Validation

基础验证：

```powershell
.venv\Scripts\python.exe -m unittest tests.test_mcp_server -v
.venv\Scripts\python.exe -m unittest tests.test_acquisition_m5 tests.test_agent_flow tests.test_stability_regression -v
```

新增 MVP 验证：

- cleanup 后 `git status` 只包含预期文档/结构变更。
- 保留的 canonical docs 不再要求旧 `docs/tasks` 强制写回。
- `.source-radar/` runtime/cache 目录约定有测试或静态检查覆盖。
- backend registry 单测。
- engine installer 单测。
- local-source backend fixture 单测。
- `source_status` 能展示 backend 类型和真实诊断。
- `search_chinese_platforms` 对第一个 native/local-source 平台有正向 smoke 或明确诊断。
- 旧 bridge fallback 路径不回归。
- CLI `ask/verify/research` 命令帮助和基础 smoke 不回归。

手动验证：

```powershell
source-radar engine install community
source-radar engine status
source-radar mcp
```

MCP 黑盒验证：

- `source_status`
- `search_chinese_platforms`
- `web_search`
- `fetch_url`

## Seed Tasks

1. 项目结构清理与文档瘦身：盘点 `docs/`、`skills/`、`external/`、`.source-radar/`、`.venv/`、旧 workflow 文件；删除或归档不再相关的 workflow/docs；明确保留的 canonical docs；更新 `README.md`、`AI_CONTEXT.md`、`docs/context/architecture.md`；不改采集行为，只整理基线环境。
2. 统一 runtime/cache 目录设计：定义 `.source-radar/engines`、`downloads`、`runtime`、`pids`、`logs` 的职责；更新 `.gitignore`；梳理当前 `.venv/`、`external/`、Playwright、Crawl4AI、SearXNG、MediaCrawler 的落点；形成迁移规则和测试目标。
3. 设计并落地 `BackendRegistry` 最小模型：记录 backend 类型、状态、安装来源、commit/version、本地路径引用、诊断字段；让 `engine status` / `source_status` 有统一数据来源。
4. 抽出 `AcquisitionKernel` seam：CLI/MCP 通过统一入口调用采集能力；先保持旧 provider 行为不变；旧 bridge 仍可作为 legacy/fallback。
5. 实现第一个中文平台 local-source/native backend 垂直切片：建议优先 B 站或知乎；支持真实结果或明确诊断；区分 cookie 缺失/过期、限流、后端异常、真无结果。
