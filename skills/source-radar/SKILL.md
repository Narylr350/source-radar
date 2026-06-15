---
name: source-radar
description: >
  Chinese internet research and fact-checking CLI. Use when the user wants to search, research, verify claims, or find information on Chinese platforms (小红书/微博/B站/贴吧/抖音/知乎). Triggers include: "查一下", "搜索", "验证", "核验", "有没有关于...的讨论", "X上说Y是真的吗", "帮我查", "搜一下". Use for any research task involving Chinese-language sources, community discussions, product reviews, tutorials, or fact verification.
---

# Source Radar

Search and analyze the Chinese internet using source-radar.

## Tool boundaries (READ THIS FIRST)

When this skill is invoked, source-radar is the PRIMARY research tool.

**Do NOT bypass source-radar:**
- Do NOT call Web Search / WebFetch just because source-radar results look incomplete
- Do NOT supplement source-radar findings with your own search
- If evidence is weak or missing, say exactly that — do not silently fill gaps

**Only use external Web Search when:**
1. source-radar command fails entirely (crash, not "weak results"), OR
2. The user explicitly asks you to use normal web search, OR
3. You clearly label it as fallback outside source-radar

## Initialization flow for AI agents

When installing source-radar for the user, NEVER run `uv sync` directly. Follow this flow:

### 1. Clone and install

```bash
git clone https://github.com/Narylr350/source-radar.git
cd source-radar

# Install core dependencies
uv run python -m source_radar engine install

# Install SearXNG (REQUIRED — websearch foundation)
uv run python -m source_radar engine install --searxng
uv run python -m source_radar engine start searxng
```

SearXNG is REQUIRED. Without it, search quality is degraded (Bing fallback only).

### 2. Check what's needed

```bash
uv run python -m source_radar setup-plan --format json
```

Read `setup-plan` JSON. It tells you:
- `required_inputs`: What MUST be configured (AI config — required, SearXNG bridge)
- `optional_inputs`: What CAN be configured (cookies, MediaCrawler)

### 3. AI configuration (REQUIRED)

AI configuration is mandatory — without it source-radar cannot complete ask/verify.

If AI config is missing, ask the user for:
- API key
- Endpoint (default: https://api.openai.com/)
- Model (or fetch available models)

```bash
uv run python -m source_radar config set-ai --api-key "<key>" --endpoint "<endpoint>" --model "gpt-4.1-mini"
uv run python -m source_radar config test-ai
```

Do NOT proceed to ask/verify until `config test-ai` passes.

### 4. Cookies (optional — for Chinese community platforms)

Ask the user whether they want Chinese community platform access. If yes:
- They can send you Cookie strings from their browser's Network tab
- Write them with: `uv run python -m source_radar cookie set --platform <key> --value "<cookie>"`
- Check configured platform status: `uv run python -m source_radar cookie show`
- Or guide them to run `uv run python -m source_radar cookie` themselves

### 5. Verify

```bash
uv run python -m source_radar probe --source searxng --query "test"
uv run python -m source_radar config test-ai
uv run python -m source_radar engine list
```

## How to use

### Routing: ask vs verify vs research

**Use `research` when the user asks a complex open-ended question:**
- "X 怎么弄 / 怎么选 / 怎么超频 / 怎么调 / 怎么配置比较稳"
- "X 值不值得 / 给完整方案 / 帮我整理方案"
- "X 争议怎么回事 / 社区经验汇总 / 对比分析"

```bash
uv run python -m source_radar research "query" --local-services
```

**research 耗时较长（3-8 分钟），必须使用 `run_in_background: true`：**

```json
{
  "command": "uv run python -m source_radar research \"query\" --local-services",
  "run_in_background": true,
  "timeout": 600000
}
```

当 `research` 适用时：
- Run exactly ONE `research` command first.
- Do NOT manually rewrite the question into multiple `ask` commands.
- Do NOT call Web Search / WebFetch to supplement.
- **research does NOT support --session.** Session context is for ask/verify only.

**Use `verify` when the user asks a yes/no factual question:**
- "X 是真的吗？" / "X 死了吗？" / "X 发生了吗？"

```bash
uv run python -m source_radar verify "claim"
```

**Use `ask` for simple one-shot research:**
- "帮我查一下 X" / "搜索 X" / "X 是什么？"

```bash
uv run python -m source_radar ask "query"
```

Rule of thumb: complex multi-aspect → `research`. yes/no → `verify`. simple lookup → `ask`.

### Adaptive timeout

Timeout is NOT fixed. It adapts to workload:
- Base: 60 seconds (search + AI planning)
- Per MediaCrawler platform: +30 seconds
- Hard cap: 300 seconds

Example: 2 platforms → 120s; 4 platforms → 180s.

### Hung detection (MediaCrawler)

If MediaCrawler appears healthy but makes no progress:
1. Poll status + logs every 2 seconds
2. 5 consecutive polls (10s) with no new logs →判定假死
3. Calls `POST /api/crawler/stop` (SIGTERM → 15s → SIGKILL)
4. Reads partial results, releases lock

### MediaCrawler startup retry

`local_services_for_query` auto-starts MediaCrawler if needed:
1. Health check → unhealthy → attempt start
2. Wait 15 seconds
3. Fail → wait 2s → retry once
4. All fail → skip, don't block agent

### Session context (ask/verify only)

```bash
uv run python -m source_radar ask "9800x3d 怎么超频" --session oc
uv run python -m source_radar ask "那内存怎么调" --session oc   # recognized as follow-up
```

### Default progress output

`ask`, `verify`, and `research` all show progress on stderr by default. Use `--quiet` to suppress.

```bash
uv run python -m source_radar ask "query" --quiet --format json
```

### Service management

```bash
uv run python -m source_radar engine start searxng      # start SearXNG
uv run python -m source_radar engine start mediacrawler  # start MediaCrawler
uv run python -m source_radar engine stop searxng        # stop SearXNG
uv run python -m source_radar engine status              # check all engines
```

## MCP Server (optional)

After AI config is working, the user can set up MCP server for direct tool access in their AI conversations.

**Claude Code** — add to `~/.claude.json` under `mcpServers`:
```json
"source-radar": {
  "command": "uv",
  "args": ["run", "--extra", "mcp", "--directory", "<project-path>", "source-radar", "mcp"],
  "type": "stdio"
}
```

MCP exposes 6 tools: `web_search`, `fetch_url`, `fetch_search_results`, `search_github`, `search_chinese_platforms`, `fetch_github_file`. All search tools support `page`, `nocache`, and automatic quality assessment.

`fetch_search_results` combines search + batch fetch: search first, then extract full text from top N URLs. Use when web_search snippets are not enough.

When SearXNG health shows `degraded` + `captcha-suspended`, search quality is reduced. `engine status` shows which engines are affected.

## AI configuration details

source-radar needs an AI API key to run synthesis and evaluation. It supports OpenAI, Anthropic, Google Gemini, and any OpenAI-compatible local model.

**OpenAI or OpenAI-compatible / local model:**
```bash
uv run python -m source_radar config set-ai --api-key "sk-xxx" --endpoint "https://api.openai.com/" --model "gpt-4.1-mini"
```

**Anthropic Claude:**
```bash
uv run python -m source_radar config set-ai --api-key "sk-ant-xxx" --endpoint "https://api.anthropic.com/" --model "claude-3-5-haiku-latest" --provider anthropic
```

**Google Gemini:**
```bash
uv run python -m source_radar config set-ai --api-key "AIzaXXX" --endpoint "https://generativelanguage.googleapis.com/" --model "gemini-2.0-flash" --provider gemini
```

`--provider` choices: `openai` (default), `anthropic`, `gemini`, `x-api-key`.

## Troubleshooting

- **"AI 未配置"**: Run `uv run python -m source_radar config set-ai` or `config setup`
- **"SearXNG 未安装"**: Run `uv run python -m source_radar engine install --searxng && engine start searxng`
- **"Cookie 未配置"**: Run `uv run python -m source_radar cookie` or `cookie set --platform <key>`
- **"MediaCrawler 未安装"**: Run `uv run python -m source_radar engine install --community`
- **Search returns noise**: Check `uv run python -m source_radar probe --source searxng --query "test"`
