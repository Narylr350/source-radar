# source-radar

**给 AI 用的可审计信息采集引擎。** 通过 MCP Server 或 CLI 为外部 AI 提供搜索、抓取、社区采集能力，把中文互联网搜索结果变成可审计的证据卡，再交给 AI 做综合、核验或研究。

## 核心能力

| 能力 | 普通 AI 搜索 | source-radar |
|------|-------------|--------------|
| 搜索源 | 单一搜索引擎 | SearXNG 元搜索（多引擎聚合）+ Bing/百度 fallback |
| 搜索规划 | 无 | AI Search Planner：自动改词、选平台、质量门重试 |
| 质量评估 | 无 | 10 个检测器：语义不匹配、实体拆分、事件确认等 |
| MCP 工具 | 无 | 5 个：web_search / fetch_url / search_github / search_chinese_platforms / fetch_github_file |
| 证据结构 | 不稳定 | 统一证据卡：id/来源类型/链接/摘要/原文/保真度 |
| 中文社区 | 弱 | 可接 MediaCrawler（小红书/微博/B站/贴吧/抖音/知乎） |
| 超时处理 | 固定硬超时 | 自适应：按平台数动态调整，假死检测基于日志增量 |

## 安装

本项目有自己的安装协议。不要按通用 Python/uv 项目经验自行推断安装步骤。

**核心规则：AI 安装和人工安装不是同一条路径。** AI 路径必须非交互、可恢复、以 `setup-plan` 为准；人工路径可以使用交互式向导。

### 如果你是 AI Agent（Claude Code / Codex 等）在帮用户安装

**不要运行 `config setup`、`cookie` 等交互命令。** 根据 `setup-plan` 输出向用户索要缺失输入，再用非交互命令写入。

**第 1 步：克隆并安装**

```bash
git clone https://github.com/Narylr350/source-radar.git
cd source-radar

# 非交互安装（不提示输入）
uv run python -m source_radar install --agent
```

**第 2 步：安装并启动 SearXNG（必选）**

```bash
uv run python -m source_radar engine install --searxng
uv run python -m source_radar engine start searxng
```

**第 3 步：查看还缺什么**

```bash
uv run python -m source_radar setup-plan --format json
```

根据返回的 `required_inputs` 向用户索要必需配置（API key、endpoint、model）。

**第 4 步：写入 AI 配置（非交互）**

```bash
uv run python -m source_radar config set-ai --api-key "<key>" --endpoint "<endpoint>" --model "<model>"
```

不要把用户 API key 写入 README、issue、commit 或远端；只写入本地配置。

**第 5 步：验证**

```bash
uv run python -m source_radar probe --source searxng --query "test"
uv run python -m source_radar config test-ai
```

**可选：中文社区采集**

```bash
uv run python -m source_radar engine install --community
uv run python -m source_radar engine start mediacrawler
# Cookie 用非交互命令写入：uv run python -m source_radar cookie set --platform <key> --value "<cookie>"
```

**禁止事项：**
- 不要直接跑 `uv sync` 或 `pip install`——必须通过 `install --agent` 或 `engine install`
- 不要跳过 SearXNG——它是必选 websearch 基础设施
- 不要运行 `config setup` 或无参数 `cookie` 捕获向导——AI 只能使用 `config set-ai` / `cookie set` 这类非交互命令
- 不要根据报错自行推断修复命令——优先使用 `setup-plan --format json` 的输出

### 如果你是真人手动安装

```bash
git clone https://github.com/Narylr350/source-radar.git
cd source-radar

# 1. 安装核心依赖
uv run python -m source_radar engine install

# 2. 安装并启动 SearXNG
uv run python -m source_radar engine install --searxng
uv run python -m source_radar engine start searxng

# 3. 配置 AI（交互式，会引导你选择协议、输入 key、选择模型）
uv run python -m source_radar config setup

# 4. 验证
uv run python -m source_radar probe --source searxng --query "test"
uv run python -m source_radar config test-ai

# 5. 使用
uv run python -m source_radar ask "RTX 5090 电源兼容问题"
```

## 架构

```
┌─────────────────────────────────────────────────────────┐
│  CLI / Claude Code / MCP Server / AI Agent              │
└───────────────┬─────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────┐
│  Agent (内置)                                            │
│  AI Planner → 采集 → 质量评估 → 重试 → Evaluator → 综合  │
│  自适应超时：60s 基础 + 30s/平台，硬上限 300s             │
│  假死检测：日志增量，连续 5 次无新日志 → stop + 读 partial │
└───────────────┬─────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────┐
│  采集引擎                                                │
│  SearXNG (必选) / Bing/百度 fallback / trafilatura /     │
│  crawl4ai / mediacrawler (可选)                          │
└─────────────────────────────────────────────────────────┘
```

## 真实案例

### 案例 1：技术问题排查

```bash
uv run python -m source_radar ask "vllm 启动报 CUDA out of memory 怎么排查" --source auto
```

AI Search Planner 自动生成 3 个搜索尝试：
- `vllm gpu_memory_utilization max_model_len`（site:docs.vllm.ai，hint:official+github）
- `vllm CUDA out of memory github issues`（site:github.com）
- `vllm 内存不足 启动 解决`（hint:community）

采集结果：找到官方文档配置项 + GitHub issue 讨论 + 中文社区经验。Evaluator 判断证据足够，10 条相关。AI 综合给出排查步骤：调整 `gpu_memory_utilization`、减小 `max_model_len`、检查显存占用。

### 案例 2：事件确认（强源要求）

```bash
uv run python -m source_radar ask "张雪峰死了吗" --source auto
```

Planner 识别为 `event_confirmation` 查询，自动生成强源查询：
- `张雪峰 讣告`
- `苏州峰学蔚来 声明 张雪峰`
- `张雪峰 官方账号`

质量检测器 `event-confirmation-needs-strong-source` 触发 → strong-source loop 自动重试。如果找到公司讣告或主流媒体确认（DoNews/财联社等），可信度为高；如果只有社区帖子，输出"未找到官方/权威确认"。

### 案例 3：评测类查询

```bash
uv run python -m source_radar ask "最新的AI模型评测哪个靠谱" --source auto
```

Planner 识别为 `benchmark` 查询，生成无 site 限制的尝试：
- `Artificial Analysis LLM leaderboard`
- `Chatbot Arena leaderboard 2026`
- `AI模型评测 排行榜`

找到 LMSYS Chatbot Arena、Artificial Analysis、SuperCLUE 等评测平台。Evaluator 判断证据足够，AI 综合对比各评测方法的优劣。

## CLI 命令

```bash
# 综合信息分析
uv run python -m source_radar ask "问题"

# 严格核验
uv run python -m source_radar verify "断言"

# 深度研究
uv run python -m source_radar research "复杂问题" --max-rounds 2

# 安静模式（JSON 输出）
uv run python -m source_radar ask "问题" --format json --quiet

# Session context（追问自动关联）
uv run python -m source_radar ask "问题" --session mysession

# 启用中文社区采集
uv run python -m source_radar ask "问题" --local-services
```

### ask / verify / research 的区别

| 命令 | 适用场景 | 采集方式 | Session |
|------|---------|---------|---------|
| `ask` | 快速查询、教程查找 | 自适应采集，max_tools=3 | 支持 |
| `verify` | 真伪核验、事实核查 | 自适应 + 严格模式（拒绝纯搜索结果） | 支持 |
| `research` | 复杂多面问题 | Planner → 多轮 collect → dedupe → synthesize | 不支持 |

## 自适应采集与超时

### 采集流程

```
Round 1: search（必跑）
  → evaluator 判断证据是否足够
    → 够 → 停止
    → 不够 → Round 2: 选择下一个工具（trafilatura / crawl4ai / mediacrawler）
      → 最多 3 个工具，12 张证据卡上限
```

### 超时策略

不再使用固定超时。超时根据实际工作量动态计算：

| 因素 | 超时 |
|------|------|
| 基础（搜索 + AI 规划） | 60 秒 |
| 每个 MediaCrawler 平台 | +30 秒 |
| 硬上限 | 300 秒 |

示例：2 个平台 → 60 + 2×30 = 120 秒；4 个平台 → 60 + 4×30 = 180 秒。

### 假死检测

MediaCrawler 爬虫可能卡住（health 通过但无进展）。自适应检测：

1. 每 2 秒 poll 状态 + 日志
2. 连续 5 次（10 秒）无新日志 → 判定假死
3. 调用 MediaCrawler stop API，尝试读取 partial 结果
4. 释放锁，下次调用正常

### MediaCrawler 启动重试

`local_services_for_query` 自动尝试启动 MediaCrawler：

1. Health 检查 → 不健康则尝试启动
2. 等待 15 秒
3. 失败 → 等 2 秒 → 重试一次
4. 全部失败 → 跳过，不阻塞 agent

## MCP Server

source-radar 可以作为 MCP server，让 Claude Code、Cursor 等支持 MCP 的 AI 工具直接调用。

### 配置

```json
{
  "mcpServers": {
    "source-radar": {
      "command": "uv",
      "args": ["run", "--extra", "mcp", "source-radar", "mcp"],
      "cwd": "/path/to/source-radar"
    }
  }
}
```

### 暴露的工具

| 工具 | 作用 | 参数 |
|------|------|------|
| `web_search` | 搜索（SearXNG → Bing → 百度） | `query`、`limit`、`site`、`page`、`nocache` |
| `fetch_url` | 抓取网页正文 | `url`、`max_chars`、`page` |
| `search_github` | 搜索 GitHub issues/PRs | `query`、`limit`、`page`、`nocache` |
| `search_chinese_platforms` | 搜索中文平台 | `query`、`platforms`、`limit`、`nocache` |
| `fetch_github_file` | 获取 GitHub 文件内容 | `repo`+`path` 或 `url`、`ref`、`max_chars`、`page` |

### AI Agent 全局指令

**Claude Code** — 添加到 `~/.claude/CLAUDE.md`：
```markdown
## Web Search & Fetch
- Use source-radar MCP tools instead of built-in WebSearch/WebFetch when available
- `source-radar_web_search` for web searches (supports `site`, `page`, `nocache`)
- `source-radar_fetch_url` for page content extraction (supports `page` for long docs)
- `source-radar_search_github` for GitHub issues/PRs
- `source-radar_search_chinese_platforms` for Chinese community platforms
- `source-radar_fetch_github_file` for raw GitHub file content
```

## 质量检测器

| 检测器 | 触发条件 |
|--------|---------|
| `no-candidates` | 无搜索结果 |
| `semantic-mismatch` | 结果与查询语义不相关 |
| `method-answers-missing` | 方法型查询但结果多为评测/参数页 |
| `navigation-heavy` | 正文是导航菜单 |
| `language-mismatch` | 查询语言与结果语言不匹配 |
| `domain-concentration` | 结果集中在单一域名 |
| `snippet-only` | 仅有搜索摘要，未抽取正文 |
| `key-platform-missing` | 新闻类查询缺少主流媒体结果 |
| `entity-tokenization-failure` | 搜索引擎拆分中文实体名（如"张雪峰"→"张"） |
| `event-confirmation-needs-strong-source` | 事件确认类查询缺少讣告/官方声明等强源 |

## 引擎管理

```bash
# 查看引擎状态
uv run python -m source_radar engine list
uv run python -m source_radar engine status

# 安装
uv run python -m source_radar engine install              # 核心
uv run python -m source_radar engine install --searxng    # SearXNG（必选）
uv run python -m source_radar engine install --community  # MediaCrawler（可选）

# 启停
uv run python -m source_radar engine start searxng
uv run python -m source_radar engine stop searxng
uv run python -m source_radar engine start mediacrawler

# 诊断
uv run python -m source_radar probe --source searxng --query "test"
uv run python -m source_radar engine status
uv run python -m source_radar health --format markdown
```

## 全部 CLI 命令

| 命令 | 作用 | 常用参数 |
|------|------|---------|
| `ask <问题>` | 综合信息分析 | `--format json`、`--quiet`、`--session <id>`、`--no-session`、`--local-services`、`--source auto/search` |
| `verify <断言>` | 严格核验 | `--format json`、`--quiet`、`--session <id>`、`--local-services` |
| `research <问题>` | 深度研究 | `--max-rounds 2`、`--local-services` |
| `install` | 交互式一键安装 | `--agent`（非交互） |
| `engine list` | 列出所有引擎状态 | |
| `engine status` | 引擎就绪状态 + 修复建议 | |
| `engine install` | 安装引擎依赖 | `--searxng`、`--community`、`--browser`、`--all` |
| `engine start <name>` | 启动服务引擎 | |
| `engine stop <name>` | 停止服务引擎 | |
| `config setup` | 交互式 AI 配置 | |
| `config set-ai` | 非交互写入 AI 配置 | `--api-key`、`--endpoint`、`--model`、`--provider` |
| `config show` | 查看当前配置（密钥脱敏） | |
| `config test-ai` | 测试 AI 连通性 | `--format json` |
| `config set-provider` | 写入 provider bridge 配置 | `--name`、`--endpoint` |
| `config set-logging` | 配置日志 | `--enabled`、`--level`、`--max_bytes`、`--backup_count` |
| `cookie` | 浏览器捕获 Cookie | `--platform <name>`、`--force` |
| `cookie set` | 非交互写入 Cookie | `--platform <key>`、`--value "<cookie>"` |
| `cookie show` | 查看 Cookie 状态（脱敏） | |
| `cache status` | 查看缓存状态 | |
| `cache clear` | 清除所有缓存 | |
| `cache prune` | 清理过期缓存 | |
| `session status` | 查看 session 状态 | |
| `session clear` | 清除 session | `--session <id>` |
| `session new` | 生成新 session ID | |
| `probe --source <name>` | 检查单个采集源 | `--query "test"` |
| `health` | 整体健康状态 | `--format markdown`、`--format json` |
| `setup-plan` | 输出初始化需求（AI 用） | `--format json` |
| `bridge <provider>` | 启动 bridge 服务 | `--port`、`--upstream-url` |
| `mcp` | 启动 MCP server（stdio） | |
| `integrations audit` | 查看外部集成许可 | |
| `integrations status` | 查看集成状态 | |
| `uninstall` | 卸载 | `--all`、`--user-config`、`--project`、`--yes` |

## Skill 安装（Claude Code）

Skill 让 Claude Code 对话中直接说"帮我查一下 XX"自动调用 source-radar。

```bash
# 方式 1：目录链接（推荐，git pull 后自动同步）
# Windows
New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\skills\source-radar" -Target "$(pwd)\skills\source-radar"

# macOS/Linux
ln -s "$(pwd)/skills/source-radar" ~/.claude/skills/source-radar

# 方式 2：复制
Copy-Item -Recurse skills/source-radar/ "$env:USERPROFILE\.claude\skills\source-radar/"
```

安装后在 Claude Code 对话中直接说：
- "帮我查一下 RTX 5090 电源接口问题在中文社区的讨论"
- "验证这个消息：XX 产品宣布涨价 30%"
- "搜索小红书和 B 站上关于 Python 教程的评价"

## 环境要求

| 依赖 | 用途 |
|------|------|
| Python >= 3.11 | 运行时 |
| uv | 包管理 |
| Git | 克隆仓库 |

## 许可证与合规

**核心仓库：Apache-2.0。** 第三方引擎不进入核心源码；其中 SearXNG 是正常 websearch 运行时的必选外部服务，MediaCrawler 是可选增强。

| 组件 | 许可证 | 集成方式 | 说明 |
|------|--------|----------|------|
| source-radar 核心 | Apache-2.0 | — | 自由使用、修改、分发 |
| SearXNG | AGPL-3.0 | 外部 bridge | 必选 websearch 基础设施，不 vendor 源码 |
| Crawl4AI | Apache-2.0 | pip 可选包 | 与核心兼容 |
| Trafilatura | **GPL-3.0** | pip 可选包 | 如果分发包含 Trafilatura 的组合包，需要评估 GPL-3.0 义务；不需要时可跳过 |
| MediaCrawler | 非商业学习/研究 | 外部 bridge | 不 vendor 源码，用户自行安装 |

**注意事项：**
- **Trafilatura 是 GPL-3.0**：不需要时跳过，核心采集可走 Crawl4AI（Apache-2.0）。如果分发包含 Trafilatura 的组合包，需要评估 GPL-3.0 义务。
- **SearXNG 是 AGPL-3.0**：通过外部 bridge 调用，不 vendor 源码
- **MediaCrawler 不得进入核心代码**：仅通过 HTTP API 调用
