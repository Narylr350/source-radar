"""Unified crawler engine management."""

import importlib
import os
import pathlib
import subprocess
import sys
import urllib.request

ENGINES: dict[str, dict] = {
    "trafilatura": {
        "name": "Trafilatura",
        "type": "library",
        "module": "trafilatura",
        "description": "通用网页正文抽取",
        "fix": "uv sync",
    },
    "crawl4ai": {
        "name": "Crawl4AI",
        "type": "library",
        "module": "crawl4ai",
        "description": "浏览器渲染动态页面采集",
        "fix": "uv sync --extra dynamic && uv run crawl4ai-setup",
    },
    "mediacrawler": {
        "name": "MediaCrawler",
        "type": "service",
        "local_dir": "external/MediaCrawler",
        "health_url": "http://127.0.0.1:8080/api/health",
        "repo_hint": "https://github.com/NanmiCoder/MediaCrawler",
        "description": "中文社区平台搜索与采集（小红书/微博/B站/贴吧/抖音/知乎）",
        "fix": "git clone https://github.com/NanmiCoder/MediaCrawler external/MediaCrawler",
    },
}


def _root() -> pathlib.Path:
    return pathlib.Path(".")


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


def run_engine_install() -> str:
    lines: list[str] = []

    # Trafilatura
    traf_status, _ = _check_library("trafilatura")
    if traf_status == "missing":
        lines.append("安装 Trafilatura...")
        subprocess.run([sys.executable, "-m", "pip", "install", "trafilatura>=2.0"], check=False)
        lines.append("  OK Trafilatura 已安装")
    else:
        lines.append("  OK Trafilatura 已安装，跳过")

    # Crawl4AI
    c4ai_status, _ = _check_library("crawl4ai")
    if c4ai_status == "missing":
        lines.append("安装 Crawl4AI（含 Playwright 浏览器）...")
        subprocess.run(["uv", "sync", "--extra", "dynamic"], check=False)
        subprocess.run(["uv", "run", "crawl4ai-setup"], check=False)
        lines.append("  OK Crawl4AI 已安装")
    else:
        lines.append("  OK Crawl4AI 已安装，跳过")

    # MediaCrawler
    root = _root()
    mc_dir = root / "external" / "MediaCrawler"
    if not mc_dir.exists():
        lines.append("安装 MediaCrawler...")
        lines.append("  正在 clone MediaCrawler（可能较慢）...")
        result = subprocess.run(
            ["git", "clone", "https://github.com/NanmiCoder/MediaCrawler",
             str(mc_dir)],
            check=False,
        )
        if result.returncode != 0:
            lines.append(f"  WARN clone 失败，请手动: git clone https://github.com/NanmiCoder/MediaCrawler {mc_dir}")
        else:
            lines.append("  安装 MediaCrawler 依赖...")
            subprocess.run(["uv", "sync"], cwd=str(mc_dir), check=False)
            lines.append("  OK MediaCrawler 已安装")
    else:
        lines.append("  OK MediaCrawler 目录已存在，跳过 clone")
        lines.append("    更新依赖...")
        subprocess.run(["uv", "sync"], cwd=str(mc_dir), check=False)

    return "\n".join(lines)
