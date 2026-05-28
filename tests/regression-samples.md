# v3 回归样本

tag: `v3-adaptive-full`

以下样本用于回归验证。每次修改 evaluator prompt、session relevance prompt、或 MediaCrawler 触发阈值后，至少跑一遍。

## 1. 简单 ask

```bash
uv run python -m source_radar ask "python 列表推导式怎么写" --format json --quiet
```

预期：
- status: analysis-ready
- evidence >= 1
- agent.planned_tools 包含 search
- 无 stderr progress 输出

## 2. verify 简单真假

```bash
uv run python -m source_radar verify "1+1等于2" --format json --quiet
```

预期：
- status: ai-judged
- judgement.confidence: high
- evidence >= 1

## 3. 实时 query

```bash
uv run python -m source_radar ask "今天天气" --format json --quiet
```

预期：
- cache 不命中（实时关键词跳过缓存）
- status: analysis-ready 或 no-evidence
- 如果有 session context，reuse_evidence=false

## 4. session 连续追问

```bash
uv run python -m source_radar ask "9800x3d 微星b850 怎么超频" --format json --session oc --quiet
uv run python -m source_radar ask "那内存怎么调" --format json --session oc --quiet
```

预期：
- 第二问 agent.context_used = true
- 第二问 agent.session_id = "oc"
- 第二问 agent.context_records_read >= 1
- 第二问最终综合（synthesis）应体现上文语境（不把"那"当独立问题）
- 如果 session context 不相关，context_ignore_reason 非空

## 5. 硬件经验类

```bash
uv run python -m source_radar ask "9800x3d 微星b850 超频 内存时序 能效比" --format json --quiet
```

预期：
- planned_tools 包含 search + trafilatura（可能还有 crawl4ai）
- evidence 中 source_type 不全是 search-result
- status: analysis-ready

## 6. 中文社区争议类

```bash
uv run python -m source_radar verify "张雪峰死了吗" --format json --quiet
```

预期：
- planned_tools 包含 mediacrawler（如已配置）
- 如果 mediacrawler 未配置，跳过并记录 reason
- evidence 来源应包含社区类（如 mediacrawler 可用）

## 7. research max-rounds=2

```bash
uv run python -m source_radar research "2025年最值得买的机械键盘" --max-rounds 2 --format json --quiet
```

预期：
- requested_max_rounds = 2
- executed_rounds >= 1
- evidence_count >= 3
- status 不是 ai-error
- agent.mode = research

---

## 验证清单

每次微调后，对照以下字段检查 JSON 输出：

| 字段 | 位置 | 要求 |
|------|------|------|
| agent.context_used | agent | 追问时 true |
| agent.session_id | agent | 与 --session 一致 |
| agent.context_ignore_reason | agent | 不相关时非空 |
| agent.reused_evidence_count | agent | reuse 时 > 0 |
| agent.cache_hit_count | agent | 命中时 > 0 |
| agent.fresh_tool_count | agent | 新采集时 > 0 |
| tool_call.cache_key | agent.tool_calls[] | 每个 tool_call 都有 |
| tool_call.cache_age_seconds | agent.tool_calls[] | 命中时 "0" 或正整数，miss 时 "" |
| skipped_tool.decided_by | agent.tool_calls[] | skipped 时 "collection_evaluator" |
| skipped_tool.skip_reason | agent.tool_calls[] | skipped 时与 reason 相同 |
