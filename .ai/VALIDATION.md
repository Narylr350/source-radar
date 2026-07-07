# VALIDATION

## Validation

按风险分级验证。低风险文档或配置改动用 targeted 检查；backend/lifecycle/installer/API 行为改动必须跑对应 focused tests。

## Baseline Commands

MCP 与核心回归：

```powershell
.venv\Scripts\python.exe -m unittest tests.test_mcp_server -v
```

核心采集与 agent 回归：

```powershell
.venv\Scripts\python.exe -m unittest tests.test_acquisition_m5 tests.test_agent_flow tests.test_stability_regression -v
```

backend registry / lifecycle / B站 native 相关：

```powershell
.venv\Scripts\python.exe -m unittest tests.test_backend_registry tests.test_lifecycle_ensure_ready tests.test_mcp_autostart tests.test_bilibili_backend tests.test_acquisition_kernel -v
```

CLI/MCP 基础 smoke：

```powershell
.venv\Scripts\python.exe -m source_radar mcp --help
.venv\Scripts\python.exe -m source_radar engine status
```

## New Work Requirements

- 新增 backend / installer / registry / lifecycle 行为：先加 focused `unittest`，看见 RED 后再实现。
- lifecycle 改动至少覆盖：ready、start failed、non-zero process exit、cooling_down、idle timeout、fallback。
- installer 改动至少覆盖：`.source-radar/downloads`、`.source-radar/engines`、metadata、断点/复用或可诊断下载状态、不读取 `external/`、不提交凭据/源码。
- runtime path 改动至少覆盖：目标路径在 `.source-radar/` 下，`external/` 存在也不会被识别为 installed。
- MCP 工具行为改动至少覆盖对应 handler 单测，并确认外部 tool schema 不回归。
- 退役协议相关改动必须验证旧测试确实失效或改写，不能让测试继续保护旧模式；涉及入口删除的，必须验证无调用方残留。

## Manual / Black-box Checks

按任务需要选择：

```powershell
uv run python -m source_radar ask "问题"
uv run python -m source_radar verify "断言"
uv run python -m source_radar research "复杂问题"
uv run python -m source_radar engine install
uv run python -m source_radar engine status
uv run python -m source_radar mcp
```

MCP 黑盒重点：

- `source_status`
- `search_chinese_platforms`
- `web_search`
- `fetch_url`
- `fetch_search_results`

## Finish Checks

提交前至少执行：

```powershell
git status --short --branch
git diff --stat
git diff --check
```

涉及代码行为时，记录实际跑过的测试命令和结果；不能把未执行的验证写成通过。
