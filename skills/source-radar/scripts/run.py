#!/usr/bin/env python3
"""Source-radar CLI wrapper for Claude Code skill.

Auto-locates the project root and runs commands there.
Runs environment readiness checks before ask/verify.
"""

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path


def _find_project_root() -> Path:
    env_home = os.environ.get("SOURCE_RADAR_HOME")
    if env_home and (Path(env_home) / "pyproject.toml").exists():
        return Path(env_home)
    p = Path.cwd()
    while p != p.parent:
        if (p / "pyproject.toml").exists():
            return p
        p = p.parent
    for c in [
        Path.home() / "source-radar",
        Path.home() / "projects" / "source-radar",
    ]:
        if (c / "pyproject.toml").exists():
            return c
    return Path.cwd()


PROJECT_ROOT = _find_project_root()
SR = ["uv", "run", "python", "-m", "source_radar"]

COMMUNITY_KEYWORDS = (
    "xiaohongshu", "rednote", "xhs", "weibo", "bilibili", "b站", "bili",
    "tieba", "douyin", "dy", "zhihu", "经验", "实测", "案例", "翻车",
)


def _run(cmd, **kwargs):
    kwargs.setdefault("cwd", str(PROJECT_ROOT))
    return subprocess.run(cmd, check=False, **kwargs)


def _run_capture(cmd) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(PROJECT_ROOT),
                          capture_output=True, text=True, check=False)


def _needs_community(query: str) -> bool:
    lowered = query.lower()
    return any(kw in lowered for kw in COMMUNITY_KEYWORDS)


def _has_pyproject() -> bool:
    return (PROJECT_ROOT / "pyproject.toml").exists()


def _has_uv() -> bool:
    try:
        subprocess.run(["uv", "--version"], capture_output=True, check=False)
        return True
    except FileNotFoundError:
        return False


def _cli_runnable() -> bool:
    result = _run_capture([*SR, "--help"])
    return result.returncode == 0


def _ai_configured() -> bool:
    # source-radar looks for config at SOURCE_RADAR_CONFIG_DIR or default paths.
    # Also check the project-local .source-radar which install creates.
    for config_dir in [
        os.environ.get("SOURCE_RADAR_CONFIG_DIR"),
        str(PROJECT_ROOT / ".source-radar"),
    ]:
        if not config_dir:
            continue
        env = os.environ.copy()
        env["SOURCE_RADAR_CONFIG_DIR"] = config_dir
        result = subprocess.run(
            [*SR, "config", "show"],
            cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, check=False,
            env=env,
        )
        try:
            data = json.loads(result.stdout)
            if data.get("openai", {}).get("configured", False):
                return True
        except Exception:
            continue
    return False


def _cookie_count() -> tuple[int, int]:
    result = _run_capture([*SR, "engine", "list"])
    # Parse engine list to see which platforms have cookies
    # Simpler: check local.env directly
    env_file = PROJECT_ROOT / ".source-radar" / "local.env"
    if not env_file.exists():
        return 0, 1
    cookie_envs = ["SOURCE_RADAR_XHS_COOKIE", "SOURCE_RADAR_WEIBO_COOKIE",
                   "SOURCE_RADAR_BILI_COOKIE", "SOURCE_RADAR_TIEBA_COOKIE",
                   "SOURCE_RADAR_DOUYIN_COOKIE"]
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key in cookie_envs:
            os.environ[key] = "1"
    configured = sum(1 for env in cookie_envs if os.environ.get(env))
    return configured, len(cookie_envs)


# ── doctor ──────────────────────────────────────────────────────


def cmd_doctor() -> str:
    """Full environment check, returns status lines + next steps."""
    lines: list[str] = []
    next_steps: list[str] = []
    blocking: list[str] = []
    non_blocking: list[str] = []

    # Project
    if _has_pyproject():
        lines.append(f"  [OK] 项目目录: {PROJECT_ROOT}")
    else:
        lines.append(f"  [--] 找不到项目目录")
        blocking.append("git clone https://github.com/Narylr350/source-radar.git && cd source-radar")
        return _format_doctor(lines, blocking, non_blocking, next_steps)

    # uv
    if _has_uv():
        lines.append("  [OK] uv 可用")
    else:
        lines.append("  [--] uv 未安装")
        blocking.append("安装 uv: https://docs.astral.sh/uv/")
        return _format_doctor(lines, blocking, non_blocking, next_steps)

    # Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    if sys.version_info >= (3, 11):
        lines.append(f"  [OK] Python {py_ver}")
    else:
        lines.append(f"  [--] Python {py_ver} (需要 >= 3.11)")
        blocking.append("安装 Python >= 3.11: https://python.org")
        return _format_doctor(lines, blocking, non_blocking, next_steps)

    # CLI runnable
    if _cli_runnable():
        lines.append("  [OK] source_radar CLI 可运行")
    else:
        lines.append("  [--] source_radar CLI 无法运行")
        blocking.append("cd source-radar && uv sync --extra dynamic && uv run crawl4ai-setup")
        return _format_doctor(lines, blocking, non_blocking, next_steps)

    # AI config
    if _ai_configured():
        lines.append("  [OK] AI 已配置")
    else:
        lines.append("  [WARN] AI 未配置")
        blocking.append("uv run python -m source_radar config setup")
        blocking.append("uv run python -m source_radar config test-ai")

    # Cookies
    configured, total = _cookie_count()
    if configured == total:
        lines.append(f"  [OK] Cookie: {total}/{total} 平台已配置")
    elif configured > 0:
        lines.append(f"  [WARN] Cookie: {configured}/{total} 平台已配置")
        missing = total - configured
        non_blocking.append(f"还有 {missing} 个平台未配置 Cookie，社区平台搜索部分不可用")
        next_steps.append("uv run python -m source_radar cookie")
    else:
        lines.append(f"  [--] Cookie: 0/{total} 平台未配置")
        non_blocking.append("社区平台搜索（小红书/微博/B站/贴吧/抖音）需要 Cookie")
        next_steps.append("uv run python -m source_radar cookie")

    # Engines
    result = _run_capture([*SR, "engine", "list"])
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "Crawl4AI" in line or "Trafilatura" in line or "MediaCrawler" in line:
            if "OK" in line or "OK" in line:
                lines.append(f"  [OK] {line[6:]}" if len(line) > 6 else f"  [OK] {line}")
            else:
                lines.append(f"  [WARN] {line[6:]}" if len(line) > 6 else f"  [WARN] {line}")
                if "MediaCrawler" in line:
                    non_blocking.append("MediaCrawler 未就绪，社区平台搜索不可用")
                    next_steps.append("uv run python -m source_radar engine install")
                    next_steps.append("uv run python -m source_radar engine start mediacrawler")

    return _format_doctor(lines, blocking, non_blocking, next_steps)


def _format_doctor(lines, blocking, non_blocking, next_steps):
    out = ["source-radar 环境检查：", ""]
    out.extend(lines)

    if blocking:
        out.append("")
        out.append("缺少必要配置，请先运行：")
        for s in blocking:
            out.append(f"  {s}")

    if non_blocking:
        out.append("")
        for s in non_blocking:
            out.append(f"注意: {s}")

    if next_steps and not blocking:
        out.append("")
        out.append("可选操作：")
        for s in next_steps:
            out.append(f"  {s}")

    return "\n".join(out)


# ── guard ────────────────────────────────────────────────────────


def _check_blocking() -> bool:
    """Lightweight check before ask/verify. Returns True if ok to proceed."""
    if not _has_pyproject() or not _has_uv():
        return False
    if sys.version_info < (3, 11):
        return False
    if not _ai_configured():
        return False
    return True


def _ready_guard() -> bool:
    if _check_blocking():
        return True
    print(cmd_doctor())
    return False


# ── commands ─────────────────────────────────────────────────────


def cmd_start():
    print("Starting MediaCrawler...")
    _run([*SR, "engine", "start", "mediacrawler"])


def cmd_stop():
    _run([*SR, "engine", "stop", "mediacrawler"])


def cmd_ask(query: str):
    if not _ready_guard():
        return
    args = [*SR, "ask", query, "--format", "markdown"]
    if _needs_community(query):
        args.append("--local-services")
    _run(args)


def cmd_verify(claim: str):
    if not _ready_guard():
        return
    args = [*SR, "verify", claim, "--format", "markdown", "--progress"]
    if _needs_community(claim):
        args.append("--local-services")
    _run(args)


def cmd_status():
    _run([*SR, "engine", "list"])


def cmd_cookie():
    _run([*SR, "cookie"])


# ── main ─────────────────────────────────────────────────────────


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: run.py <start|stop|ask|verify|status|cookie|doctor> [args...]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "start":
        cmd_start()
    elif action == "stop":
        cmd_stop()
    elif action == "ask":
        cmd_ask(" ".join(sys.argv[2:]))
    elif action == "verify":
        cmd_verify(" ".join(sys.argv[2:]))
    elif action == "status":
        cmd_status()
    elif action == "cookie":
        cmd_cookie()
    elif action == "doctor":
        print(cmd_doctor())
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
