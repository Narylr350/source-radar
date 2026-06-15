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
        "fix": "uv run python -m source_radar engine install",
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
        "fix": "uv run python -m source_radar engine install --community",
    },
    "searxng": {
        "name": "SearXNG",
        "type": "service",
        "local_dir": "external/searxng",
        "health_url": "http://127.0.0.1:8888/",
        "api_port": 8888,
        "bridge_port": 3004,
        "repo": "https://github.com/searxng/searxng",
        "description": "元搜索引擎，聚合多个搜索源（替代直接 Bing 抓取）",
        "fix": "uv run python -m source_radar engine install --searxng",
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


def _check_searxng_engine(cfg: dict) -> tuple[str, str]:
    """Check SearXNG status: upstream health + bridge health."""
    upstream_url = f"http://127.0.0.1:{cfg['api_port']}"
    health = _searxng_health_check(upstream_url)
    bridge_ok = _http_ok(f"http://127.0.0.1:{cfg['bridge_port']}/health")
    searxng_dir = _root() / cfg["local_dir"]

    if health["status"] == "ok" and bridge_ok:
        return "running", f"SearXNG 运行中 (upstream + 桥 端口 {cfg['bridge_port']})"
    if health["status"] == "ok":
        return "stopped", f"SearXNG upstream 运行中，桥未启动 (端口 {cfg['bridge_port']})"
    if searxng_dir.exists():
        return "stopped", f"SearXNG 已安装 ({cfg['local_dir']})，未启动"
    return "missing", "SearXNG 未安装"


def list_engines() -> list[dict]:
    result = []
    for key, cfg in ENGINES.items():
        if cfg["type"] == "library":
            status, detail = _check_library(cfg["module"])
        elif key == "searxng":
            status, detail = _check_searxng_engine(cfg)
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
    # Check MediaCrawler Windows no-console patch
    if sys.platform == "win32":
        mc_dir = _root() / "external" / "MediaCrawler"
        if mc_dir.exists() and not _check_mediacrawler_patch(mc_dir):
            lines.append("  WARN MediaCrawler Windows patch 未应用，采集可能弹 uv 窗口")
            lines.append("      修复: uv run python -m source_radar engine install --community")
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
    *, core: bool = True, browser: bool = False, community: bool = False, searxng: bool = False,
) -> str:
    if not core and not browser and not community and not searxng:
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

    # Always: sync core extras in one shot (Trafilatura + Crawl4AI + MCP pip)
    lines.append("安装核心采集库（Trafilatura + Crawl4AI + MCP）...")
    _try(
        "核心采集库已安装",
        lambda: _run_required(
            ["uv", "sync", "--extra", "trafilatura", "--extra", "crawl4ai", "--extra", "mcp"],
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
                    fix="uv run python -m source_radar engine install --community",
                )
                lines.append("  " + _patch_mediacrawler_no_console(mc_dir))
        else:
            lines.append("  OK MediaCrawler 目录已存在，跳过 clone")
            _try(
                "MediaCrawler 依赖已更新",
                lambda: _run_required(["uv", "sync"], cwd=str(mc_dir), env=clean_env),
                fix="uv run python -m source_radar engine install --community",
            )
            lines.append("  " + _patch_mediacrawler_no_console(mc_dir))
    else:
        lines.append("  SKIP MediaCrawler（社区采集需运行 engine install --all 安装）")

    # SearXNG: git clone + pip install
    if searxng:
        lines.append("")
        lines.append(run_engine_install_searxng())
    else:
        lines.append("  SKIP SearXNG（运行 engine install --searxng 安装）")

    return "\n".join(lines)


def _background_python(root: pathlib.Path) -> str:
    """Return path to pythonw.exe. MUST exist in root/.venv — no fallback."""
    if sys.platform != "win32":
        return sys.executable
    pyw = root / ".venv" / "Scripts" / "pythonw.exe"
    if pyw.exists():
        return str(pyw)
    raise RuntimeError(
        f"找不到后台 Python: {pyw}\n"
        f"请先运行: cd {root} && uv sync"
    )


def _patch_mediacrawler_no_console(mc_dir: pathlib.Path) -> str:
    """Patch MediaCrawler's crawler_manager to use pythonw.exe instead of uv run.

    Idempotent: skips if already patched or if target file not found.
    """
    target = mc_dir / "api" / "services" / "crawler_manager.py"
    if not target.exists():
        return "SKIP MediaCrawler patch: crawler_manager.py not found"

    text = target.read_text(encoding="utf-8")

    old_cmd = '["uv", "run", "python", "main.py"]'
    if old_cmd not in text:
        if "_windows_background_python" in text:
            return "OK MediaCrawler patch already applied"
        return "SKIP MediaCrawler patch: uv run pattern not found (source may have changed)"

    helper = '''
def _windows_background_python():
    import pathlib, sys
    if sys.platform != "win32":
        return ["uv", "run", "python"]
    pyw = pathlib.Path(__file__).resolve().parents[2] / ".venv" / "Scripts" / "pythonw.exe"
    if pyw.exists():
        return [str(pyw)]
    raise RuntimeError(f"找不到 MediaCrawler 后台 Python: {pyw}")
'''.lstrip("\n")

    # Insert helper after the last import line before the class definition
    marker = "class CrawlerManager:"
    if marker in text:
        text = text.replace(marker, helper + "\n" + marker)
    else:
        return "SKIP MediaCrawler patch: class CrawlerManager not found"

    text = text.replace(old_cmd, '[*_windows_background_python(), "main.py"]')
    target.write_text(text, encoding="utf-8")
    return "OK MediaCrawler Windows no-console patch applied"


def _check_mediacrawler_patch(mc_dir: pathlib.Path) -> bool:
    target = mc_dir / "api" / "services" / "crawler_manager.py"
    if not target.exists():
        return False
    text = target.read_text(encoding="utf-8")
    return "_windows_background_python" in text


def _hidden_spawn_opts() -> dict:
    if sys.platform != "win32":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW | subprocess.STARTF_USESTDHANDLES
    si.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": si,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }


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


def _searxng_health_check(upstream_url: str = "http://127.0.0.1:8888") -> dict:
    """Check SearXNG upstream health: reachable + JSON format enabled."""
    import urllib.error
    test_url = f"{upstream_url}/search?q=test&format=json"
    try:
        req = urllib.request.Request(test_url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and "results" in data:
                return {"status": "ok", "reason": "ready", "message": "SearXNG upstream 可访问，JSON 格式已启用"}
            return {"status": "error", "reason": "json-disabled",
                    "message": "SearXNG 返回了非 JSON 响应",
                    "fix": "在 SearXNG settings.yml 中启用 JSON: search.formats: [html, json]"}
    except urllib.error.HTTPError as e:
        return {"status": "error", "reason": f"http-{e.code}",
                "message": f"SearXNG 返回 HTTP {e.code}",
                "fix": "检查 SearXNG 是否正常运行: uv run python -m source_radar engine status searxng"}
    except urllib.error.URLError as e:
        return {"status": "error", "reason": "unreachable",
                "message": f"SearXNG 不可访问: {e.reason}",
                "fix": "启动 SearXNG: uv run python -m source_radar engine start searxng"}
    except json.JSONDecodeError:
        return {"status": "error", "reason": "json-disabled",
                "message": "SearXNG 返回了非 JSON 响应",
                "fix": "在 SearXNG settings.yml 中启用 JSON: search.formats: [html, json]"}


def run_engine_install_searxng() -> str:
    """Install SearXNG via git clone, virtualenv, and pip."""
    lines = ["安装 SearXNG..."]
    searxng_dir = _root() / "external" / "searxng"
    venv_dir = searxng_dir / ".venv"
    clean_env = os.environ.copy()
    clean_env.pop("VIRTUAL_ENV", None)
    clean_env.pop("UV_ACTIVE", None)

    # 1. Clone repo (with sparse-checkout on Windows to avoid colon-in-filename issues)
    if searxng_dir.exists():
        lines.append("  OK SearXNG 目录已存在")
    else:
        lines.append("  克隆 SearXNG 仓库...")
        if sys.platform == "win32":
            # Windows: --no-checkout + sparse to avoid files with colons in names
            result = subprocess.run(
                ["git", "clone", "--no-checkout", ENGINES["searxng"]["repo"], str(searxng_dir)],
                check=False, capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                subprocess.run(
                    ["git", "-C", str(searxng_dir), "sparse-checkout", "init", "--cone"],
                    check=False, capture_output=True, timeout=30,
                )
                subprocess.run(
                    ["git", "-C", str(searxng_dir), "sparse-checkout", "set", "searx", "client"],
                    check=False, capture_output=True, timeout=30,
                )
                subprocess.run(
                    ["git", "-C", str(searxng_dir), "checkout", "-f", "HEAD",
                     "--", "searx", "client", "setup.py", "requirements.txt",
                     "requirements-dev.txt", "requirements-server.txt", "README.rst"],
                    check=False, capture_output=True, timeout=30,
                )
        else:
            result = subprocess.run(
                ["git", "clone", ENGINES["searxng"]["repo"], str(searxng_dir)],
                check=False, capture_output=True, text=True, timeout=120,
            )
        if result.returncode != 0:
            lines.append(f"  WARN clone 失败: {result.stderr[:200]}")
            lines.append(f"       重试: git clone {ENGINES['searxng']['repo']} {searxng_dir}")
            return "\n".join(lines)
        lines.append("  OK 仓库已克隆")

    # 2. Create venv
    if not venv_dir.exists():
        lines.append("  创建虚拟环境...")
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=False, capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            lines.append(f"  WARN venv 创建失败: {result.stderr[:200]}")
            return "\n".join(lines)
        lines.append("  OK 虚拟环境已创建")

    # 3. Get venv python
    if sys.platform == "win32":
        venv_py = str(venv_dir / "Scripts" / "python.exe")
    else:
        venv_py = str(venv_dir / "bin" / "python")

    # 4. Install dependencies
    lines.append("  安装依赖...")
    for pkg in ["pip", "setuptools", "wheel", "pyyaml", "msgspec", "typing-extensions", "pybind11"]:
        subprocess.run(
            [venv_py, "-m", "pip", "install", "-U", pkg],
            check=False, capture_output=True, text=True, timeout=120,
            env=clean_env,
        )

    # 5. Install SearXNG in editable mode
    lines.append("  安装 SearXNG...")
    result = subprocess.run(
        [venv_py, "-m", "pip", "install", "--use-pep517", "--no-build-isolation", "-e", "."],
        cwd=str(searxng_dir),
        check=False, capture_output=True, text=True, timeout=300,
        env=clean_env,
    )
    if result.returncode == 0:
        lines.append("  OK SearXNG 已安装")
    else:
        lines.append(f"  WARN 安装失败: {result.stderr[:300]}")
        lines.append(f"       重试: cd {searxng_dir} && pip install --use-pep517 --no-build-isolation -e .")
        return "\n".join(lines)

    # 6. Generate settings.yml with JSON enabled
    _ensure_searxng_settings(searxng_dir)
    lines.append("  OK settings.yml 已生成 (JSON 格式已启用)")

    return "\n".join(lines)


def _ensure_searxng_settings(searxng_dir: pathlib.Path) -> None:
    """Generate or patch SearXNG settings.yml to enable JSON format."""
    settings_path = searxng_dir / "searx" / "settings.yml"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    if settings_path.exists():
        # Patch existing settings to ensure JSON is enabled
        content = settings_path.read_text(encoding="utf-8")
        # Check if JSON is already in the active formats list (not just comments)
        if "    - json" not in content:
            if "formats:" in content and "    - html" in content:
                content = content.replace("    - html\n", "    - html\n    - json\n", 1)
            settings_path.write_text(content, encoding="utf-8")
        return

    # Generate minimal settings.yml
    settings = """\
# SearXNG settings for source-radar
use_default_settings: true

search:
  safe_search: 0
  autocomplete: ""
  formats:
    - html
    - json

server:
  port: 8888
  bind_address: "127.0.0.1"
  secret_key: "source-radar-local-dev-key"
  limiter: false
  image_proxy: false

ui:
  default_theme: simple
"""
    settings_path.write_text(settings, encoding="utf-8")


def _searxng_start_upstream() -> tuple[bool, str]:
    """Start SearXNG via Python venv. Returns (success, message)."""
    cfg = ENGINES["searxng"]
    api_port = cfg["api_port"]
    searxng_dir = _root() / cfg["local_dir"]
    venv_dir = searxng_dir / ".venv"

    if not searxng_dir.exists():
        return False, f"SearXNG 未安装: {cfg['local_dir']}"

    if _http_ok(f"http://127.0.0.1:{api_port}/"):
        return True, f"SearXNG 已在运行 (端口 {api_port})"

    if not venv_dir.exists():
        return False, "虚拟环境不存在，请运行: uv run python -m source_radar engine install --searxng"

    # Get venv python
    if sys.platform == "win32":
        venv_py = str(venv_dir / "Scripts" / "python.exe")
    else:
        venv_py = str(venv_dir / "bin" / "python")

    # Ensure settings.yml exists with JSON enabled
    _ensure_searxng_settings(searxng_dir)
    settings_path = str((searxng_dir / "searx" / "settings.yml").resolve())

    # Create a launcher script that mocks pwd (Windows) and starts SearXNG
    launcher = searxng_dir / "_start_searxng.py"
    launcher.write_text(
        "import sys, os\n"
        "if sys.platform == 'win32':\n"
        "    import types\n"
        "    pwd = types.ModuleType('pwd')\n"
        "    pwd.getpwnam = lambda x: None\n"
        "    sys.modules['pwd'] = pwd\n"
        "os.environ['SEARXNG_SETTINGS_PATH'] = r'" + settings_path + "'\n"
        "from searx.webapp import app\n"
        "app.run(host='127.0.0.1', port=" + str(api_port) + ", debug=False)\n",
        encoding="utf-8",
    )

    # Start SearXNG
    spawn_opts = _hidden_spawn_opts()
    proc = subprocess.Popen(
        [venv_py, str(launcher)],
        cwd=str(searxng_dir),
        env={**os.environ, "SEARXNG_SETTINGS_PATH": settings_path},
        **spawn_opts,
    )
    _pid_path("searxng").write_text(f"{proc.pid}\n")
    return True, f"SearXNG 进程已启动 (PID {proc.pid})"


def _searxng_stop_upstream() -> None:
    """Stop SearXNG process."""
    pid_file = _pid_path("searxng")
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip().split("\n")[0])
            os.kill(pid, signal.SIGTERM)
        except (ValueError, ProcessLookupError, OSError):
            pass
    # Also kill by port
    _kill_port(ENGINES["searxng"]["api_port"])


def _start_searxng(cfg: dict, bridge_port: int) -> str:
    """Start SearXNG: upstream process + source-radar bridge."""
    upstream_url = f"http://127.0.0.1:{cfg['api_port']}"
    bridge_running = _http_ok(f"http://127.0.0.1:{bridge_port}/health")
    upstream_health = _searxng_health_check(upstream_url)

    if upstream_health["status"] == "ok" and bridge_running:
        return f"SearXNG 已完整运行\n  Upstream: {upstream_url}\n  桥: 端口 {bridge_port}"

    lines = ["启动 SearXNG..."]
    searxng_dir = _root() / cfg["local_dir"]

    # 1. Start upstream
    if upstream_health["status"] != "ok":
        if not searxng_dir.exists():
            lines.append(f"  WARN SearXNG 未安装: {cfg['local_dir']}")
            lines.append("       运行: uv run python -m source_radar engine install --searxng")
            return "\n".join(lines)
        ok, msg = _searxng_start_upstream()
        lines.append(f"  {'OK' if ok else 'WARN'} {msg}")
        if ok:
            if _wait_http(f"{upstream_url}/", timeout_seconds=30):
                lines.append(f"  OK SearXNG upstream 就绪 (端口 {cfg['api_port']})")
                health = _searxng_health_check(upstream_url)
                if health["status"] != "ok":
                    lines.append(f"  WARN {health['message']}")
                    lines.append(f"       {health.get('fix', '')}")
            else:
                lines.append("  WARN SearXNG upstream 启动超时")
                lines.append("       检查日志或手动启动")

    # 2. Start bridge
    if not bridge_running:
        spawn_opts = _hidden_spawn_opts()
        sr_py = _background_python(_root())
        bridge_proc = subprocess.Popen(
            [sr_py, "-m", "source_radar", "bridge", "searxng",
             "--upstream-url", upstream_url,
             "--port", str(bridge_port)],
            env=os.environ.copy(),
            **spawn_opts,
        )
        _pid_path("searxng-bridge").write_text(f"{bridge_proc.pid}\n")
        if _wait_http(f"http://127.0.0.1:{bridge_port}/health", timeout_seconds=10):
            lines.append(f"  OK 桥就绪 (端口 {bridge_port})")
        else:
            lines.append(f"  WARN 桥启动超时，请手动: source-radar bridge searxng --upstream-url {upstream_url}")

    # 3. Auto-write config
    try:
        from .cli import run_config_set_provider
        run_config_set_provider("searxng", endpoint=f"http://127.0.0.1:{bridge_port}", command="")
        lines.append(f"  OK 配置已写入: searxng endpoint=http://127.0.0.1:{bridge_port}")
    except Exception:
        lines.append(f"  WARN 配置写入失败，请手动: source-radar config set-provider --name searxng --endpoint http://127.0.0.1:{bridge_port}")

    return "\n".join(lines)


def run_engine_start(name: str) -> str:
    if name not in ENGINES:
        return f"未知引擎: {name}"

    cfg = ENGINES[name]
    if cfg["type"] != "service":
        return f"{cfg['name']} 是 library 引擎，无需启动"

    bridge_port = cfg["bridge_port"]

    # SearXNG uses a local checkout and Python virtualenv for upstream.
    if name == "searxng":
        return _start_searxng(cfg, bridge_port)

    api_port = cfg["api_port"]

    local_dir = _root() / cfg["local_dir"]

    # Determine what needs starting
    api_running = _http_ok(cfg["health_url"])
    bridge_running = _http_ok(f"http://127.0.0.1:{bridge_port}/health")

    if api_running and bridge_running:
        return f"{cfg['name']} 已完整运行\n  API: {cfg['health_url']}\n  桥: 端口 {bridge_port}"

    if not local_dir.exists() and not api_running:
        return f"{cfg['name']} 未安装: {cfg['local_dir']}\n运行: source-radar engine install"

    lines = [f"启动 {cfg['name']}..."]
    spawn_opts = _hidden_spawn_opts()
    media_py = _background_python(local_dir)
    sr_py = _background_python(_root())

    api_proc = None
    bridge_proc = None

    if not api_running:
        api_proc = subprocess.Popen(
            [media_py, "-m", "uvicorn", "api.main:app",
             "--host", "127.0.0.1", "--port", str(api_port)],
            cwd=str(local_dir),
            env=os.environ.copy(),
            **spawn_opts,
        )

    if not bridge_running:
        bridge_proc = subprocess.Popen(
            [sr_py, "-m", "source_radar", "bridge", "mediacrawler",
             "--api-url", f"http://127.0.0.1:{api_port}",
             "--port", str(bridge_port)],
            env=os.environ.copy(),
            **spawn_opts,
        )

    pids = []
    if api_proc:
        pids.append(str(api_proc.pid))
    if bridge_proc:
        pids.append(str(bridge_proc.pid))
    if pids:
        _pid_path(name).write_text("\n".join(pids) + "\n")

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

    lines = [f"停止 {cfg['name']}..."]

    # SearXNG: stop upstream process + bridge
    if name == "searxng":
        _searxng_stop_upstream()
        _kill_port(cfg["bridge_port"])
        pid_file = _pid_path("searxng-bridge")
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip().split("\n")[0])
                os.kill(pid, signal.SIGTERM)
            except (ValueError, ProcessLookupError, OSError):
                pass
            pid_file.unlink()
        lines.append("  OK 已停止")
        return "\n".join(lines)

    api_port = cfg["api_port"]
    bridge_port = cfg["bridge_port"]
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
    from .config import load_openai_config, load_provider_configs
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

    # SearXNG bridge (required for real web search)
    provider_configs = load_provider_configs()
    searxng_endpoint = (
        os.environ.get("SOURCE_RADAR_SEARXNG_ENDPOINT", "")
        or provider_configs.get("searxng", {}).get("endpoint", "")
    )
    # Check bridge health at configured endpoint or auto-discovered port 3004
    searxng_bridge_url = searxng_endpoint or "http://127.0.0.1:3004"
    searxng_bridge_running = _http_ok(f"{searxng_bridge_url.rstrip('/')}/health", timeout=1)
    searxng_ok = searxng_bridge_running
    if searxng_ok:
        required_inputs.append({
            "key": "searxng_bridge",
            "title": "SearXNG 搜索桥（必选）",
            "required": True,
            "status": "configured",
            "details": {
                "endpoint": searxng_endpoint or "http://127.0.0.1:3004",
                "auto_discovered": str(not bool(searxng_endpoint) and searxng_bridge_running).lower(),
            },
        })
    else:
        required_inputs.append({
            "key": "searxng_bridge",
            "title": "SearXNG 搜索桥（必选）",
            "required": True,
            "status": "missing",
            "reason": "真实 websearch 是基础能力；没有 SearXNG bridge 时只能依赖不稳定的搜索页抓取或离线 fixture。",
            "fields": [
                {"name": "upstream_url", "label": "SearXNG upstream URL", "secret": False, "required": True, "default": "http://127.0.0.1:8888"},
                {"name": "endpoint", "label": "source-radar bridge endpoint", "secret": False, "required": True, "default": "http://127.0.0.1:3004"},
            ],
            "run_command": "uv run python -m source_radar bridge searxng --upstream-url http://127.0.0.1:8888 --port 3004",
            "apply_command": "uv run python -m source_radar config set-provider --name searxng --endpoint http://127.0.0.1:3004",
            "verify_command": "uv run python -m source_radar probe --source searxng --query \"张雪峰 去世 证券时报\"",
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
        except Exception:
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
            "install_command": "uv run python -m source_radar engine install --community",
        })

    ready = ai_ok and searxng_ok

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
    lines.append("核心引擎已安装。如需增强功能，推荐继续安装：")
    lines.append("  uv run python -m source_radar engine install --browser     # 动态页面渲染")
    lines.append("  uv run python -m source_radar engine install --community  # 中文社区平台搜索")
    lines.append("  uv run python -m source_radar engine install --all        # 全部")
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
