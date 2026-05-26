---
name: source-radar
description: >
  Chinese internet research and fact-checking CLI. Use when the user wants to search, research, verify claims, or find information on Chinese platforms (小红书/微博/B站/贴吧/抖音/知乎). Triggers include: "查一下", "搜索", "验证", "核验", "有没有关于...的讨论", "X上说Y是真的吗", "帮我查", "搜一下". Use for any research task involving Chinese-language sources, community discussions, product reviews, tutorials, or fact verification.
---

# Source Radar

Search and analyze the Chinese internet using source-radar.

## Setup (one-time)

The skill needs `uv` and Python >= 3.11. Install source-radar:

```bash
git clone https://github.com/Narylr350/source-radar.git
cd source-radar
uv run uv run python -m source_radar install
```

This installs all engines, configures AI, and guides cookie capture for Chinese platforms.

## How to use

### Research

When the user asks to search or research something, use `scripts/run.py ask`:

```bash
python <skill-dir>/scripts/run.py ask "the user's query"
```

Add community platform names (小红书/微博/B站/贴吧/抖音) to the query to trigger platform search.

### Verify claims

```bash
python <skill-dir>/scripts/run.py verify "the claim to check"
```

### Service management

```bash
python <skill-dir>/scripts/run.py start    # start MediaCrawler
python <skill-dir>/scripts/run.py stop     # stop it
python <skill-dir>/scripts/run.py status   # check engine health
```

## Workflow

First time or if commands fail, run a health check:

```bash
python <skill-dir>/scripts/run.py doctor
```

Doctor checks every prerequisite: project root, uv, Python version, CLI, AI config, cookies, engine status. If it reports missing setup, guide the user through the printed commands before proceeding.

If doctor passes, run research or verification directly. `ask` and `verify` auto-run a lightweight check first — if the environment is not ready they will print setup guidance instead of failing with errors.

1. **Check**: `scripts/run.py doctor` shows what's ready and what's missing
2. **Research**: `scripts/run.py ask "query"` (auto-checks environment first)
3. **Verify**: `scripts/run.py verify "claim"` (auto-checks environment first)
4. **Report results**: Summarize key findings in Chinese. Include notable sources and disagreements.
5. **Cleanup**: Optionally `stop` services when done.

## Query types

- **Community/social**: Include 小红书/微博/B站/贴吧/抖音/知乎 in the query → triggers MediaCrawler
- **General web**: No platform keywords → uses search engines + Trafilatura + Crawl4AI
- **Mixed**: Combine both for broad coverage

## AI configuration

source-radar needs an OpenAI-compatible API key to run AI synthesis. If the user hasn't configured it yet:

### If user provides API key in conversation

Save it directly via CLI (no interactive prompts needed):

```bash
uv run python -m source_radar config set-openai --api-key "sk-xxx" --endpoint "https://api.openai.com/" --model "gpt-4.1-mini"
```

For non-OpenAI endpoints (local models, proxies), include `--endpoint` and `--model`:

```bash
uv run python -m source_radar config set-openai --api-key "sk-local-xxx" --endpoint "http://127.0.0.1:9317/" --model "gemini-3.5-flash"
```

### Interactive setup (user doesn't know the flow)

Guide them to run `uv run python -m source_radar config setup` — it will prompt for API key, endpoint, and automatically fetch available models to choose from.

### Check current config

```bash
uv run python -m source_radar config show
```

## Troubleshooting

- **"AI 未配置"**: Ask user for their API key and endpoint, then run `config set-openai` above. Or guide to `uv run python -m source_radar config setup`.
- **"Cookie 未配置"**: Guide user to run `uv run python -m source_radar cookie`
- **"Playwright 未安装"**: Guide user to run `uv run crawl4ai-setup`
- **"MediaCrawler 未安装"**: Guide user to run `uv run python -m source_radar engine install`
