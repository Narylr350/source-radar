#!/usr/bin/env python3
"""Source-radar CLI wrapper for Claude Code skill.

Auto-locates the project root and runs commands there.
Handles service lifecycle: start/stop MediaCrawler as needed.
"""

import os
import subprocess
import sys
from pathlib import Path


def _find_project_root() -> Path:
    """Locate source-radar project root.

    Checks:
    1. SOURCE_RADAR_HOME env var
    2. Walk up from CWD looking for pyproject.toml
    3. Common install directories
    """
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


def _needs_community(query: str) -> bool:
    lowered = query.lower()
    return any(kw in lowered for kw in COMMUNITY_KEYWORDS)


def cmd_start():
    print("Starting MediaCrawler...")
    _run([*SR, "engine", "start", "mediacrawler"])


def cmd_stop():
    _run([*SR, "engine", "stop", "mediacrawler"])


def cmd_ask(query: str):
    args = [*SR, "ask", query, "--format", "markdown"]
    if _needs_community(query):
        args.append("--local-services")
    _run(args)


def cmd_verify(claim: str):
    args = [*SR, "verify", claim, "--format", "markdown", "--progress"]
    if _needs_community(claim):
        args.append("--local-services")
    _run(args)


def cmd_status():
    _run([*SR, "engine", "list"])


def cmd_cookie():
    _run([*SR, "cookie"])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: run.py <start|stop|ask|verify|status|cookie> [args...]")
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
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
