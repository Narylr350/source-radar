# PROJECT

## Goal

`source-radar` 是面向外部 AI 的、本地可控、可诊断、可审计的信息采集内核。项目通过 MCP 和 CLI 提供网页、GitHub 与中文社区信息采集，并把不同后端的结果转换为统一证据结构。

当前阶段的核心目标不是重写 MediaCrawler，而是删除 source-radar 额外增加的 HTTP bridge 和重复转换层，直接接入固定版本的 MediaCrawler 本地源码能力：

```text
MCP / CLI
→ source-radar local-source adapter
→ .source-radar/engines/mediacrawler/source
→ MediaCrawler platform client/crawler
→ platform
```

source-radar 负责 MCP、能力发现、安装缓存、生命周期、调用适配、错误诊断和证据归一化；MediaCrawler 继续负责平台 endpoint、签名、浏览器登录、Cookie、搜索、详情、评论和风控相关实现。

## Users and Scenarios

- 外部 AI 通过 MCP 搜索网页、GitHub 和中文社区来源。
- 研究者使用中文社区中的经验、争议、教程、故障报告和用户反馈核验问题。
- 开发者通过 CLI 或 MCP 查看 backend 的真实安装、运行、登录和错误状态。
- 用户网络不稳定，需要下载、源码 checkout、wheel、浏览器运行时可缓存、可恢复、可离线复用。
- 外部 AI 不知道本机仓库绝对路径，也不应被要求执行项目内部 shell 命令。

核心场景：

1. 搜索普通网页并抽取正文。
2. 搜索 GitHub 仓库、Issue、PR 和源码。
3. 搜索小红书、微博、B站、贴吧、抖音和知乎。
4. 从搜索结果继续获取帖子、视频或回答详情。
5. 按需获取评论或回复，补充社区共识与反例。
6. 查询平台能力、登录态、限流和运行状态。
7. 通过 MCP 显式安装、启动、停止或诊断本地 service backend。

## MVP

当前阶段 MVP = **MediaCrawler local-source integration + bridge retirement + MCP enhancement**。

必须完成：

- 定义 MediaCrawler local-source adapter 的最小稳定调用边界。
- 使用固定 commit/version 的 `.source-radar/engines/mediacrawler/source`，不依赖仓库外绝对路径。
- 先以 Bilibili 打通 search/detail/comments/session-status 垂直切片，验证直接源码调用和统一证据转换。
- 将其他中文平台逐步迁移到同一 local-source adapter，不在 source-radar 中重写平台协议。
- 每个平台切换后删除对应旧 bridge 路由，不保留 native 或 bridge fallback。
- 最终删除 `MediaCrawlerBridgeBackend`、`ExternalBridgeProvider("mediacrawler")`、bridge CLI、bridge 端口和相关 health/config/test/docs。
- MCP 能发现 backend/platform capabilities，返回真实结构化状态，并提供不依赖项目路径的可执行管理动作。
- 所有下载、源码、runtime、pid、日志、browser profile 和缓存统一收敛到 `.source-radar/`。

已落地基础：

- `AcquisitionKernel`。
- `BackendRegistry`。
- `BackendLifecycleManager`。
- `EngineInstaller`。
- `.source-radar/` runtime/cache/engine 布局。
- SearXNG 已直接调用 upstream HTTP API，不经 source-radar bridge。
- MCP SSE/stdio transport。
- MCP `manage_backend`。
- Bilibili 独立 native search 已验证 MCP canonical route，但该实现属于需要由 local-source adapter 替换的过渡代码，不作为后续平台模板。

## Inputs and Outputs

输入：

- query、claim、URL、repository。
- platform、page、limit、detail/comments 开关和分页 cursor。
- Cookie、API key、本地浏览器登录态引用。
- backend lifecycle 操作和显式 install/start/stop/status 请求。
- MediaCrawler checkout URL、commit/version 和本地 source metadata。
- nocache、刷新、超时和采集限制。

输出：

- 搜索候选和正文证据。
- 中文平台内容详情、评论和回复。
- 平台内容 ID、作者、发布时间、互动数据和来源 URL。
- 实际 provider/backend/capability 和采集路径。
- backend install/runtime/session 状态。
- 结构化 `status`、`reason`、`message`、`retryable`、`fix`、`warnings`、`diagnostics`。
- MCP 可直接执行的恢复或管理动作。

## Non-goals

- 不重写 MediaCrawler 已有的平台 endpoint、签名、登录、搜索、详情和评论实现。
- 不把 MediaCrawler 整个仓库复制进 source-radar Git 历史；使用本地固定版本 checkout/cache。
- 不同时维护 local-source、native 重写和 HTTP bridge 三套等价路径。
- 不保留 local-source 失败后回退 `BilibiliNativeBackend` 或 MediaCrawler bridge 的隐式 fallback。
- 不为了“功能对等”接入 MediaCrawler 中与 source-radar 研究场景无关的下载、创作者关系或批量存储能力。
- 不在普通只读搜索时擅自安装大型组件。
- 不要求外部 AI 知道项目路径或执行本地 shell。
- 不把人类可读错误文本当作唯一机器协议。
- 不绕过验证码、登录或访问控制。
- 不把 AI 推断伪装成平台返回事实。
- 不把 AI-first 写成安装、生命周期、缓存、参数验证等确定性模块的普遍规则。
- 不恢复旧 `docs/tasks` 流水账和过期 roadmap。

## Seed Tasks

1. **定义 local-source adapter 合约**：识别 MediaCrawler 中可复用的平台 client/crawler、全局 config、Playwright、store 和 import 耦合；定义最小 search/detail/comments/session 调用边界及隔离方案。
2. **Bilibili local-source 垂直切片**：直接复用 MediaCrawler 的 Bilibili client、WBI、Cookie 和评论能力，完成结果转换；同一迁移中删除 `BilibiliNativeBackend` 及其路由，不保留 fallback。
3. **MCP capability/status 增强**：让外部 AI 查询每个平台支持的 search/detail/comments/pagination、是否需要 Cookie、当前 backend 和真实状态；修正仍写着“必须运行 MediaCrawler bridge”的过期 schema。
4. **中文详情与评论 MCP 接口**：在 Bilibili 切片验证后增加克制的统一接口，使搜索结果可继续获取 detail/comments，并返回稳定结构化数据。
5. **其余平台 local-source 迁移**：按实际价值依次迁移小红书、知乎、微博、贴吧、抖音；每完成一个平台就删除对应 bridge 分发和旧测试。
6. **MediaCrawler bridge 彻底退役**：删除 bridge backend/provider/CLI/端口/health/config/engine 启动链和文档，`manage_backend` 改为管理 local-source runtime 所需资源。
7. **MCP 稳定性与可审计性**：统一 timeout、rate-limit、auth、unsupported、cancel、progress、pagination、cache provenance 和实际 backend 诊断；使用真实 MCP transport 黑盒验证。
8. **用户文档同步**：根据真实完成状态重写 README 的架构、工具数量、中文平台路径、安装方式和许可证说明，不提前宣传未完成能力。
