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
uv run python -m source_radar install
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

1. **Check status**: Run `scripts/run.py status`. If MediaCrawler shows "stopped", run `start`.
2. **Run research**: `scripts/run.py ask "query"`. Always include platform keywords when searching for community discussions.
3. **Report results**: Summarize key findings in Chinese. Include notable sources and disagreements.
4. **Cleanup**: Optionally `stop` services when done.

## Query types

- **Community/social**: Include 小红书/微博/B站/贴吧/抖音/知乎 in the query → triggers MediaCrawler
- **General web**: No platform keywords → uses search engines + Trafilatura + Crawl4AI
- **Mixed**: Combine both for broad coverage

## Troubleshooting

- **"Cookie 未配置"**: Guide user to run `python -m source_radar cookie`
- **"Playwright 未安装"**: Guide user to run `uv run crawl4ai-setup`
- **"MediaCrawler 未安装"**: Guide user to run `python -m source_radar engine install`
- **"AI 未配置"**: Guide user to run `python -m source_radar config setup`
