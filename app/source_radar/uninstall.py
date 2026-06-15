"""Uninstall source-radar components safely.

Default is dry-run only. Use --yes to actually delete.
"""

from __future__ import annotations

import os
import pathlib
import shutil
from dataclasses import dataclass


@dataclass
class DeleteTarget:
    kind: str
    path: pathlib.Path
    description: str
    exists: bool


def _project_root() -> pathlib.Path:
    return pathlib.Path.cwd()


def _config_dir() -> pathlib.Path:
    configured = os.environ.get("SOURCE_RADAR_CONFIG_DIR")
    if configured:
        return pathlib.Path(configured)
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return pathlib.Path(appdata) / "source-radar"
    return pathlib.Path.home() / ".config" / "source-radar"


def _skill_dir() -> pathlib.Path:
    return pathlib.Path.home() / ".claude" / "skills" / "source-radar"


def build_uninstall_plan(
    *,
    project: bool = False,
    skill: bool = False,
    user_config: bool = False,
    all_: bool = False,
) -> list[DeleteTarget]:
    if all_:
        project = skill = user_config = True

    root = _project_root()
    targets: list[DeleteTarget] = []

    if project:
        for path, desc in [
            (root / ".venv", "Python virtual environment"),
            (root / ".source-radar", "project local env, cookies, browser profiles"),
            (root / "external" / "MediaCrawler", "MediaCrawler checkout"),
            (root / "external" / "searxng", "SearXNG checkout"),
        ]:
            targets.append(DeleteTarget("project", path, desc, path.exists()))

    if skill:
        path = _skill_dir()
        targets.append(DeleteTarget("skill", path, "Claude Code Skill", path.exists()))

    if user_config:
        path = _config_dir()
        targets.append(DeleteTarget("user-config", path, "user-level source-radar config including API key", path.exists()))

    return targets


def render_uninstall_plan(targets: list[DeleteTarget]) -> str:
    if not targets:
        return (
            "未指定卸载范围。\n"
            "可用选项:\n"
            "  --project       删除当前项目的 .venv/.source-radar/external/MediaCrawler\n"
            "  --skill         删除 Claude Code Skill\n"
            "  --user-config   删除用户级配置，包括 AI key\n"
            "  --all           删除以上全部\n"
        )

    lines = ["=== source-radar 卸载计划 ==="]
    for t in targets:
        mark = "FOUND" if t.exists else "MISS"
        lines.append(f"  [{mark}] {t.kind}: {t.path}")
        lines.append(f"          {t.description}")

    lines.append("")
    lines.append("默认只是预览，不会删除。")
    lines.append("确认删除请加 --yes。")
    return "\n".join(lines)


def run_uninstall(
    *,
    project: bool = False,
    skill: bool = False,
    user_config: bool = False,
    all_: bool = False,
    yes: bool = False,
) -> str:
    targets = build_uninstall_plan(
        project=project,
        skill=skill,
        user_config=user_config,
        all_=all_,
    )

    if not yes:
        return render_uninstall_plan(targets)

    lines = ["=== source-radar 卸载 ==="]
    for target in targets:
        if not target.exists:
            lines.append(f"  SKIP 不存在: {target.path}")
            continue
        try:
            if target.path.is_dir():
                shutil.rmtree(target.path)
            else:
                target.path.unlink()
            lines.append(f"  OK 已删除: {target.path}")
        except Exception as e:
            lines.append(f"  WARN 删除失败: {target.path} - {e}")

    return "\n".join(lines)
