"""Unified crawler engine management."""

import importlib
import json
import os
import pathlib
import signal
import subprocess
import sys
import time
import urllib.request

ENGINES: dict[str, dict] = {
    "trafilatura": {
        "name": "Trafilatura",
        "type": "library",
        "module": "trafilatura",
        "description": "通用网页正文抽取",
        "fix": "uv sync --extra trafilatura",
    },
    "crawl4ai": {
        "name": "Crawl4AI",
        "type": "library",
        "module": "crawl4ai",
        "description": "浏览器渲染动态页面采集",
        "fix": "确认 Python 3.11-3.13，然后: uv run python -m source_radar engine install",
    },
    "mediacrawler": {
        "name": "MediaCrawler",
        "type": "service",
        "local_dir": "external/MediaCrawler",
        "health_url": "http://127.0.0.1:8080/api/health",
        "api_port": 8080,
        "bridge_port": 3003,
        "repo_hint": "https://github.com/NanmiCoder/MediaCrawler",
        "description": "中文社区平台搜索与采集（小红书/微博/B站/贴吧/抖音/知乎）",
        "fix": "git clone https://github.com/NanmiCoder/MediaCrawler external/MediaCrawler",
    },
}


def _root() -> pathlib.Path:
    return pathlib.Path(".")


def _pid_dir() -> pathlib.Path:
    p = _root() / ".source-radar" / "pids"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _pid_path(engine_key: str) -> pathlib.Path:
    return _pid_dir() / f"{engine_key}.pid"


def _check_library(module: str) -> tuple[str, str]:
    try:
        importlib.import_module(module)
        return "ready", "已安装"
    except ImportError:
        return "missing", "未安装"


def _check_service(local_dir: str, health_url: str) -> tuple[str, str]:
    root = _root()
    if not (root / local_dir).exists():
        return "missing", f"目录不存在: {local_dir}"
    try:
        req = urllib.request.Request(health_url)
        urllib.request.urlopen(req, timeout=3)
        return "running", f"服务运行中 ({health_url})"
    except Exception:
        return "stopped", "服务未启动"


def list_engines() -> list[dict]:
    result = []
    for key, cfg in ENGINES.items():
        if cfg["type"] == "library":
            status, detail = _check_library(cfg["module"])
        else:
            status, detail = _check_service(cfg["local_dir"], cfg["health_url"])
        result.append({
            "key": key,
            "name": cfg["name"],
            "type": cfg["type"],
            "status": status,
            "detail": detail,
            "description": cfg["description"],
        })
    return result


def run_engine_list() -> str:
    engines = list_engines()
    lines = []
    max_name = max(len(e["name"]) for e in engines) if engines else 0
    for e in engines:
        icon = {"ready": "OK", "running": "OK", "missing": "--", "stopped": "--"}.get(e["status"], "??")
        lines.append(f"  {icon:2}  {e['name']:<{max_name}}  {e['type']:<8}  {e['detail']}")
    return "\n".join(lines)


def run_engine_status() -> str:
    engines = list_engines()
    lines: list[str] = []
    for e in engines:
        cfg = ENGINES[e["key"]]
        if e["status"] in ("ready", "running"):
            lines.append(f"  OK  {e['name']}: {e['detail']}")
        else:
            lines.append(f"  --  {e['name']}: {e['detail']}")
            lines.append(f"      修复: {cfg['fix']}")
    return "\n".join(lines)


def _python_version_warning() -> str | None:
    if sys.version_info >= (3, 14):
        return (
            f"当前 Python {sys.version_info.major}.{sys.version_info.minor} 太新，"
            "部分依赖（lxml/crawl4ai）在 Windows 上可能无预编译 wheel，"
            "会触发源码编译并要求 MSVC Build Tools。\n"
            "      改用 Python 3.12：\n"
            "        uv python install 3.12\n"
            "        uv python pin 3.12\n"
            "        删除 .venv 后重新运行 uv run python -m source_radar install"
        )
    return None


def _run_required(cmd: list[str], *, cwd: str, env: dict[str, str]) -> None:
    result = subprocess.run(
        cmd, cwd=cwd, env=env,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        output = (result.stdout or "").strip()
        tail = "\n".join(output.splitlines()[-30:])
        raise RuntimeError(tail or f"command failed: {' '.join(cmd)}")


def run_engine_install(
    *, core: bool = True, browser: bool = False, community: bool = False,
) -> str:
    if not core and not browser and not community:
        browser = community = True  # bare `engine install` = all

    lines: list[str] = []
    project_root = str(_root())
    clean_env = os.environ.copy()
    clean_env.pop("VIRTUAL_ENV", None)
    clean_env.pop("UV_ACTIVE", None)

    # Python version check
    warning = _python_version_warning()
    if warning:
        lines.append(f"  WARN {warning}")
        lines.append("  请改用 Python 3.12 后重试。")
        return "\n".join(lines)

    def _try(label: str, fn, fix: str = ""):
        try:
            fn()
            lines.append(f"  OK {label}")
        except Exception as e:
            detail = str(e)[:1200] if str(e) else "unknown"
            lines.append(f"  WARN {label}: {detail}")
            if fix:
                lines.append(f"       重试: {fix}")

    # Always: sync core extras in one shot (Trafilatura + Crawl4AI pip)
    lines.append("安装核心采集库（Trafilatura + Crawl4AI）...")
    _try(
        "核心采集库已安装",
        lambda: _run_required(
            ["uv", "sync", "--extra", "trafilatura", "--extra", "crawl4ai"],
            cwd=project_root, env=clean_env,
        ),
        fix="uv run python -m source_radar engine install",
    )

    # Browser: Playwright Chromium (optional, can fail)
    if browser:
        lines.append("安装 Playwright Chromium 浏览器（动态渲染支持）...")
        _try(
            "Playwright Chromium 已安装",
            lambda: _run_required(
                ["uv", "run", "python", "-m", "playwright", "install", "chromium"],
                cwd=project_root, env=clean_env,
            ),
            fix="uv run python -m source_radar engine install --browser",
        )
    else:
        lines.append("  SKIP Playwright 浏览器（动态渲染不可用，运行 engine install --all 安装）")

    # Community: MediaCrawler (optional, slow due to GitHub clone)
    if community:
        mc_repo = os.environ.get("SOURCE_RADAR_MEDIACRAWLER_REPO",
                                 "https://github.com/NanmiCoder/MediaCrawler")
        mc_dir = _root() / "external" / "MediaCrawler"
        if not mc_dir.exists():
            lines.append("安装 MediaCrawler 社区引擎（GitHub clone，可能较慢）...")
            result = subprocess.run(["git", "clone", mc_repo, str(mc_dir)], check=False)
            if result.returncode != 0:
                lines.append("  WARN clone 失败")
                lines.append(f"      重试: git clone {mc_repo} {mc_dir}")
            else:
                _try(
                    "MediaCrawler 依赖已安装",
                    lambda: _run_required(["uv", "sync"], cwd=str(mc_dir), env=clean_env),
                    fix=f"cd {mc_dir} && uv sync",
                )
        else:
            lines.append("  OK MediaCrawler 目录已存在，跳过 clone")
            _try(
                "MediaCrawler 依赖已更新",
                lambda: _run_required(["uv", "sync"], cwd=str(mc_dir), env=clean_env),
                fix=f"cd {mc_dir} && uv sync",
            )
    else:
        lines.append("  SKIP MediaCrawler（社区采集需运行 engine install --all 安装）")

    return "\n".join(lines)


def _http_ok(url: str, timeout: int = 3) -> bool:
    try:
        req = urllib.request.Request(url)
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception:
        return False


def _wait_http(url: str, timeout_seconds: int = 30) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _http_ok(url):
            return True
        time.sleep(1)
    return False


def _kill_port(port: int) -> None:
    """Kill any process listening on the given port."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, check=False,
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = parts[-1]
                    subprocess.run(["taskkill", "/F", "/PID", pid],
                                   capture_output=True, check=False)
        else:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, check=False,
            )
            for pid_str in result.stdout.strip().splitlines():
                if pid_str:
                    os.kill(int(pid_str), signal.SIGTERM)
    except Exception:
        pass


def run_engine_start(name: str) -> str:
    if name not in ENGINES:
        return f"未知引擎: {name}"

    cfg = ENGINES[name]
    if cfg["type"] != "service":
        return f"{cfg['name']} 是 library 引擎，无需启动"

    api_port = cfg["api_port"]
    bridge_port = cfg["bridge_port"]

    # Already running?
    if _http_ok(cfg["health_url"]):
        lines = [f"{cfg['name']} 已在运行 ({cfg['health_url']})"]
        if _http_ok(f"http://127.0.0.1:{bridge_port}/health"):
            lines.append(f"  桥已运行 (端口 {bridge_port})")
        else:
            lines.append("  桥未运行，请手动: source-radar bridge mediacrawler")
        return "\n".join(lines)

    local_dir = _root() / cfg["local_dir"]
    if not local_dir.exists():
        return f"{cfg['name']} 未安装: {cfg['local_dir']}\n运行: source-radar engine install"

    lines = [f"启动 {cfg['name']}..."]

    # Start API
    api_proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "api.main:app",
         "--host", "127.0.0.1", "--port", str(api_port)],
        cwd=str(local_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Start bridge
    bridge_proc = subprocess.Popen(
        [sys.executable, "-m", "source_radar", "bridge", "mediacrawler",
         "--api-url", f"http://127.0.0.1:{api_port}",
         "--port", str(bridge_port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Write PIDs
    _pid_path(name).write_text(f"{api_proc.pid}\n{bridge_proc.pid}\n")

    # Wait for ready
    if _wait_http(cfg["health_url"], timeout_seconds=45):
        lines.append(f"  OK API 就绪 (端口 {api_port})")
    else:
        lines.append(f"  WARN API 启动超时")

    if _wait_http(f"http://127.0.0.1:{bridge_port}/health", timeout_seconds=10):
        lines.append(f"  OK 桥就绪 (端口 {bridge_port})")
    else:
        lines.append(f"  WARN 桥启动超时，请手动: source-radar bridge mediacrawler")

    return "\n".join(lines)


def run_engine_stop(name: str) -> str:
    if name not in ENGINES:
        return f"未知引擎: {name}"

    cfg = ENGINES[name]
    if cfg["type"] != "service":
        return f"{cfg['name']} 是 library 引擎，无需停止"

    api_port = cfg["api_port"]
    bridge_port = cfg["bridge_port"]

    lines = [f"停止 {cfg['name']}..."]
    _kill_port(api_port)
    _kill_port(bridge_port)

    # Clean up PID file
    pid_file = _pid_path(name)
    if pid_file.exists():
        pid_file.unlink()

    lines.append("  OK 已停止")
    return "\n".join(lines)


def setup_plan() -> dict:
    """Return structured plan of what's needed for initialization.

    Intended for AI agents: read this to know what to ask the user for,
    then apply values with non-interactive commands.
    """
    from .config import load_openai_config
    from .cookie_capture import PLATFORM_COOKIE_CONFIG

    required_inputs: list[dict] = []
    optional_inputs: list[dict] = []

    # AI config (required)
    ai = load_openai_config()
    ai_ok = bool(ai.get("api_key") and ai.get("endpoint") and ai.get("model"))
    if not ai_ok:
        required_inputs.append({
            "key": "ai_config",
            "title": "AI 配置（必选）",
            "required": True,
            "status": "missing",
            "fields": [
                {"name": "api_key", "label": "API key", "secret": True, "required": True},
                {"name": "endpoint", "label": "Endpoint", "secret": False, "required": True, "default": "https://api.openai.com/"},
                {"name": "model", "label": "Model", "secret": False, "required": True, "default": "gpt-4.1-mini"},
            ],
            "apply_command": "uv run python -m source_radar config set-openai --api-key <api_key> --endpoint <endpoint> --model <model>",
            "verify_command": "uv run python -m source_radar config test-ai",
            "reason": "AI 配置是必选项。没有 AI 无法完成 ask/verify 的综合和核验。",
        })
    else:
        required_inputs.append({
            "key": "ai_config",
            "title": "AI 配置（必选）",
            "required": True,
            "status": "configured",
            "details": {"endpoint": ai.get("endpoint", ""), "model": ai.get("model", "")},
        })

    # Cookies (optional)
    from .bridge import load_local_env
    load_local_env()
    cookie_configs = list(PLATFORM_COOKIE_CONFIG.values())
    configured = sum(1 for c in cookie_configs if os.environ.get(c["env"]))
    total = len(cookie_configs)
    if configured < total:
        cookie_vars = [c["env"] for c in cookie_configs if not os.environ.get(c["env"])]
        optional_inputs.append({
            "key": "cookies",
            "title": "中文社区 Cookie（可选）",
            "required": False,
            "status": f"{configured}/{total} 已配置",
            "reason": "只在查询微博/小红书/B站/贴吧/抖音等社区平台时需要",
            "manual_import": {
                "env_file": ".source-radar/local.env",
                "vars": cookie_vars,
            },
            "capture_commands": [
                f"uv run python -m source_radar cookie --platform {k}"
                for k in PLATFORM_COOKIE_CONFIG
            ],
            "set_command_template": "uv run python -m source_radar cookie set --platform <platform> --value \"<cookie>\"",
        })

    # Engines (lightweight: import check only, no HTTP)
    failed: list[str] = []
    for mod, name in [("trafilatura", "Trafilatura"), ("crawl4ai", "Crawl4AI")]:
        try:
            importlib.import_module(mod)
        except ImportError:
            failed.append(name)
    mc_exists = (_root() / "external" / "MediaCrawler").exists()
    if failed:
        optional_inputs.append({
            "key": "engines",
            "title": "核心引擎",
            "required": False,
            "status": "missing",
            "missing": failed,
            "install_command": "uv run python -m source_radar engine install",
        })
    if not mc_exists:
        optional_inputs.append({
            "key": "engines-community",
            "title": "社区采集引擎（可选）",
            "required": False,
            "status": "not-installed",
            "description": "MediaCrawler 未安装。只在需要搜索微博/小红书/B站/贴吧/抖音/知乎时需要。",
            "install_command": "uv run python -m source_radar engine install --all",
        })

    ready = ai_ok

    return {
        "mode": "agent_setup",
        "ready_for_use": ready,
        "required_inputs": required_inputs,
        "optional_inputs": optional_inputs,
        "non_interactive_commands": [
            {
                "command": "uv run python -m source_radar engine install",
                "note": "non-interactive, may take time and may fail due to network",
            },
        ],
        "verify_commands": [
            "uv run python -m source_radar config test-ai",
            "uv run python -m source_radar engine list",
        ],
    }


def run_setup_plan(format: str = "json") -> str:
    data = setup_plan()
    if format == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)
    # Human-readable
    lines = ["=== 安装状态 ==="]
    for item in data["required_inputs"]:
        icon = "OK" if item["status"] == "configured" else "--"
        lines.append(f"  [{icon}] {item['title']}: {item['status']}")
        if item["status"] != "configured" and "reason" in item:
            lines.append(f"      {item['reason']}")
    for item in data["optional_inputs"]:
        lines.append(f"  [可选] {item['title']}: {item['status']}")
        if "reason" in item:
            lines.append(f"      {item.get('reason', '')}")
    return "\n".join(lines)


def run_install_agent() -> str:
    """Non-interactive install for AI agents: core only, no prompts."""
    lines = ["=== 快速安装（Agent 模式 - 仅核心引擎）===", ""]
    lines.append(run_engine_install(core=True, browser=False, community=False))
    lines.append("")
    lines.append(run_setup_plan(format="text"))
    return "\n".join(lines)


def run_install() -> str:
    """Full guided setup: engines + AI config + cookie capture.

    Each step is independent — one failure does not block the rest.
    """
    lines: list[str] = []
    issues: list[str] = []

    # 1. Engines
    lines.append("=== 安装爬虫引擎 ===")
    try:
        lines.append(run_engine_install())
    except Exception as e:
        lines.append(f"  WARN 引擎安装异常: {e}")
        issues.append("引擎安装未完成，可稍后运行 source-radar engine install")

    # 2. AI config
    lines.append("")
    lines.append("=== AI 配置 ===")
    from .config import load_openai_config, save_openai_config

    existing = load_openai_config()
    if existing.get("api_key"):
        lines.append("  OK AI 已配置，跳过")
        lines.append(f"     端点: {existing.get('endpoint', '')}")
        lines.append(f"     模型: {existing.get('model', '')}")
    else:
        try:
            from getpass import getpass
            from .config import fetch_models

            api_key = getpass("API key: ")
            endpoint = input("Endpoint [https://api.openai.com/]: ").strip()
            endpoint = endpoint or "https://api.openai.com/"

            models = fetch_models(endpoint, api_key)
            if models:
                print(f"\n可用模型 ({len(models)} 个):")
                for i, m in enumerate(models):
                    print(f"  [{i}] {m}")
                choice = input("选择模型编号 [默认 0]: ").strip()
                try:
                    model = models[int(choice)]
                except (ValueError, IndexError):
                    model = models[0]
            else:
                print("无法获取模型列表，请手动输入模型名")
                model = input("Model [gpt-4.1-mini]: ").strip()
                model = model or "gpt-4.1-mini"

            save_openai_config(api_key=api_key, endpoint=endpoint, model=model)
            lines.append(f"  OK AI 已配置: {endpoint} / {model}")
        except (EOFError, KeyboardInterrupt):
            lines.append("  SKIP 跳过 AI 配置")
            issues.append("AI 配置未完成，ask/verify 无法使用。请先运行 source-radar config setup")
        except Exception as e:
            lines.append(f"  WARN AI 配置失败: {e}")
            issues.append("AI 配置未完成，ask/verify 无法使用。请先运行 source-radar config setup")

    # 3. Cookies
    lines.append("")
    lines.append("=== Cookie 获取 ===")
    from .bridge import load_local_env
    from .cookie_capture import PLATFORM_COOKIE_CONFIG

    load_local_env()
    existing_cookies = sum(
        1 for cfg in PLATFORM_COOKIE_CONFIG.values()
        if os.environ.get(cfg["env"])
    )
    total = len(PLATFORM_COOKIE_CONFIG)
    if existing_cookies == total:
        lines.append(f"  OK 全部 {total} 个平台 Cookie 已配置，跳过")
    else:
        lines.append(f"  {existing_cookies}/{total} 个平台已配置 Cookie")
        answer = input("  是否现在获取？[Y/n]: ").strip().lower()
        if answer in ("", "y", "yes"):
            try:
                from .cookie_capture import run_cookie
                result = run_cookie()
                lines.append(f"  {result}")
            except (EOFError, KeyboardInterrupt):
                lines.append("  SKIP 跳过 Cookie 获取")
                issues.append("Cookie 未获取，社区平台搜索不可用，可稍后运行 source-radar cookie")
            except Exception as e:
                lines.append(f"  WARN Cookie 获取异常: {e}")
                issues.append("Cookie 获取失败，社区平台搜索不可用，可稍后运行 source-radar cookie --platform <平台>")
        else:
            lines.append(f"  跳过，稍后可用 source-radar cookie 获取")

    # 4. Verification
    lines.append("")
    lines.append("=== 安装验证 ===")
    lines.append(run_engine_status())

    # 5. Summary
    if issues:
        lines.append("")
        lines.append("有些步骤未完成，不影响已配置部分的使用：")
        for i, issue in enumerate(issues, 1):
            lines.append(f"  {i}. {issue}")

    return "\n".join(lines)
