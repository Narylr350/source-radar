"""Minimal engine installer planning and metadata helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .paths import (
    archive_download_path,
    download_manifest_path,
    downloads_root,
    engine_dir,
    engine_metadata_path,
    engine_source_path,
    engine_venv_path,
)
from .registry import BackendRegistry


@dataclass(frozen=True)
class EngineInstallPlan:
    backend_key: str
    engine_key: str
    engine_dir: Path
    source_path: Path
    venv_path: Path
    metadata_path: Path
    downloads_root: Path


@dataclass(frozen=True)
class ResolvedSource:
    path: Path
    using_legacy: bool
    reason: str
    migration_hint: str = ""


class EngineInstaller:
    """Owns engine/download layout, metadata, and non-destructive legacy fallback."""

    def __init__(self, registry: BackendRegistry, project_root: Path | str = ".") -> None:
        self.registry = registry
        self.project_root = Path(project_root)

    def prepare_layout(self, backend_key: str) -> EngineInstallPlan:
        backend = self.registry.get(backend_key)
        plan = self._plan(backend.key)
        plan.engine_dir.mkdir(parents=True, exist_ok=True)
        for name in ("archives", "wheels", "manifests"):
            (plan.downloads_root / name).mkdir(parents=True, exist_ok=True)
        return plan

    def resolve_source(self, backend_key: str) -> ResolvedSource:
        backend = self.registry.get(backend_key)
        target = engine_source_path(backend.key, self.project_root)
        if target.exists():
            return ResolvedSource(path=target, using_legacy=False, reason="target")

        legacy = self.project_root / backend.install.legacy_path if backend.install.legacy_path else None
        if legacy and legacy.exists():
            hint = f"legacy source detected; migrate to {target}"
            return ResolvedSource(path=legacy, using_legacy=True, reason="legacy-fallback", migration_hint=hint)

        return ResolvedSource(path=target, using_legacy=False, reason="missing")

    def write_metadata(
        self,
        backend_key: str,
        *,
        source: str,
        version: str = "",
        commit: str = "",
        archive_name: str = "",
    ) -> dict[str, Any]:
        backend = self.registry.get(backend_key)
        plan = self.prepare_layout(backend.key)
        resolved = self.resolve_source(backend.key)
        archive_path = archive_download_path(archive_name, self.project_root) if archive_name else None
        metadata: dict[str, Any] = {
            "backend_key": backend.key,
            "engine_key": plan.engine_key,
            "source": source,
            "version": version,
            "commit": commit,
            "source_path": self._portable(resolved.path),
            "target_path": self._portable(plan.source_path),
            "venv_path": self._portable(resolved.path / ".venv"),
            "downloads_root": self._portable(plan.downloads_root),
            "archive_path": self._portable(archive_path) if archive_path else "",
            "legacy_path": backend.install.legacy_path,
            "using_legacy": resolved.using_legacy,
        }
        plan.metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        backend.install.source = source
        backend.install.version = version
        backend.install.commit = commit
        backend.install.target_path = self._portable(plan.source_path)
        return metadata

    def record_download(
        self,
        backend_key: str,
        *,
        filename: str,
        url: str,
        status: str,
        reason: str = "",
    ) -> dict[str, Any]:
        backend = self.registry.get(backend_key)
        self.prepare_layout(backend.key)
        archive_path = archive_download_path(filename, self.project_root)
        manifest_path = download_manifest_path(filename, self.project_root)
        manifest = {
            "backend_key": backend.key,
            "engine_key": backend.key.split(".")[-1],
            "filename": filename,
            "url": url,
            "status": status,
            "reason": reason,
            "archive_path": self._portable(archive_path),
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return manifest

    def install_diagnostics(self, backend_key: str, *, download_limit: int = 3) -> dict[str, Any]:
        backend = self.registry.get(backend_key)
        plan = self._plan(backend.key)
        resolved = self.resolve_source(backend.key)
        metadata = self._read_json(plan.metadata_path)
        for key in ("source_path", "target_path", "venv_path", "downloads_root", "archive_path"):
            if metadata.get(key):
                metadata[key] = self._portable_relative(metadata[key])
        downloads = []
        manifest_dir = plan.downloads_root / "manifests"
        if manifest_dir.exists():
            manifests = sorted(
                manifest_dir.glob("*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            for path in manifests:
                manifest = self._read_json(path)
                if manifest.get("backend_key") != backend.key:
                    continue
                if manifest.get("archive_path"):
                    manifest["archive_path"] = self._portable_relative(manifest["archive_path"])
                downloads.append(manifest)
                if len(downloads) >= download_limit:
                    break
        return {
            "source_path": self._portable_relative(resolved.path),
            "using_legacy": resolved.using_legacy,
            "migration_hint": resolved.migration_hint,
            "metadata": metadata,
            "downloads": downloads,
        }

    def _plan(self, backend_key: str) -> EngineInstallPlan:
        engine_key = backend_key.split(".")[-1]
        return EngineInstallPlan(
            backend_key=backend_key,
            engine_key=engine_key,
            engine_dir=engine_dir(backend_key, self.project_root),
            source_path=engine_source_path(backend_key, self.project_root),
            venv_path=engine_venv_path(backend_key, self.project_root),
            metadata_path=engine_metadata_path(backend_key, self.project_root),
            downloads_root=downloads_root(self.project_root),
        )

    @staticmethod
    def _portable(path: Path | None) -> str:
        return "" if path is None else str(path).replace("\\", "/")

    def _portable_relative(self, path: Path | str) -> str:
        value = Path(path)
        try:
            value = value.relative_to(self.project_root)
        except ValueError:
            pass
        return self._portable(value)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
