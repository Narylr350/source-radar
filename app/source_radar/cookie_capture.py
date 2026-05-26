"""Cookie capture via Playwright browser automation."""

import os
import pathlib

from .bridge import load_local_env

PLATFORM_COOKIE_CONFIG: dict[str, dict[str, str]] = {
    "xhs":   {"name": "小红书", "env": "SOURCE_RADAR_XHS_COOKIE",   "login_url": "https://www.xiaohongshu.com"},
    "wb":    {"name": "微博",   "env": "SOURCE_RADAR_WEIBO_COOKIE", "login_url": "https://weibo.com"},
    "bili":  {"name": "B站",    "env": "SOURCE_RADAR_BILI_COOKIE",  "login_url": "https://www.bilibili.com"},
    "tieba": {"name": "贴吧",   "env": "SOURCE_RADAR_TIEBA_COOKIE", "login_url": "https://tieba.baidu.com"},
    "dy":    {"name": "抖音",   "env": "SOURCE_RADAR_DOUYIN_COOKIE", "login_url": "https://www.douyin.com"},
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


def _profile_dir(platform_key: str) -> pathlib.Path:
    return _local_env_path().parent / "browser-profiles" / platform_key


def _close_if_blank(page):
    """Close a new page if it's stuck at about:blank (common with Weibo login popups)."""
    try:
        page.wait_for_timeout(1500)
        if page.url == "about:blank":
            page.close()
    except Exception:
        pass


def capture_cookies(login_url: str, platform_key: str, platform_name: str) -> str:
    """Open browser, let user log in, return cookie string on Enter.

    Uses persistent browser profile so login state survives across runs.
    Tries real Chrome first (less detectable), falls back to Chromium.
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

    profile = _profile_dir(platform_key)
    profile.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser_type = p.chromium
        channel = None
        try:
            browser_type.launch(channel="chrome", headless=True).close()
            channel = "chrome"
        except Exception:
            pass

        context = browser_type.launch_persistent_context(
            str(profile),
            headless=False,
            channel=channel,
            viewport=None,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        # Auto-close empty popups that some sites (e.g. Weibo) trigger on login
        context.on("page", lambda p: _close_if_blank(p))

        page = context.pages()[0] if context.pages() else context.new_page()
        page.goto(login_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        print(f"\n请自行点击登录 {platform_name}，完成后按 Enter...")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            context.close()
            raise KeyboardInterrupt

        cookies = context.cookies()
        context.close()

    if not cookies:
        return ""

    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def run_cookie(platform: str | None = None, force: bool = False) -> str:
    """Main entry point for `source-radar cookie` command."""
    load_local_env()

    platforms = list(PLATFORM_COOKIE_CONFIG.items())
    if platform:
        platforms = [(p, c) for p, c in platforms if p == platform]
        if not platforms:
            known = ", ".join(PLATFORM_COOKIE_CONFIG)
            return f"未知平台: {platform}\n可用平台: {known}"

    pending: list[tuple[str, dict[str, str]]] = []
    skipped: list[str] = []
    for key, config in platforms:
        env_name = config["env"]
        existing = os.environ.get(env_name, "")
        if existing and not force:
            skipped.append(config["name"])
        else:
            pending.append((key, config))

    if not pending:
        return "所有平台 Cookie 已配置，无需获取。使用 --force 强制重新获取。"

    plan_lines = [
        f"将获取 {len(pending)} 个平台的 Cookie"
        f"（{', '.join(c['name'] for _, c in pending)}）"
    ]
    if skipped:
        plan_lines.append(
            f"跳过 {len(skipped)} 个已配置（{', '.join(skipped)}）"
        )
    print("\n".join(plan_lines))

    captured: dict[str, str] = {}
    for key, config in pending:
        try:
            cookie_str = capture_cookies(config["login_url"], key, config["name"])
            if cookie_str:
                captured[config["env"]] = cookie_str
                print(f"  OK {config['name']}: 已获取 Cookie")
            else:
                print(f"  WARN {config['name']}: 未检测到 Cookie，可能登录未完成")
        except KeyboardInterrupt:
            print("\n中断，已获取的 Cookie 将保存。")
            break

    if captured:
        write_local_env(captured)
        os.environ.update(captured)
        print(f"\nCookie 已保存到 {_local_env_path()}")

    failed = len(pending) - len(captured)
    lines: list[str] = []
    lines.append(f"成功 {len(captured)} 个")
    if skipped:
        lines.append(f"跳过 {len(skipped)} 个（已配置）")
    if failed:
        lines.append(f"未获取 {failed} 个")
    return "，".join(lines)
