# MCP Server 设计文档

日期：2026-06-11

## 背景与动机

Claude Code 接入第三方模型后，内置 WebSearch 工具不可用（实测返回 0 results）。source-radar 已有 Bing 搜索、Trafilatura/Crawl4AI 抓取、MediaCrawler 中文平台采集等能力，将其包装为 MCP server，让外部 AI 直接调用替代缺失的 WebSearch。

外部 AI 负责推理，source-radar 只负责采集——不走内置 AI agent 流程。

## 设计原则（基于 MCP 官方规范）

1. **单一职责**：每个 tool 只做一件事，不混合搜索和抓取
2. **模型控制**：LLM 自主决定何时调用哪个 tool
3. **结构化输出**：同时返回纯文本（LLM 直读）和结构化数据（程序解析）
4. **优雅降级**：工具不可用时返回明确错误文本，不抛异常
5. **输入校验**：用 JSON Schema 定义输入，服务端二次校验
6. **幂等性**：相同输入相同输出（走缓存），不产生副作用

## 目标

- 暴露三个 MCP tool：搜索、抓取页面、中文平台搜索
- 支持 stdio 模式（随用随关，Claude Desktop / Claude Code 直接配置）
- 支持 HTTP/SSE 模式（手动启停，供其他 agent 连接）
- 不修改现有任何模块，新增 `app/source_radar/mcp/` 模块
- 走现有 acquisition cache，避免重复请求

## 非目标

- 不暴露内置 AI agent（不走 ask/verify 流程）
- 不做后台 daemon 或自动重启
- 不引入新配置文件（复用现有 config 和环境变量）
- 不返回完整 EvidenceCard（只返回外部 AI 需要的字段）

## 架构

### 新增模块

```
app/source_radar/mcp/
    __init__.py     # 导出 run_stdio, run_http
    server.py       # MCP server 定义，三个 tool
```

`mcp` 依赖作为 optional extra 加入 `pyproject.toml`：

```toml
[project.optional-dependencies]
mcp = ["mcp>=1.0"]
```

### CLI 入口

在现有 `cli.py` 的 `build_parser()` 中加入 `mcp` 子命令：

```
source-radar mcp          # stdio 模式
source-radar mcp serve    # HTTP/SSE 模式，默认端口 8765
source-radar mcp serve --port <PORT>
```

## 三个 MCP Tool

### `web_search`

搜索引擎搜索，返回结果列表。

**输入 schema：**
```json
{
  "type": "object",
  "properties": {
    "query": {"type": "string", "description": "搜索关键词"},
    "limit": {"type": "integer", "description": "返回条数，默认 5，最大 10", "default": 5}
  },
  "required": ["query"]
}
```

**底层：** `BingSearchProvider`（cn.bing.com，无需 API key）

**返回格式：**
```
搜索结果 (query: "xxx", 5 条):

1. 标题
   URL: https://...
   摘要: ...

2. 标题
   URL: https://...
   摘要: ...
```

**错误处理：**
- 搜索无结果：返回 "未找到相关结果"（不报错）
- 网络失败：返回错误描述 + 建议重试（isError=true）

### `fetch_url`

抓取单个页面正文。

**输入 schema：**
```json
{
  "type": "object",
  "properties": {
    "url": {"type": "string", "description": "要抓取的 URL"},
    "max_chars": {"type": "integer", "description": "最大返回字符数，默认 8000", "default": 8000}
  },
  "required": ["url"]
}
```

**底层：** Trafilatura 优先 → 返回正文 < 200 字符时 fallback Crawl4AI

**返回格式：**
```
页面正文 (来源: https://..., 提取器: trafilatura, 原始长度: 12345 字符, 截取前 8000 字符):

[正文内容]
```

**错误处理：**
- URL 无效/无法访问：返回错误描述（isError=true）
- 正文提取失败：返回 "无法提取正文内容"（isError=true）
- Crawl4AI 不可用：只用 Trafilatura，不报错

### `search_chinese_platforms`

中文社区平台搜索（小红书/微博/B站/贴吧/抖音/知乎）。

**输入 schema：**
```json
{
  "type": "object",
  "properties": {
    "query": {"type": "string", "description": "搜索关键词"},
    "platforms": {
      "type": "array",
      "items": {"type": "string"},
      "description": "指定平台列表，为空则搜全部已配置平台"
    },
    "limit": {"type": "integer", "description": "每平台返回条数，默认 3", "default": 3}
  },
  "required": ["query"]
}
```

**底层：** `ExternalBridgeProvider`（读现有 bridge endpoint 配置）

**返回格式：**
```
中文平台搜索结果 (query: "xxx"):

[小红书] 标题
  URL: https://www.xiaohongshu.com/...
  摘要: ...
  作者: xxx, 发布时间: 2026-01-01

[微博] 标题
  URL: https://weibo.com/...
  摘要: ...
```

**错误处理：**
- Bridge 未配置/不在线：返回 "MediaCrawler bridge 未启动。请运行: source-radar engine start mediacrawler"（不报错，给操作指引）
- 指定平台无 cookie：返回 "平台 xxx 未配置 cookie，跳过"
- 全部平台无 cookie：返回 "未配置任何平台 cookie，请运行: source-radar cookie"（isError=true）

## 数据流

```
外部 AI 调用 tool
    → MCP server (server.py)
        → AcquisitionRequest(query=..., limit=...)
        → Provider.collect()
            → AcquisitionResult
        → 格式化为纯文本
    → 返回给外部 AI
```

不经过 agent.py、evidence.py、judgement.py、reporting.py。

## 配置复用

- Bing 搜索：直接调用 `BingSearchProvider`，无需额外配置
- Bridge endpoint：从环境变量 `SOURCE_RADAR_MEDIACRAWLER_ENDPOINT` 读取，或读现有 provider config
- Cookie：从 `.source-radar/local.env` 读取（现有机制）
- 无需新增配置命令

## 缓存

走现有 acquisition cache：
- `web_search` 和 `fetch_url` 结果自动缓存
- TTL：search=6h, trafilatura=24h
- 相同 query 直接命中缓存，不重复请求

## 安装

```bash
uv sync --extra mcp
```

Claude Desktop 配置示例：

```json
{
  "mcpServers": {
    "source-radar": {
      "command": "uv",
      "args": ["run", "--extra", "mcp", "python", "-m", "source_radar", "mcp"],
      "cwd": "/path/to/source-radar"
    }
  }
}
```

Claude Code 配置示例：

```json
{
  "mcpServers": {
    "source-radar": {
      "command": "uv",
      "args": ["run", "--extra", "mcp", "python", "-m", "source_radar", "mcp"]
    }
  }
}
```

## 测试范围

- `web_search` 用 mock BingSearchProvider 验证返回格式和错误处理
- `fetch_url` 验证截断逻辑、Trafilatura → Crawl4AI fallback
- `search_chinese_platforms` 验证 bridge 不在线时的友好错误文本
- 验证缓存命中行为
- stdio 模式启动冒烟测试
