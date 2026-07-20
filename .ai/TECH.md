# TECH

## Tech Direction

- Runtime：Python 3.11+。
- 包管理：`uv` + setuptools。
- 测试：标准库 `unittest`，backend/adapter/lifecycle/MCP 行为使用 focused tests 和必要的真实 transport 黑盒验证。
- 项目形态：single app，核心源码位于 `app/source_radar/`。
- 外部入口保持 CLI + MCP；内部收敛到统一 acquisition/backend/runtime 模型。
- 中文平台采用固定版本 MediaCrawler local-source integration，不在 source-radar 中逐个平台复制协议实现。

## Architecture Direction

```text
CLI / MCP
  ↓
AcquisitionKernel
  ├─ BackendRegistry
  ├─ BackendLifecycleManager
  ├─ EngineInstaller
  ├─ Capability Registry
  └─ Evidence Normalizer
       ↓
MediaCrawlerLocalSourceBackend
       ↓
.source-radar/engines/mediacrawler/source
       ↓
MediaCrawler platform client/crawler
```

职责边界：

### source-radar owns

- MCP 和 CLI 工具协议。
- backend/platform capability 发现。
- engine 下载、固定 commit、metadata、repair 和缓存。
- lifecycle、ready、warm、idle stop、失败冷却。
- MediaCrawler 调用参数适配和运行隔离。
- MediaCrawler 输出到 `CandidateSource` / `SourceItem` / diagnostics 的转换。
- 缓存、证据追踪、状态和可执行恢复动作。

### MediaCrawler owns

- 平台 endpoint 和请求参数。
- WBI 或其他签名算法。
- User-Agent、Referer、Cookie 和浏览器登录实现。
- 平台搜索、详情、评论、回复和分页协议。
- 平台风控相关行为和协议更新。

source-radar 不复制以上平台协议；如上游接口不适合库调用，优先建立明确的 local-source adapter 或对固定 checkout 应用可审计 patch，而不是在核心中重新实现一份。

## Local-source Integration Boundary

MediaCrawler 当前不是天然 library，需要先处理：

- 项目根目录式 import。
- 顶层全局 `config`。
- Playwright `Page` / `BrowserContext` 生命周期。
- store callback 和批量落盘耦合。
- crawler type、keyword 等 context/global state。
- 登录态和 browser profile。
- 日志、代理和运行目录。

adapter 必须将这些耦合限制在单一边界内。调用方只面对 source-radar 自己的 request/result/status 合约，不直接 import 任意 MediaCrawler 内部模块。

优先顺序：

1. 复用 MediaCrawler 平台 client 和签名实现。
2. 绕开与 source-radar 无关的数据库/store 批处理层。
3. 保留必要 browser/session 生命周期。
4. 将 source checkout 的 import/config 污染隔离在 adapter 或受控 worker 中。
5. 如必须使用子进程，使用单一受控 local-source worker 和结构化 IPC，不恢复面向调用方的独立 HTTP bridge、端口和第二套 health/config 状态机。

## Canonical Paths

| 能力 | canonical path |
|---|---|
| Web search | MCP/CLI → `SearXNGNativeProvider` → SearXNG upstream |
| Web fetch | MCP/CLI → unified fetch → Trafilatura/Crawl4AI capability path |
| GitHub | MCP → GitHub native provider |
| Chinese community | MCP/CLI → `MediaCrawlerLocalSourceBackend` → pinned local source |
| Backend management | MCP/CLI → `BackendLifecycleManager` + `EngineInstaller` |
| Status | registry + capability + installer + lifecycle + session diagnostics |

`BilibiliNativeBackend` 是当前过渡实现，不是目标架构。Bilibili local-source 切换成功时必须同步删除它和保护它的路由测试。

## Capability Model

平台能力至少表达：

```text
platform
backend_key
backend_type
search
detail
comments
sub_comments
pagination
requires_cookie
session_status
installed
ready
```

未支持能力返回结构化 `unsupported/capability-not-supported`，不得调用另一条历史路径补齐。

## MCP Direction

- 工具描述必须反映实际 backend，不得把 Bilibili local-source/native 说成必须经过 bridge。
- `source_status` 返回平台 capability、安装、运行、登录和最近错误，而不仅是端口状态。
- `manage_backend` 不要求调用者知道项目路径；install 必须显式触发。
- 搜索、详情和评论返回稳定结构化内容，同时保留人类可读摘要。
- 长任务提供 progress；错误区分 timeout、auth、rate-limit、unsupported、not-installed 和 backend-failed。
- MCP handler 单测不能替代真实 stdio/SSE transport 验证。

## Runtime Layout

```text
.source-radar/
  config.json
  local.env
  engines/
    mediacrawler/
      source/
      metadata.json
      patches/
    searxng/
      source/
      metadata.json
  downloads/
    MediaCrawler-<commit>.zip
    searxng-<version>.zip
    wheels/
  browser-profiles/
  sessions/
  runtime/
  pids/
  logs/
  cache/
  tmp/
```

- 下载一次，多次复用。
- 固定 commit/version 可审计。
- 支持断点、repair、离线复用和集中清理。
- `external/` 不参与安装、启动、状态或 fallback。
- `.venv/` 是 source-radar 开发环境，不是 engine checkout。

## State Evolution and Retirement

新路径落地时必须同一迁移删除旧路径：

- 旧调用方。
- 旧入口。
- 旧测试。
- 旧配置和状态语义。
- 旧文档宣传。

公开 CLI/MCP 名称可以保留，但必须薄转发到唯一 canonical path。内部不得保留 local-source/native/bridge 多轨实现。

## AI and Deterministic Responsibilities

- AI 可用于搜索规划、语义质量、证据充分性和综合判断。
- 确定性代码负责协议适配、生命周期、缓存、参数验证、错误分类和状态转换。
- 某模块是否需要确定性降级由该模块需求决定，不写成全局必备 fallback。
- 历史实现 fallback 禁止；能力降级必须显式、可观测且不伪装成功。
