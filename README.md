# source-radar

**给 AI Agent 用的中文互联网证据采集层。**

不是聊天机器人，不是简单搜索封装。它把中文互联网搜索结果变成可审计的证据卡，再交给 AI 做综合、核验或研究。和普通 AI 搜索的区别在于：链路分层、采集过程可追溯、缓存可查、追问上下文可控。

## 和普通 AI 搜索有什么区别

| 能力 | 普通 AI 搜索 | source-radar |
|------|-------------|--------------|
| 搜索网页 | 有 | 有 |
| 证据卡结构化 | 不稳定，每次格式不同 | 统一证据卡，有 id/来源类型/链接/摘要 |
| 工具调用追溯 | 不透明 | 完整记录：用了哪些工具、跳过哪些、为什么 |
| 缓存命中可见 | 通常不可见 | 命中次数、缓存时长都在 JSON 里 |
| 追问上下文 | 黑箱 | 可记录、可关闭、是否使用上下文可查 |
| 严格核验模式 | 看模型发挥 | 独立链路：纯搜索结果不够，强制追加正文抽取 |
| 中文社区增强 | 弱 | 可接 MediaCrawler（小红书/微博/B站/贴吧/抖音/知乎） |
| 适合 Agent 集成 | 一般 | 专门设计：JSON 输出干净、进度与结果分离、追溯结构化；支持 MCP Server |

**一句话总结**：普通 AI 搜索是"快速查一下"，source-radar 是"可审计的信息采集流水线"。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│  CLI / Claude Code Skill / MCP Server / AI Agent        │
│  ask / verify / research / web_search / fetch_url / search_github / search_chinese_platforms  │
└───────────────┬─────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│  Agent (内置)                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ AI Planner   │  │  Evaluator   │  │  Synthesizer  │  │
│  │ 搜索规划+重试 │  │  判断证据     │  │  综合输出      │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────────┘  │
│         │                 │                              │
│         ▼                 ▼                              │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Adaptive Collection                             │   │
│  │  1. AI Planner 生成 2-4 个搜索尝试                │   │
│  │  2. 执行搜索，合并候选                            │   │
│  │  3. 质量评估 (8 个检测器)                         │   │
│  │  4. 质量低 → AI 重试改词/换平台                   │   │
│  │  5. planner 指定平台 → 强制 MediaCrawler          │   │
│  │  6. Evaluator 决定是否需要更多工具                │   │
│  └──────────────────────────────────────────────────┘   │
│         │                                                │
│         ▼                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Cache       │  │  Session     │  │  Agent Trace  │  │
│  │  采集结果缓存 │  │  追问上下文   │  │  完整采集追踪  │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│  采集引擎（全部可选）                                      │
│  ┌────────────┐ ┌────────────┐ ┌──────────────────────┐ │
│  │ search     │ │trafilatura │ │ crawl4ai             │ │
│  │ 搜索发现    │ │正文抽取     │ │ 动态渲染             │ │
│  └────────────┘ └────────────┘ └──────────────────────┘ │
│  ┌────────────────────────────────────────────────────┐ │
│  │ mediacrawler (外部 bridge)                         │ │
│  │ 小红书 / 微博 / B站 / 贴吧 / 抖音 / 知乎           │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## 快速开始（无需中文社区爬虫）

无需中文社区爬虫也可以先跑通基础链路：

```bash
git clone https://github.com/Narylr350/source-radar.git
cd source-radar

# 1. 配置 AI（支持 OpenAI / Anthropic / Gemini / 本地模型）
uv run python -m source_radar config setup

# 2. 直接用
uv run python -m source_radar ask "RTX 5090 电源兼容问题"
uv run python -m source_radar verify "某产品宣布涨价 30%"
```

不需要 MediaCrawler、不需要 Cookie、不需要爬虫配置。`search` + `trafilatura`（自动安装）+ AI 就能跑完整条链路。MediaCrawler 是中文社区增强能力，不是基础使用前提；未配置时仍可使用 search + web extraction。

如果需要增强中文社区采集（小红书/微博/B站等），再配置 MediaCrawler：

```bash
uv run python -m source_radar engine install --community
uv run python -m source_radar cookie
```

## 真实 demo：9800x3D 超频查询

```bash
uv run python -m source_radar ask "9800x3d 微星b850 怎么超频" --format json --quiet
```

输出（简化）：

```json
{
  "query": "9800x3d 微星b850 怎么超频",
  "status": "analysis-ready",
  "evidence": [
    {"id": "ev-001", "source_type": "search-result", "title": "9800X3D超频教程...", "adapter": "search"},
    {"id": "ev-002", "source_type": "web-page", "title": "PBO2设置指南...", "adapter": "trafilatura"}
  ],
  "analysis": {
    "summary": "9800X3D 超频主要通过 PBO2 + Curve Optimizer 实现...",
    "key_points": ["BIOS 中开启 PBO2 Advanced", "CO 值建议 -20 到 -30", "..."],
    "source_notes": ["search: 5 条来源", "trafilatura: 2 条来源"],
    "disagreements": [],
    "noise_notes": ["搜索结果只作为线索，优先看正文抽取和社区原帖。"]
  },
  "agent": {
    "mode": "analysis",
    "planned_tools": ["search", "trafilatura"],
    "tool_calls": [
      {"tool": "search", "items_found": "5", "cache_hit": "False", "elapsed_ms": "1200"},
      {"tool": "trafilatura", "items_found": "2", "cache_hit": "True", "cache_age_seconds": "3600"}
    ],
    "actually_used_tools": ["search", "trafilatura"],
    "skipped_tools": [{"tool": "mediacrawler", "reason": "不需要中文社区讨论", "decided_by": "collection_evaluator"}],
    "cache_hit_count": 1,
    "fresh_tool_count": 1
  }
}
```

追问（session 自动关联）：

```bash
uv run python -m source_radar ask "那内存怎么调" --session oc --quiet
```

agent 识别为追问，`context_used: true`，综合时自动带上上文语境。

## AI agent 如何驱动整个流程

source-radar 不是脚本硬编码的爬虫管线。每次运行，内置 agent 都在做真实决策：

```
你的问题
  ↓
agent 规划：该用哪些采集工具？
  ↓
第 1 轮：搜索（必跑）
  ↓
evaluator（AI）：证据够了吗？
  → 够 → 停止采集
  → 不够 → 选下一个工具（trafilatura / crawl4ai / mediacrawler）
  ↓
（最多 3 个工具，12 张证据卡上限）
  ↓
AI 综合：基于证据卡输出回答 / 核验判断
```

agent 内部包含两个 AI 调用角色：

| 角色 | 作用 |
|------|------|
| **evaluator** | 每轮采集后判断证据是否充分，决定是否继续、选哪个工具 |
| **synthesizer** | 基于所有证据卡，输出综合回答（ask）或真伪判断（verify）|

两者都调用你配置的 AI（同一个 endpoint/model）。evaluator 失败时自动 fallback 到保守规则（search → trafilatura → 停止）。

**自适应采集规则：**

1. **先 search，再判断**：`source=auto`（默认）时，ask/verify 先执行搜索，由 evaluator 判断证据是否足够。
2. **渐进式采集**：evaluator 决定是否需要继续采集（trafilatura 正文抽取、crawl4ai 动态渲染等）。
3. **最多 3 个工具**：max_tools=3，evidence_limit=12。evaluator 无法突破上限。
4. **MediaCrawler 不默认跑**：仅当问题明确涉及中文社区经验、争议、舆论、平台讨论时，evaluator 才选择 mediacrawler。普通事实查询、编程问题、教程搜索不会触发它。
5. **采集结果可缓存**：provider.collect() 的结果写入 acquisition cache，后续相同 query 直接命中。
6. **ask/verify 支持 session context**：追问自动识别，evaluator 用 AI 判断是否与历史上下文相关。
7. **默认显示进度**：stderr 输出时间戳进度，`--quiet` 关闭。JSON stdout 始终干净、不被进度污染。

**AI 配置说明**：高质量 ask/verify/research 依赖你配置的 AI provider（OpenAI / Anthropic / Gemini / 本地模型）。未配置 AI 时，ask/verify 会退化到本地 fallback（不调用 AI），research 不可用。

## MCP Server（给外部 AI 用）

source-radar 可以作为 MCP server，让 Claude Code、Claude Desktop、MiMoCode、Cursor 等支持 MCP 的 AI 工具直接调用搜索和抓取能力。

### 安装

```bash
# 项目有专用安装器，不要直接 uv sync
uv run python -m source_radar install
```

安装器会自动处理 MCP 依赖（`mcp>=1.0`）、Trafilatura、Crawl4AI 等所有可选依赖。

### 配置

**Claude Desktop / Claude Code**，在配置文件中添加：

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

**MiMoCode**，在 `~/.config/mimocode/mimocode.json` 中添加：

```json
{
  "mcp": {
    "source-radar": {
      "type": "local",
      "command": ["uv", "run", "--extra", "mcp", "--directory", "你的项目路径", "source-radar", "mcp"],
      "enabled": true,
      "environment": {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

### 暴露的工具

| 工具 | 作用 | 参数 |
|------|------|------|
| `web_search` | Bing 搜索，返回结果列表 | `query`（必填）、`limit`（默认 5，最大 10）、`site`（可选，限定域名）、`page`（翻页）、`nocache`（跳过缓存） |
| `fetch_url` | 抓取单个网页正文 | `url`（必填）、`max_chars`（默认 8000） |
| `search_github` | 搜索 GitHub issues/PRs | `query`（必填）、`limit`（默认 5，最大 10）、`page`（翻页）、`nocache` |
| `search_chinese_platforms` | 搜索中文平台（小红书/微博/B站等） | `query`（必填）、`platforms`（可选，如 `bili,tieba`）、`limit`（默认 3）、`nocache` |

### 质量评估

搜索结果自动附带质量评估（`⚠️ 质量: low/medium` + `💡 建议`）。检测器包括：
- `no-candidates` — 无搜索结果
- `semantic-mismatch` — 结果与查询语义不相关
- `method-answers-missing` — 方法型查询（怎么/如何/教程）但结果多为评测/参数页
- `navigation-heavy` — 正文是导航菜单
- `language-mismatch` — 查询语言与结果语言不匹配
- `domain-concentration` — 结果集中在单一域名
- `snippet-only` — 仅有搜索摘要，未抽取正文
- `key-platform-missing` — 新闻类查询缺少主流媒体结果

### 安全限制

- `fetch_url` 只允许 http/https，拒绝 localhost、内网地址、file:// 等
- 超时 30 秒，最大返回 50000 字符
- 搜索和抓取结果走现有缓存机制（search=6h, trafilatura=24h）
- `search_chinese_platforms` 需要 MediaCrawler bridge 运行（`engine start mediacrawler`），首次调用较慢（~30s/平台），缓存后极快。默认只跑 1 个平台，可通过 `platforms` 参数指定（如 `bili,tieba`）
- `fetch_url` 对 wiki/论坛域名（liquipedia.net、hltv.org、fandom.com 等）自动使用 Crawl4AI 渲染
- 搜索结果自动评估质量，低质量结果会显示 ⚠️ 警告和 💡 建议
- Agent 内置 AI Search Planner：自动生成 2-4 个搜索尝试，质量低时自动重试改词/换平台

### 使用

配置完成后，在 AI 对话中直接说"搜索 xxx"或"抓取 xxx 页面"，AI 工具会自动调用 source-radar。

## Claude Code Skill（推荐使用方式）

source-radar 的核心使用方式是 **Claude Code Skill**：安装后在对话中直接说"帮我查一下 XX"，Claude Code 自动调用 source-radar 搜索中文互联网，综合结果返回给你。

### 如果你是 AI Agent（Claude Code / Codex 等）在帮用户安装

**本项目有自己的 Agent 安装协议。不要按通用 Python/uv 项目经验自行推断安装步骤。**

#### 第 1 步：先读 Skill 文档

克隆后第一件事是读取项目的 Agent 安装指南，而不是直接跑 `uv sync`：

```bash
git clone https://github.com/Narylr350/source-radar.git
cd source-radar
python -c "from pathlib import Path; print(Path('skills/source-radar/SKILL.md').read_text(encoding='utf-8'))"
```

重点读 **"Initialization flow for AI agents"** 章节。

#### 第 2 步：安装 Skill 文件 + 非交互引擎安装

```powershell
# 安装 Skill（推荐用链接，git pull 后自动同步）
# Windows: 用 Junction（不需要管理员权限）
New-Item -ItemType Directory -Force $env:USERPROFILE\.claude\skills | Out-Null
New-Item -ItemType Junction -Path $env:USERPROFILE\.claude\skills\source-radar -Target "$PWD\skills\source-radar"

# macOS/Linux: 用符号链接
# mkdir -p ~/.claude/skills && ln -s "$(pwd)/skills/source-radar" ~/.claude/skills/source-radar

# 非交互安装引擎依赖（不会卡住，不会问你任何问题）
uv run python -m source_radar install --agent
```

#### 第 3 步：查看配置缺口

```bash
uv run python -m source_radar setup-plan --format json
```

根据返回的 `required_inputs` 向用户索要必需配置。**不要运行交互式 `install`（不带 --agent 的那个）。**

#### 禁止事项

- **不要直接跑 `uv sync` 或 `pip install`**——本项目依赖安装必须通过 `uv run python -m source_radar engine install` 或 `uv run python -m source_radar install --agent`
- **不要根据报错自行推断修复命令**——优先使用 `setup-plan` + `doctor` 的输出作为修复指引
- **不要跳过 Skill 直接凭 Python 经验操作**

### 如果你是真人手动安装

```powershell
git clone https://github.com/Narylr350/source-radar.git
cd source-radar

# 安装 Skill 文件
Copy-Item -Recurse skills/source-radar/ $env:USERPROFILE\.claude\skills\source-radar\

# 交互式一键安装（会问你 API key、打开浏览器等）
uv run python -m source_radar install
```

**推荐：用目录链接代替复制，这样 git pull 后 Skill 自动同步，不用每次手动复制：**

```powershell
# 先删除已复制的目录，再创建链接
Remove-Item -Recurse -Force $env:USERPROFILE\.claude\skills\source-radar
New-Item -ItemType Junction -Path $env:USERPROFILE\.claude\skills\source-radar -Target "$PWD\skills\source-radar"
```

macOS/Linux 用符号链接（需要项目路径保持不变）：

```bash
rm -rf ~/.claude/skills/source-radar
ln -s "$(pwd)/skills/source-radar" ~/.claude/skills/source-radar
```

### 使用 Skill

安装完成后，在 Claude Code 对话中直接说：

```
"帮我查一下 RTX 5090 电源接口问题在中文社区的讨论"
"搜一下小红书和 B 站上关于 Python 教程的评价"
"验证这个消息：XX 产品宣布涨价 30%"
```

Skill 会自动：
1. 检测引擎状态
2. source-radar 内部 evaluator 判断是否需要中文社区采集
3. 执行自适应采集、AI 综合
4. 返回分析报告（包含综合回答、关键要点、来源分布、分歧争议、噪音提示）

### 推荐：配置 MCP Server

Skill 通过 CLI 命令调用 source-radar，每次都是完整 agent 流程。如果你只需要搜索和抓取能力（不需要 AI 综合），配置 MCP Server 更轻量：

```bash
# 验证 MCP server 可用
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | uv run --extra mcp source-radar mcp
```

然后在你的 AI 工具中配置 MCP（详见上方 [MCP Server 章节](#mcp-server给外部-ai-用)）。配置后可以直接说"搜索 xxx"或"抓取 xxx 页面"，不走完整 agent 流程，响应更快。

### Skill 调用规范

- **不要手动拆 query**：用户一个问题 = 一个 ask/research/verify 命令。不要把一个复杂问题拆成多个 ask 调用。
- **不要绕过 source-radar 自己补 WebSearch/WebFetch**：source-radar 内部已做 adaptive collection。如果证据弱或缺失，如实报告，不要偷偷用自己工具补充搜索。
- **research 用 research 命令**：复杂多面问题用 `research`（走 planner/evaluator 多轮逻辑），不要混成多个 ask。

### Skill 文件结构

```
skills/source-radar/
├── SKILL.md          # 技能描述和触发条件
└── scripts/
    └── run.py        # 命令封装，自动管理服务生命周期
```

`run.py` 支持的命令：

| 命令 | 作用 |
|------|------|
| `run.py research "问题"` | 深度研究（复杂多面问题） |
| `run.py ask "问题"` | 综合信息分析 |
| `run.py verify "断言"` | 严格核验 |
| `run.py start` | 启动 MediaCrawler 服务 |
| `run.py stop` | 停止服务 |
| `run.py status` | 查看引擎状态 |
| `run.py doctor` | 检查配置并输出修复建议 |
| `run.py cookie` | 获取平台 Cookie |

## 命令行直接使用

不使用 Skill 时，也可以直接调用 CLI：

```powershell
# 一键安装
uv run python -m source_radar install

# 综合信息分析（默认显示进度，source=auto 自适应采集）
uv run python -m source_radar ask "RTX 5090 电源兼容问题的中文社区反馈"

# 启用 MediaCrawler（需先启动本地服务，见"引擎管理"）
uv run python -m source_radar ask "小红书上关于 XX 产品的真实评价" --local-services

# 深度研究（planner 自动为每个子查询选择合适工具）
uv run python -m source_radar research "9800x3d 微星b850 超频经验汇总" --max-rounds 2

# 严格核验
uv run python -m source_radar verify "某产品宣布涨价 30%"

# 安静模式（不输出进度，适合脚本/管线的 JSON 提取）
uv run python -m source_radar ask "问题" --format json --quiet

# Session context：追问自动关联历史
uv run python -m source_radar ask "9800x3d 怎么超频" --session oc
uv run python -m source_radar ask "那内存怎么调" --session oc   # 识别为追问

# Session context：禁用
uv run python -m source_radar ask "问题" --no-session

# 获取 Cookie
uv run python -m source_radar cookie

# 引擎管理
uv run python -m source_radar engine list
uv run python -m source_radar engine start mediacrawler
uv run python -m source_radar engine stop mediacrawler

# Cache 管理
uv run python -m source_radar cache status
uv run python -m source_radar cache clear
uv run python -m source_radar cache prune

# Session 管理
uv run python -m source_radar session status
uv run python -m source_radar session clear --session oc
uv run python -m source_radar session new
```

或用 PowerShell 快捷入口：

```powershell
.\source-radar.ps1 setup       # 一键安装
.\source-radar.ps1 ask "..."   # 综合分析
.\source-radar.ps1 verify "..." # 核验消息
```

### ask / verify / research 的区别

| 命令 | 适用场景 | 采集方式 | Session |
|------|---------|---------|---------|
| `ask` | 简单查询、教程查找、快速搜索 | 自适应采集（source=auto），max_tools=3 | 支持 `--session` |
| `verify` | 真伪核验、事实核查 | 自适应采集 + verify 严格模式（拒绝纯搜索结果，优先一手来源） | 支持 `--session` |
| `research` | 复杂多面问题、硬件调优、方案汇总 | Planner → 按 query 指定工具 → Collect → Dedupe → Synthesize | 暂不支持 session context |

### 自适应采集（Adaptive Collection）

ask/verify 默认 `source=auto` 时启用。工作流程：

```
Round 1: search（必跑）
  → evaluator 判断证据是否足够
    → 够 → 停止，输出
    → 不够 → Round 2: 选择下一个工具（e.g. trafilatura）
      → evaluator 再判断
        → 够 → 停止
        → 不够 → Round 3（最后一个）
```

规则：
- **max_tools=3**：最多跑 3 个工具。
- **evidence_limit=12**：证据达到 12 张卡后停止。
- **不重复工具**：已跑过的工具不再跑。
- **trafilatura 优先**：search 之后优先 trafilatura 正文抽取。
- **mediacrawler 受控**：仅中文社区争议/经验/舆论时由 evaluator 选择。
- **verify 模式更严格**：仅 search-result 证据会被强制追加 trafilatura；不自动跑 mediacrawler。

指定 `--source search` 或 `--url` 等参数时，走 legacy 固定工具路径，不走自适应采集。

### Acquisition Cache

缓存 provider.collect() 的结果（不缓存最终 AI 回答）：

```
.source-radar/cache/acquisition/
├── index.json           # 缓存索引
└── entries/<key>.json   # 单条缓存
```

| 规则 | 说明 |
|------|------|
| 缓存条件 | provider.collect() 返回 ok/items-found/candidates-found |
| 不缓存 | 实时 query（含 今天/最新/天气/股价等关键词）、error/unreachable 结果 |
| TTL | search=6h, trafilatura=24h, mediacrawler=12h, crawl4ai=24h |
| 淘汰 | max 1000 entries / 200MB；过期自动清理 + LRU |
| Cache key | provider + query + url + repo + limit + platform + schema_version + adapter_version + provider_signature |
| 不存储 | cookie、API key、local.env、provider secret |

### Session Context

ask/verify 支持 session context，用于识别追问、复用历史上下文：

```
.source-radar/sessions/<session_id>.jsonl
```

| 规则 | 说明 |
|------|------|
| 默认 session | 不带 `--session` 时自动使用 `default` session |
| 读取范围 | 最近 10 条记录、24 小时内 |
| 相关性判断 | 优先 AI evaluator → 失败 fallback lexical（追问词/共享词匹配） |
| 禁用 | `--no-session` |
| 存储内容 | query、status、tools_used、tools_skipped、cache_keys、evidence_refs（snippet 截断 ≤300 字）、answer_summary（截断 ≤500 字） |
| 不存储 | 完整网页正文、cookie、API key、local.env、provider secret |
| research | 暂不接 session context |

### Agent Trace / JSON 输出

`--format json` 输出的 `agent` 字段包含完整采集追踪：

```json
{
  "agent": {
    "mode": "analysis",
    "model": "gpt-4.1-mini",
    "planned_tools": ["search", "trafilatura"],
    "tool_calls": [
      {
        "tool": "search",
        "status": "ok",
        "elapsed_ms": "320",
        "cache_hit": "False",
        "cache_key": "abc123...",
        "cache_age_seconds": "",
        "limit": "5"
      }
    ],
    "context_used": true,
    "session_id": "oc",
    "context_records_read": 2,
    "context_ignore_reason": "",
    "reused_evidence_count": 0,
    "fresh_evidence_count": 5,
    "actually_used_tools": ["search", "trafilatura"],
    "skipped_tools": [{"tool": "mediacrawler", "reason": "不需要中文社区讨论"}],
    "cache_hit_count": 1,
    "fresh_tool_count": 1
  }
}
```

Markdown 报告展示简洁摘要，完整 trace 仅 JSON 可见。

### 证据保真（Evidence Fidelity）

每张证据卡同时包含三层信息：

| 字段 | 来源 | 长度限制 | 用途 |
|------|------|---------|------|
| `summary` | snippet 或正文前 500 字 | 500 字 | 快速概览 |
| `raw_excerpt` | 正文全文（优先）或 snippet | 3000 字 | 核对原文细节、参数、引用 |
| `distilled` | AI 结构化提炼（可选） | 不限 | 快速定位事实、参数、风险 |

搜索结果只有 summary 和 snippet 级别的 raw_excerpt。trafilatura/crawl4ai 抽取的正文会保留更长的 raw_excerpt（最多 3000 字），并记录原始长度和截断状态。

每张证据卡的 `compression` 字段记录保真质量：

```json
{
  "compression": {
    "method": "mechanical_excerpt+ai_distill",
    "summary_chars": 200,
    "raw_excerpt_chars": 2800,
    "raw_content_length": 12000,
    "raw_content_truncated": true,
    "ai_distilled": true,
    "loss_risk": "medium"
  }
}
```

`loss_risk` 含义：`low`（完整保留）、`medium`（正文被截断）、`high`（无正文或无摘要）。

AI 证据蒸馏（`--distill-evidence`）可选开启，对 raw_excerpt 做结构化提炼（事实、参数、风险、引用），不替代原文。默认 auto 模式：research 自动开启，ask/verify 在证据较多时开启。

## 环境要求

| 依赖 | 用途 | 安装 |
|------|------|------|
| Python >= 3.11 | 运行时 | `winget install python` 或 https://python.org |
| uv | 包管理和虚拟环境 | `winget install astral-sh.uv` 或 https://docs.astral.sh/uv/ |
| Git | 克隆仓库和 MediaCrawler | `winget install Git.Git` 或 https://git-scm.com |
| Chrome | Cookie 捕获浏览器（真实 Chrome，非 Chromium） | 系统自带或用 `winget install Google.Chrome` |

项目默认使用阿里云 PyPI 镜像加速下载。如需切换回官方源：

```powershell
$env:UV_INDEX_URL = "https://pypi.org/simple"
```

## AI 配置

source-radar 支持任何主流 AI API，包括 OpenAI、Anthropic Claude、Google Gemini，以及兼容 OpenAI 格式的本地模型（LM Studio、Ollama 等）：

```powershell
# 交互式配置（引导选择协议类型 + 模型列表）
uv run python -m source_radar config setup

# 非交互式：OpenAI / OpenAI 兼容 / 本地模型
uv run python -m source_radar config set-ai --api-key "sk-xxx" --endpoint "https://api.openai.com/" --model "gpt-4.1-mini"

# 非交互式：Anthropic Claude
uv run python -m source_radar config set-ai --api-key "sk-ant-xxx" --endpoint "https://api.anthropic.com/" --model "claude-3-5-haiku-latest" --provider anthropic

# 非交互式：Google Gemini
uv run python -m source_radar config set-ai --api-key "AIzaXXX" --endpoint "https://generativelanguage.googleapis.com/" --model "gemini-2.0-flash" --provider gemini

# 非交互式：本地模型（LM Studio / Ollama 等，通常 OpenAI 兼容）
uv run python -m source_radar config set-ai --api-key "sk-local" --endpoint "http://127.0.0.1:1234/" --model "llama-3.2-3b"

# 查看配置（密钥已脱敏）
uv run python -m source_radar config show

# 清除配置
uv run python -m source_radar config clear-ai
```

| 协议类型（`--provider`） | 适用场景 | 鉴权方式 |
|--------------------------|----------|----------|
| `openai`（默认） | OpenAI、本地模型、大多数兼容接口 | `Authorization: Bearer` |
| `anthropic` | Anthropic Claude API | `x-api-key` 头 |
| `gemini` | Google Gemini API | `Authorization: Bearer` |
| `x-api-key` | 其他使用 `x-api-key` 头的接口 | `x-api-key` 头 |

环境变量也可覆盖：`OPENAI_API_KEY` / `SOURCE_RADAR_OPENAI_ENDPOINT` / `SOURCE_RADAR_OPENAI_MODEL` / `SOURCE_RADAR_AI_PROVIDER`。

配置完成后验证连通性：

```powershell
uv run python -m source_radar config test-ai
```

### API 调用重试与超时

AI API 调用可能因网络抖动、限流、服务端错误等原因失败。source-radar 内置自动重试：

| 参数 | 默认值 | 环境变量 |
|------|--------|----------|
| 单次请求超时 | 60 秒 | `SOURCE_RADAR_REQUEST_TIMEOUT` |
| 最大重试次数 | 3 次 | `SOURCE_RADAR_MAX_RETRIES` |

重试范围：429（限流）、500/502/503/504（服务端错误）、超时、连接断开。退避间隔：2s → 5s → 10s。

如果 AI 服务不稳定，可适当增大重试次数：

```powershell
$env:SOURCE_RADAR_MAX_RETRIES = "5"
```

### 日志配置

source-radar 支持文件日志，便于排查问题：

```powershell
# 开启日志（默认关闭）
uv run python -m source_radar config set-logging --enabled true --level INFO

# 关闭日志
uv run python -m source_radar config set-logging --enabled false

# 查看日志配置
uv run python -m source_radar config show
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | false | 开关 |
| `level` | INFO | DEBUG/INFO/WARNING |
| `max_bytes` | 1048576 (1MB) | 单文件上限 |
| `backup_count` | 3 | 保留旧日志数 |

日志文件：`.source-radar/source-radar.log`，自动轮转。也可直接编辑 `.source-radar/config.json` 的 `logging` 字段。

环境变量覆盖：`SOURCE_RADAR_LOG_LEVEL=INFO`（优先级高于配置文件）。

## Cookie 获取（辅助工具）

中文社区平台需要登录态才能搜索。source-radar 提供浏览器辅助捕获工具，**但不能保证所有平台 100% 成功**——微博、小红书等平台有复杂的风控机制，特定环境、IP、设备指纹可能导致登录页白屏、弹窗空白、二维码不加载等。

### 优先方案：手动导入 Cookie（推荐）

这是最可靠的方式。用你的日常浏览器登录目标平台，从 Network 请求里复制 Cookie。

**从 Network 请求复制：**

1. 打开目标网站并确认已经登录
2. F12 → Network
3. 刷新页面
4. 点一个目标平台自己的请求（如 `weibo.com`、`xiaohongshu.com`）
5. Headers → Request Headers → Cookie，复制整段值
6. 写入 `.source-radar/local.env`

```env
SOURCE_RADAR_XHS_COOKIE="a1=xxx; web_session=xxx; ..."
SOURCE_RADAR_WEIBO_COOKIE="SUB=xxx; SCF=xxx; ..."
SOURCE_RADAR_BILI_COOKIE="SESSDATA=xxx; bili_jct=xxx; ..."
```

Network 里的 Cookie 就是浏览器实际发送的格式（`name=value; name2=value2`），直接用。

**备选：从 Application 手动拼接**

F12 → Application → Storage → Cookies → 选择目标域名，手动把 `name` 和 `value` 拼成 `name1=value1; name2=value2`。不要把 Domain、Path、Expires、HttpOnly 等属性拼进去。

**安全提醒：** Cookie 等同于登录态，不要分享给任何人，不要提交到 Git。`.source-radar/local.env` 应保持本地私有。不建议安装来历不明的 Cookie 浏览器扩展。

### 辅助方案：浏览器自动捕获

如果手动导入不方便，也可以尝试自动捕获（微博等平台可能因风控失败）：

```powershell
uv run python -m source_radar cookie                    # 所有未配置平台
uv run python -m source_radar cookie --platform wb      # 仅微博
uv run python -m source_radar cookie --platform wb --force  # 微博重新获取
```

- 已配置的平台自动跳过（除非 `--force`）
- 登录态持久化在 `.source-radar/browser-profiles/`，下次复用
- 微博最容易卡住，建议单独操作：`source-radar cookie --platform wb`

## 引擎架构

```
用户问题
  → agent 规划采集源
    ├─ search（搜索引擎）           → 搜索发现候选 URL
    ├─ trafilatura (GPL-3.0)      → 通用网页正文抽取
    ├─ crawl4ai  (Apache-2.0)     → 浏览器渲染动态页面
    └─ mediacrawler (外部 bridge)  → 中文社区平台搜索（evaluator 按需选择）
  → 证据卡清洗去重
  → AI 综合输出
```

| 引擎 | 类型 | 用途 |
|------|------|------|
| Trafilatura | pip 包 | 通用网页正文抽取，轻量快速 |
| Crawl4AI | pip 包 + 浏览器 | 动态页面渲染采集 |
| MediaCrawler | 外部独立服务 | 小红书/微博/B站/贴吧/抖音/知乎搜索 |

## 全部 CLI 命令

| 命令 | 作用 |
|------|------|
| `install` | 一键安装：引擎 + AI 配置 + Cookie 获取 |
| `ask <问题>` | 综合信息分析（支持 `--quiet`、`--session`、`--no-session`、`--format json/markdown`、`--local-services`） |
| `verify <断言>` | 严格核验，返回证据卡和可信度判断（支持 `--quiet`、`--session`、`--no-session`、`--local-services`） |
| `research <问题>` | 深度研究：planner → 多轮 collect → dedupe → synthesize（支持 `--max-rounds 2`） |
| `cache status/clear/prune` | 查看/清除/清理采集缓存 |
| `session status/clear/new` | 查看/清除/新建 session |
| `cookie` | 打开浏览器引导登录各平台，自动捕获 Cookie |
| `cookie set --platform <name>` | 为指定平台写入 Cookie（交互式） |
| `cookie show` | 显示已配置平台的 Cookie 状态（脱敏） |
| `engine list` | 列出爬虫引擎状态 |
| `engine status` | 检查引擎就绪状态 + 修复建议 |
| `engine install` | 安装全部爬虫引擎依赖 |
| `engine start/stop <name>` | 启停服务型引擎 |
| `probe --source <name>` | 检查单个采集源是否就绪 |
| `health` | 查看整体健康状态 |
| `doctor` | 检查整体配置，输出缺口和修复建议 |
| `config setup/set-ai/show/clear-ai/test-ai` | 管理并验证 AI 配置（`set-openai`/`clear-openai` 为旧别名，保持兼容） |
| `config set-provider/clear-provider` | 管理 Provider 桥配置 |
| `mcp` | 启动 MCP server（stdio 模式，供 Claude Code / MiMoCode / Cursor 等调用） |
| `integrations audit/status` | 查看外部集成许可和状态 |

> **`--local-services`**：ask/verify/research 加此 flag 后，MediaCrawler 才会进入工具池（前提是已启动本地 MediaCrawler 服务：`engine start mediacrawler`）。不带此 flag 时 mediacrawler 不参与采集。

## 卸载

先预览将删除什么（默认不会删，只是展示计划）：

```bash
uv run python -m source_radar uninstall --all
```

确认删除：

```bash
uv run python -m source_radar uninstall --all --yes
```

只清除 AI 配置（保留项目文件）：

```bash
uv run python -m source_radar uninstall --user-config --yes
```

只清除项目本地文件（保留 Skill 和配置）：

```bash
uv run python -m source_radar uninstall --project --yes
```

## 开发

```powershell
git clone https://github.com/Narylr350/source-radar.git
cd source-radar
uv sync --extra dev           # 安装全部可选引擎（含 trafilatura GPL-3.0 + crawl4ai Apache-2.0）
uv run crawl4ai-setup         # 安装 Playwright 浏览器（仅 crawl4ai extra 安装后才需要）
uv run python -m unittest discover -s tests -v   # 运行测试
```

如果只想要 Apache-2.0 组件，跳过 GPL-3.0：`uv sync --extra crawl4ai`

## 许可证与合规

普通本地使用（clone → install → run）不需要关心分发合规问题。以下内容仅在二次分发、打包、或商用集成时需要重点阅读。

**核心仓库：Apache-2.0。** 所有第三方引擎均为可选依赖，通过外部集成方式使用，源码不进入 Apache-2.0 核心。

| 组件 | 许可证 | 集成方式 | 合规说明 |
|------|--------|----------|----------|
| source-radar 核心 | Apache-2.0 | — | 自由使用、修改、分发 |
| Crawl4AI | Apache-2.0 | pip 可选包 (`uv sync --extra crawl4ai`) | 与核心兼容 |
| Playwright | Apache-2.0 | pip 包（Crawl4AI 依赖） | 与核心兼容 |
| Trafilatura | **GPL-3.0** | pip 可选包 (`uv sync --extra trafilatura`) | **Copyleft**：使用 Trafilatura 会使你的整体分发受 GPL-3.0 约束 |
| MediaCrawler | 非商业学习/研究 | 外部独立服务（bridge 调用） | 不 vendor 源码，用户自行安装 |

**关键注意事项：**

- **Trafilatura 是 GPL-3.0**：它不是核心依赖，安装时明确标注许可证。如果你分发包含 Trafilatura 的 source-radar，整体可能需要遵守 GPL-3.0。如果你不需要 GPL 组件，跳过它：`source-radar` 核心在没有 Trafilatura 的情况下仍可通过 Crawl4AI（Apache-2.0）完成网页采集。
- **MediaCrawler 不得进入核心代码**：通过外部 bridge 进程调用，仅读取其 HTTP API。MediaCrawler 源码永远不进入 source-radar 仓库。
- **所有第三方许可文件**应随分发一起提供。自动安装脚本会显示上游项目、版本、许可证和源码 URL。
