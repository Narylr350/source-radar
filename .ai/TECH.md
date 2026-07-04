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
- `BackendLifecycleManager` 负责启动、预热、ready 检查、warm lease、idle stop、失败熔断和 fallback。
- `EngineInstaller` 负责下载缓存、local-source checkout、engine 目录、metadata、修复和 registry 写回。
- 旧 bridge 标记为 `legacy-bridge`，只作为迁移期 fallback。
- 当前优先级是 installer/downloads/runtime/lifecycle 稳定性；中文平台 native 扩张需等这些基础稳定后再继续。

## Backend Types and Policies

Backend types:

- `native`
- `local-source`
- `service`
- `legacy-bridge`
- `external`

Lifecycle policies:

- `disabled`
- `on-demand`
- `warm`
- `always-on`
- `external`

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

第三方源码第一阶段通过本地 clone/cache 进入 `.source-radar/engines` 或兼容 legacy fallback，不进入主仓库。
