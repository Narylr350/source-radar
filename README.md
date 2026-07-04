# source-radar

AI 友好的本地 CLI / MCP 采集引擎，用于中文互联网综合信息分析、资料搜索、经验汇总和事实核验。

当前项目基线见 `.ai/PROJECT.md`。项目正在从 **bridge-first 多服务包装器** 迁移到 **原生采集内核 + 统一后端安装/状态管理**。

## 当前目标

- 保持 `ask` / `verify` / `research` / MCP 外部入口稳定。
- 将采集能力收敛到 `AcquisitionKernel`。
- 用 `BackendRegistry` 记录后端安装来源、类型、版本、路径引用、状态和诊断。
- 用 `BackendLifecycleManager` 统一管理预热、保温、ready 检查、idle stop 和失败熔断。
- 用 `EngineInstaller` 统一下载、local-source checkout、runtime 目录、修复和状态登记。
- 将后端源码、下载包、wheel cache、浏览器运行时、pid、日志和临时文件收敛到 `.source-radar/`。

目标 runtime 形态：

```text
.source-radar/
  engines/
  downloads/
  runtime/
  pids/
  logs/
  config.json
```

## 已有入口

```powershell
# 综合信息分析
uv run python -m source_radar ask "问题"

# 严格核验
uv run python -m source_radar verify "断言"

# 深度研究
uv run python -m source_radar research "复杂问题"

# MCP server
uv run python -m source_radar mcp

# 后端状态
uv run python -m source_radar engine status
```

## MCP 工具

当前 MCP server 暴露：

- `web_search`
- `fetch_url`
- `fetch_search_results`
- `search_github`
- `search_chinese_platforms`
- `fetch_github_file`
- `source_status`

MCP 是薄外壳。后续底层应走统一采集内核和后端生命周期管理，不应在 MCP 内部私自实现随用随起、常驻或 idle stop。

## 安装方向

当前安装命令仍保留兼容：

```powershell
uv run python -m source_radar engine install
uv run python -m source_radar engine status
```

新方向是让 `engine install/status/repair` 统一管理：

- Python 依赖；
- local-source backend checkout；
- 下载缓存；
- 浏览器/runtime；
- 后端 lifecycle policy；
- readiness probe；
- 诊断和修复建议。

不要新增散落 runtime 目录。新的后端运行态必须进入 `.source-radar/` 约定目录。

## 开发

```powershell
.venv\Scripts\python.exe -m unittest tests.test_mcp_server -v
.venv\Scripts\python.exe -m unittest tests.test_acquisition_m5 tests.test_agent_flow tests.test_stability_regression -v
```

新增 backend registry / lifecycle / installer 工作应先加 focused `unittest`。

## 文档

当前保留的事实源：

- `.ai/PROJECT.md`
- `.ai/TECH.md`
- `.ai/CONSTRAINTS.md`
- `.ai/VALIDATION.md`
- `README.md`

旧 `docs/tasks` 索引、compose plans、历史 roadmap 和过期 skill 包不再作为当前工作流的一部分。
