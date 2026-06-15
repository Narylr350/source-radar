# v0.2.0-alpha.1

**首个可用的 SearXNG-backed 本地 websearch alpha 版**

## 新增

- **SearXNG 生命周期管理**
  - `engine install --searxng` — git clone + venv + pip install（Windows 自动 sparse-checkout 避免路径问题）
  - `engine start searxng` — 启动 upstream + bridge + 自动写入 config
  - `engine stop searxng` — 停止 upstream + bridge
  - `engine status searxng` — 检查 upstream JSON + bridge health
  - 自动生成 `settings.yml`，确保 `formats: [html, json]` 启用

- **MCP / CLI / Agent 搜索统一**
  - `dispatch_search()` 统一搜索分发：SearXNG → Bing → Baidu fallback
  - MCP `web_search` 和 Agent `run_tool("search")` 共享同一搜索路径
  - SearXNG 通过 `ExternalBridgeProvider` auto-discovery（env/config/port 3004 probe）

- **Evidence bucketing**
  - 证据按来源强度分桶：official → mainstream → platform-account → community → noise
  - `has_strong_source()` 检查是否有官方/主流媒体来源
  - `sort_evidence_by_strength()` 综合时强源优先

- **event_confirmation 查询策略**
  - Planner 自动生成 `讣告`/`公司声明`/`官方账号` 查询
  - 质量检测器：事件确认类查询缺少强源时标记 `event-confirmation-needs-strong-source`
  - Strong-source loop：无强源时自动重试
  - Evaluator/综合层约束：无官方/主流媒体 → 必须报告"未确认"

- **entity-tokenization-failure 检测**
  - 检测搜索引擎拆分中文实体名（如"张雪峰"→"张"）
  - 自动 fallback 到 Baidu

- **search_github 分页缓存修复**
  - `put_cached_result` 使用正确的 `cache_key`（含 page 后缀）

- **fetch_github_file schema 补 page**
  - MCP 工具 schema 暴露 `page` 参数

## 已知问题

- **MediaCrawler 可能导致超时** — 社区采集步骤可能很慢，部分黑盒测试因此超时
- **全量 `unittest discover` 耗时长** — 240s 超时未拿到完整通过结论；相关测试通过
- **SearXNG Windows 依赖** — 需要 mock `pwd` 模块；启动通过 launcher 脚本
- **Bing 搜索质量** — 程序化请求可能返回垃圾结果；SearXNG 作为主搜索源缓解此问题

## 黑盒测试结果（4/6 通过）

| 题目 | 状态 | 备注 |
|------|------|------|
| AI模型评测 | ✅ | 找到 LMSYS、Artificial Analysis |
| vllm CUDA OOM | ✅ | 10 条相关，官方文档+GitHub issue |
| 张雪峰死了吗 | ⏱️ 超时 | MediaCrawler 慢 |
| amd9800x3d | ⏱️ 超时 | 同上 |
| OpenWrt 防变砖 | ✅ | 有社区帖子+教程 |
| 小米15拍照翻车 | ✅ | 有社区帖子 |

## 测试

- 206 个单元测试通过
- `git diff --check` 通过
- SearXNG real install/start/probe smoke 通过
