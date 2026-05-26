"""Cookie capture via Playwright browser automation."""

import os
import pathlib

PLATFORM_COOKIE_CONFIG: dict[str, dict[str, str]] = {
    "xhs":   {"name": "小红书", "env": "SOURCE_RADAR_XHS_COOKIE",   "login_url": "https://www.xiaohongshu.com/explore"},
    "wb":    {"name": "微博",   "env": "SOURCE_RADAR_WEIBO_COOKIE", "login_url": "https://weibo.com/login.php"},
    "bili":  {"name": "B站",    "env": "SOURCE_RADAR_BILI_COOKIE",  "login_url": "https://passport.bilibili.com/login"},
    "tieba": {"name": "贴吧",   "env": "SOURCE_RADAR_TIEBA_COOKIE", "login_url": "https://tieba.baidu.com/index.html"},
    "dy":    {"name": "抖音",   "env": "SOURCE_RADAR_DOUYIN_COOKIE", "login_url": "https://www.douyin.com/"},
}


def _local_env_path(root: str | os.PathLike[str] = ".") -> pathlib.Path:
    return pathlib.Path(root) / ".source-radar" / "local.env"


def read_local_env(root: str | os.PathLike[str] = ".") -> dict[str, str]:
    """Read all key=value pairs from local.env as a dict."""
    path = _local_env_path(root)
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            result[key] = value
    return result


def write_local_env(updates: dict[str, str], root: str | os.PathLike[str] = ".") -> None:
    """Merge updates into local.env, preserving keys not in updates."""
    existing = read_local_env(root)
    existing.update(updates)
    path = _local_env_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in existing.items() if v]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def capture_cookies(login_url: str, platform_name: str) -> str:
    """Open Chromium, let user log in, return cookie string on Enter.

    Returns empty string if no cookies were captured.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        import sys

        print(
            "Playwright 未安装。请运行: playwright install chromium\n"
            "或: uv run crawl4ai-setup",
            file=sys.stderr,
        )
        raise SystemExit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(login_url)

        try:
            input(f"\n请在浏览器中登录 {platform_name}，完成后按 Enter...")
        except (EOFError, KeyboardInterrupt):
            browser.close()
            raise KeyboardInterrupt

        cookies = context.cookies()
        browser.close()

    if not cookies:
        return ""

    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)
