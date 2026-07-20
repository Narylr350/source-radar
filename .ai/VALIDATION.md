# VALIDATION

## Validation Principle

按变更风险选择最小充分验证。文档改动不运行无关全量测试；local-source、backend、lifecycle 和 MCP 行为改动必须验证真实调用路径。

权威证据优先级：

```text
目标源码行为和真实 MCP 调用
> focused integration test
> handler/unit test
> 代理工具或推理
```

不得用直接调用 Python handler、curl 或浏览器代理的结果冒充 MCP 客户端真实调用成功。

## Baseline Checks

提交前：

```powershell
git status --short --branch
git diff --stat
git diff --check
```

文档基线改动至少确认：

- 四份 `.ai` 文件没有相互矛盾。
- README 的过期内容已列入 Seed Task，而未被误写成当前事实。
- `AGENTS.md` 项目方向与 `.ai/PROJECT.md` 一致。

## Local-source Adapter Validation

adapter 合约至少覆盖：

- checkout 不存在。
- metadata/commit 不匹配。
- Python 依赖缺失。
- import/config 初始化失败。
- browser/session 缺失。
- Cookie 缺失或过期。
- search/detail/comments 成功。
- no-results。
- pagination/cursor。
- timeout、rate-limit 和平台返回错误。
- MediaCrawler 输出到统一 evidence model 的映射。
- 调用结束后的 global/config/session 隔离。
- 不访问 `external/` 或用户自定义绝对 checkout。

## Bilibili Migration Validation

Bilibili local-source 切片至少验证：

- 实际调用 MediaCrawler Bilibili client/crawler，而不是 source-radar 自建 endpoint。
- 搜索使用上游已有 WBI/session/cookie 逻辑。
- 视频详情映射。
- 评论和评论分页映射。
- Cookie/session 状态。
- rate-limit/auth 错误分类。
- MCP 搜索、详情、评论真实 transport 调用。
- 删除 `BilibiliNativeBackend` 后无 import、路由、缓存命名或测试残留。
- local-source 失败不会回退 native 或 HTTP bridge。

建议 focused tests：

```powershell
.venv\Scripts\python.exe -m unittest tests.test_bilibili_backend tests.test_mcp_server -v
```

迁移时应按新合约改写测试文件和名称，不能让旧测试继续保护 native 实现。

## MCP Validation

MCP 改动至少覆盖：

- `tools/list` schema 和 description。
- stdio transport 初始化和连续调用。
- SSE/stream transport 如受影响则单独验证。
- `source_status` 的 capability/backend/session 状态。
- `manage_backend` 的 status/start/stop/install。
- install 不会被普通 read/search 隐式触发。
- 外部 AI 获得的修复动作不依赖项目绝对路径。
- 搜索结果标明实际 backend 和 cache provenance。
- timeout、auth、rate-limit、unsupported、not-installed 的结构化结果。

当前核心 MCP 回归：

```powershell
.venv\Scripts\python.exe -m unittest tests.test_mcp_server tests.test_mcp_stdio tests.test_mcp_autostart -v
```

## Lifecycle and Installer Validation

lifecycle 至少覆盖：

- ready。
- start failed。
- non-zero exit。
- cooling_down。
- idle timeout。
- autostart disabled。
- status 与实际 backend 一致。

installer 至少覆盖：

- `.source-radar/downloads` 和 `.source-radar/engines`。
- 固定 commit/version metadata。
- 下载复用、repair 和可诊断失败。
- 不提交源码、凭据或运行态。
- 不从 `external/` 进入运行路径。
- 普通查询不会隐式 install。

```powershell
.venv\Scripts\python.exe -m unittest tests.test_engine_installer tests.test_backend_registry tests.test_lifecycle_ensure_ready -v
```

## Bridge Retirement Validation

每删除一个 bridge 路径必须验证：

- 语义搜索无运行调用方。
- CLI 不再注册旧入口。
- MCP schema 不再宣传 bridge。
- engine/status 不再检查 bridge port。
- provider/config/health/cache 命名已迁移。
- 旧测试删除或改写。
- local-source 失败明确报错，不回退 bridge。

最终退役检查应覆盖：

```text
MediaCrawlerBridgeBackend
ExternalBridgeProvider("mediacrawler")
source-radar bridge mediacrawler
SOURCE_RADAR_MEDIACRAWLER_ENDPOINT
bridge_port 3003
source-radar.bridge.v1
```

## Full Regression

只有跨模块架构变更或提交前需要时运行：

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

记录实际执行命令和结果，不把未执行验证写成通过。
