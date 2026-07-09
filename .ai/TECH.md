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
- 决策层架构：AI-first -> 脚本 fallback。所有判断先调 AI，AI 不可用时降级到现有脚本规则。
- AI 判断点：搜索质量评估、fallback 决策、工具选择、采集充分性、错误诊断。
- 脚本 fallback 保留但不作为第一选择。
- AI 判断结果需结构化（reasoning + decision + confidence），便于 trace 和调试。

## Entry Modes and Canonical Paths

当前公开入口并存是兼容需求，不代表内部可以多套状态机并存：

| 入口 | 当前状态 | canonical 内部路径 |
|---|---|---|
| `ask` / `verify` / `research` CLI | 保留 | `VerificationAgent` → `dispatch_search` / `fetch_with_fallback` / provider registry |
| `mcp` CLI | 保留 | `app/source_radar/mcp/server.py` → `AcquisitionKernel` → `dispatch_search` / `fetch_with_fallback` |
| `engine install/status/start/stop/repair/cleanup` | 保留 | `EngineInstaller` + `BackendRegistry` + `BackendLifecycleManager` |
| MCP `web_search` / `fetch_url` | 保留 | `SearXNGNativeProvider` (直接调 upstream HTTP API) / `fetch_with_fallback` |
| MCP `search_chinese_platforms` | 保留 | native `community.bilibili` first；其余平台暂经 MediaCrawler service adapter |
| MCP `source_status` | 保留 | `engine.list_engines` + `BridgeHealth` + lifecycle diagnostics |
| `source-radar bridge ...` | 待删除 - MediaCrawler only | `engine start mediacrawler` 通过 `subprocess.Popen` 调用 bridge CLI。SearXNG 已改用 `SearXNGNativeProvider`，不经 bridge。退役路径：`engine start` 改为直接调用 `serve_bridge()`，然后删除 bridge CLI 子命令。不得绕过 registry/lifecycle 变成第二套启动状态机 |

已发现的旧模式残留：

- `VerificationAgent._ask_legacy` 已退役：`ask` 方法统一处理 adaptive 和 explicit source 路径，共享 `_finish_ask` 后采集管线。
- SearXNG 已改用 `SearXNGNativeProvider`，直接调 SearXNG upstream HTTP API，不经 bridge 进程。`ExternalBridgeProvider("searxng")` 已从 `dispatch_search` 和 `default_providers` 移除。
- `ExternalBridgeProvider` / `BridgeHealth` / `source-radar bridge` 当前仍是 MediaCrawler 的 adapter 边界；SearXNG 不再走 bridge。删除 bridge 前必须先有 MediaCrawler 的等价 native/local-source adapter。
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
