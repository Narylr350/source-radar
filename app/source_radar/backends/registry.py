"""Structured backend registry used by CLI and MCP status output."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .paths import engine_source_path

BACKEND_TYPES = {"native", "local-source", "service", "legacy-bridge", "external"}
LIFECYCLE_POLICIES = {"disabled", "on-demand", "warm", "always-on", "external"}
LIFECYCLE_STATES = {
    "stopped",
    "starting",
    "warming",
    "ready",
    "degraded",
    "failed",
    "cooling_down",
}


@dataclass
class BackendDiagnostics:
    reason: str = ""
    message: str = ""
    retryable: bool = True
    fix: str = ""
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BackendInstall:
    source: str = ""
    target_path: str = ""
    legacy_path: str = ""
    repo_url: str = ""
    version: str = ""
    commit: str = ""
    license: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class BackendRecord:
    key: str
    name: str
    backend_type: str
    lifecycle_policy: str
    lifecycle_state: str = "stopped"
    status: str = "stopped"
    ready: bool = False
    install: BackendInstall = field(default_factory=BackendInstall)
    idle_timeout_seconds: int = 0
    start_budget_seconds: int = 0
    diagnostics: BackendDiagnostics = field(default_factory=BackendDiagnostics)
    fallback: str = ""
    warm_lease_until: float | None = None
    cooling_down_until: float | None = None
    description: str = ""
    engine_key: str = ""

    def __post_init__(self) -> None:
        if self.backend_type not in BACKEND_TYPES:
            raise ValueError(f"unknown backend_type: {self.backend_type}")
        if self.lifecycle_policy not in LIFECYCLE_POLICIES:
            raise ValueError(f"unknown lifecycle_policy: {self.lifecycle_policy}")
        if self.lifecycle_state not in LIFECYCLE_STATES:
            raise ValueError(f"unknown lifecycle_state: {self.lifecycle_state}")

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["install"] = self.install.as_dict()
        data["diagnostics"] = self.diagnostics.as_dict()
        return data


class BackendRegistry:
    def __init__(self, records: list[BackendRecord]):
        self._records = {record.key: record for record in records}
        self._aliases: dict[str, str] = {}
        for record in records:
            self._aliases[record.key.split(".")[-1]] = record.key
            if record.engine_key:
                self._aliases[record.engine_key] = record.key

    def get(self, key: str) -> BackendRecord:
        real_key = self._aliases.get(key, key)
        return self._records[real_key]

    def all(self) -> list[BackendRecord]:
        return list(self._records.values())

    def snapshot(self) -> list[dict[str, Any]]:
        return [record.as_dict() for record in self.all()]


def _path(path: Path) -> str:
    return str(path).replace("\\", "/")


def build_default_registry(project_root: Path | str = ".") -> BackendRegistry:
    root = Path(project_root)
    return BackendRegistry([
        BackendRecord(
            key="web.trafilatura",
            engine_key="trafilatura",
            name="Trafilatura",
            backend_type="native",
            lifecycle_policy="on-demand",
            install=BackendInstall(source="python-package"),
            start_budget_seconds=0,
            idle_timeout_seconds=0,
            description="通用网页正文抽取",
        ),
        BackendRecord(
            key="browser.crawl4ai",
            engine_key="crawl4ai",
            name="Crawl4AI",
            backend_type="native",
            lifecycle_policy="on-demand",
            install=BackendInstall(
                source="python-package",
                target_path=_path(engine_source_path("browser.crawl4ai", root)),
            ),
            start_budget_seconds=30,
            idle_timeout_seconds=120,
            fallback="web.trafilatura",
            description="浏览器渲染动态页面采集",
        ),
        BackendRecord(
            key="community.mediacrawler",
            engine_key="mediacrawler",
            name="MediaCrawler",
            backend_type="legacy-bridge",
            lifecycle_policy="on-demand",
            install=BackendInstall(
                source="local-source",
                target_path=_path(engine_source_path("community.mediacrawler", root)),
                legacy_path="external/MediaCrawler",
                repo_url="https://github.com/NanmiCoder/MediaCrawler",
            ),
            start_budget_seconds=45,
            idle_timeout_seconds=180,
            fallback="community.mediacrawler legacy bridge fallback",
            description="中文社区平台搜索与采集（小红书/微博/B站/贴吧/抖音/知乎）",
        ),
        BackendRecord(
            key="community.bilibili",
            engine_key="bilibili",
            name="Bilibili",
            backend_type="native",
            lifecycle_policy="on-demand",
            install=BackendInstall(source="builtin-native"),
            start_budget_seconds=10,
            idle_timeout_seconds=0,
            fallback="community.mediacrawler",
            description="B站 native 视频搜索后端",
        ),
        BackendRecord(
            key="search.searxng",
            engine_key="searxng",
            name="SearXNG",
            backend_type="service",
            lifecycle_policy="warm",
            install=BackendInstall(
                source="local-source",
                target_path=_path(engine_source_path("search.searxng", root)),
                legacy_path="external/searxng",
                repo_url="https://github.com/searxng/searxng",
            ),
            start_budget_seconds=45,
            idle_timeout_seconds=300,
            fallback="search builtin fallback",
            description="元搜索引擎，聚合多个搜索源（替代直接 Bing 抓取）",
        ),
    ])
