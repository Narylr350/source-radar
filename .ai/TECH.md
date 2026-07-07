# TECH

## Tech Direction

- Runtime：Python 3.11+。
- 包管理：`uv` + setuptools。
- 测试：标准库 `unittest`，新增 backend/installer/lifecycle 工作先加 focused tests。
- 项目形态：single app，源码位于 `app/source_radar/`。
- 外部入口保持稳定，内部优先从 bridge-first 迁移到：
  - `AcquisitionKernel`
  - `BackendRegistry`
  - `BackendLifecycleManager`
  - `EngineInstaller`
  - 统一 `.source-radar/` downloads/engines/runtime/cache
  - native/local-source backend（后续扩张方向，不是当前最高优先级）

## Architecture Direction

- CLI/MCP 调用统一采集内核或等价深模块；调用方不直接感知 bridge、clone 路径、cookie 文件、浏览器目录或下载缓存位置。
- `BackendRegistry` 记录 backend 类型、安装来源、版本/commit、本地路径引用、状态和诊断。
- `BackendLifecycleManager` 负责启动、预热、ready 检查、warm lease、idle stop 和失败熔断。
- `EngineInstaller` 负责下载缓存、local-source checkout、engine 目录、metadata、修复和 registry 写回。
- 历史 `external/` checkout 不参与运行路径。
- 当前优先级是 installer/downloads/runtime/lifecycle 稳定性 + 状态演进退役协议；中文平台 native 扩张需等这些基础稳定后再继续。
- 状态演进退役协议是技术约束的一部分：新模式落地必须同时输出旧模式退役清单（死亡条件、入口删除、测试失效、文档降级），不能只新增新层然后把旧层留作隐式 fallback。

## Entry Modes and Canonical Paths

当前公开入口并存是兼容需求，不代表内部可以多套状态机并存：

| 入口 | 当前状态 | canonical 内部路径 |
|---|---|---|
| `ask` / `verify` / `research` CLI | 保留 | `VerificationAgent` → `dispatch_search` / `fetch_with_fallback` / provider registry |
| `mcp` CLI | 保留 | `app/source_radar/mcp/server.py` → `AcquisitionKernel` → `dispatch_search` / `fetch_with_fallback` |
| `engine install/status/start/stop/repair/cleanup` | 保留 | `EngineInstaller` + `BackendRegistry` + `BackendLifecycleManager` |
| MCP `web_search` / `fetch_url` | 保留 | `AcquisitionKernel.search/fetch` |
| MCP `search_chinese_platforms` | 保留 | native `community.bilibili` first；其余平台暂经 MediaCrawler service adapter |
| MCP `source_status` | 保留 | `engine.list_engines` + `BridgeHealth` + lifecycle diagnostics |
| `source-radar bridge ...` | 过渡兼容入口 | 只作为 service adapter host，由 `engine start` / lifecycle 管理；不得绕过 registry/lifecycle 变成第二套启动状态机 |

已发现的旧模式残留：

- `VerificationAgent._ask_legacy` 已退役：`ask` 方法统一处理 adaptive 和 explicit source 路径，共享 `_finish_ask` 后采集管线。
- `ExternalBridgeProvider` / `BridgeHealth` / `source-radar bridge` 当前仍是 SearXNG、MediaCrawler 这类本地 service 的 adapter 边界；它们不是 `external/` checkout fallback，但命名仍带历史痕迹。删除 bridge 前必须先有等价 native/local-source service adapter。
- `fallback` 一词在本项目有两类含义：允许的采集质量降级（如 SearXNG 低质量后用 Bing/Baidu、Trafilatura 到 Crawl4AI）和不允许的历史路径兜底。后者不得恢复。

## Backend Types and Policies

Backend types:

- `native`
- `local-source`
- `service`

Lifecycle policies:

- `disabled`
- `on-demand`
- `warm`
- `always-on`

默认策略：

- `search.searxng`：`warm`
- `community.*`：`on-demand` 或短 TTL `warm`
- `browser.crawl4ai`：`on-demand`
- GitHub / Trafilatura 等无常驻进程后端：`native`

`warm` / `always-on` 用于缓解随用随起的启动慢和启动失败；`on-demand` 只用于启动代价低或使用频率低的 backend。

## Runtime Layout

所有 backend 源码、下载包、wheel cache、浏览器运行时、pid、日志和临时运行数据收敛到 `.source-radar/`：

```text
.source-radar/
  config.json
  local.env
  engines/
    mediacrawler/
    searxng/
    crawl4ai/
  downloads/
    MediaCrawler-<commit>.zip
    searxng-<version>.zip
    wheels/
  runtime/
  pids/
  logs/
```

第三方源码通过本地 clone/cache 进入 `.source-radar/engines`，不进入主仓库；`external/` 不再参与安装、启动或状态判断。
