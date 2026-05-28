"""Acquisition cache — caches provider.collect results, not AI answers."""

import hashlib
import json
import os
import pathlib
import time
from dataclasses import asdict
from typing import Optional

CACHE_DIR = pathlib.Path(".source-radar") / "cache" / "acquisition"
MAX_ENTRIES = 1000
MAX_BYTES = 200 * 1024 * 1024  # 200MB
SCHEMA_VERSION = 1
CACHE_ADAPTER_VERSION = "v3-adaptive-1"

REALTIME_KEYWORDS = (
    "今天", "现在", "刚刚", "实时", "最新", "新闻",
    "股价", "汇率", "天气", "比赛", "赛程", "开奖",
    "价格", "优惠", "活动", "降价",
)

TTL_MAP: dict[str, int] = {
    "search": 6 * 3600,
    "trafilatura": 24 * 3600,
    "crawl4ai": 24 * 3600,
    "mediacrawler": 12 * 3600,
    "firecrawl": 12 * 3600,
    "web": 24 * 3600,
    "official": 24 * 3600,
    "github": 24 * 3600,
}


def _cache_root() -> pathlib.Path:
    p = CACHE_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def is_realtime_query(query: str) -> bool:
    return any(kw in query for kw in REALTIME_KEYWORDS)


def _make_provider_signature(provider: str, provider_type: str = "",
                             endpoint: str = "", adapter_class: str = "") -> str:
    """Build a non-sensitive provider signature for cache key differentiation."""
    parts = [provider, provider_type]
    if endpoint:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(endpoint)
            if parsed.hostname:
                parts.append(parsed.hostname)
        except Exception:
            pass
    if adapter_class:
        parts.append(adapter_class)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:8]


def _make_key(provider: str, query: str = "", url: str = "",
              repo: str = "", limit: int = 5, platform: str = "",
              provider_signature: str = "") -> str:
    raw = (f"{provider}|{query}|{url}|{repo}|{limit}|{platform}|"
           f"v{SCHEMA_VERSION}|{CACHE_ADAPTER_VERSION}|{provider_signature}")
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _entry_path(key: str) -> pathlib.Path:
    return _cache_root() / "entries" / f"{key}.json"


def _read_index() -> dict:
    idx_path = _cache_root() / "index.json"
    if not idx_path.exists():
        return {}
    try:
        return json.loads(idx_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _total_bytes() -> int:
    entries_dir = _cache_root() / "entries"
    total = 0
    if entries_dir.exists():
        for f in entries_dir.iterdir():
            if f.suffix == ".json":
                total += f.stat().st_size
    return total


def _write_index(data: dict) -> None:
    idx_path = _cache_root() / "index.json"
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = idx_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(idx_path)


def get_cached_result(provider: str, query: str = "", url: str = "",
                      repo: str = "", limit: int = 5, platform: str = "",
                      provider_signature: str = "") -> tuple[Optional[dict], int]:
    """Returns (cached_result_or_None, cache_age_seconds).

    cache_age_seconds is 0 on miss, positive integer on hit.
    """
    if is_realtime_query(query):
        return None, 0
    key = _make_key(provider, query, url, repo, limit, platform, provider_signature)
    ep = _entry_path(key)
    if not ep.exists():
        return None, 0
    try:
        data = json.loads(ep.read_text(encoding="utf-8"))
    except Exception:
        ep.unlink(missing_ok=True)
        return None, 0
    created = data.get("created_at", 0)
    ttl = data.get("ttl_seconds", TTL_MAP.get(provider, 86400))
    age = int(time.time() - created) if created else 0
    if time.time() - created > ttl:
        ep.unlink(missing_ok=True)
        return None, 0
    # Update last accessed in entry file
    data["last_accessed_at"] = time.time()
    ep.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    # Also update last_accessed_at in index
    idx = _read_index()
    if key in idx:
        idx[key]["last_accessed_at"] = data["last_accessed_at"]
        _write_index(idx)
    return data.get("result"), age


def get_cached_entry(provider: str, query: str = "", url: str = "",
                     repo: str = "", limit: int = 5, platform: str = "",
                     provider_signature: str = "") -> Optional[dict]:
    """Returns full cache entry dict (including metadata) or None."""
    if is_realtime_query(query):
        return None
    key = _make_key(provider, query, url, repo, limit, platform, provider_signature)
    ep = _entry_path(key)
    if not ep.exists():
        return None
    try:
        data = json.loads(ep.read_text(encoding="utf-8"))
    except Exception:
        ep.unlink(missing_ok=True)
        return None
    created = data.get("created_at", 0)
    ttl = data.get("ttl_seconds", TTL_MAP.get(provider, 86400))
    if time.time() - created > ttl:
        ep.unlink(missing_ok=True)
        return None
    return data


def put_cached_result(provider: str, result: dict, query: str = "",
                      url: str = "", repo: str = "", limit: int = 5,
                      platform: str = "", provider_signature: str = "") -> None:
    if is_realtime_query(query):
        return
    key = _make_key(provider, query, url, repo, limit, platform, provider_signature)
    entry = {
        "schema_version": SCHEMA_VERSION,
        "adapter_version": CACHE_ADAPTER_VERSION,
        "created_at": time.time(),
        "last_accessed_at": time.time(),
        "provider": provider,
        "key": key,
        "ttl_seconds": TTL_MAP.get(provider, 86400),
        "query": query,
        "result": result,
    }
    ep = _entry_path(key)
    ep.parent.mkdir(parents=True, exist_ok=True)
    tmp = ep.with_suffix(".tmp")
    tmp.write_text(json.dumps(entry, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(ep)
    # Update index
    idx = _read_index()
    idx[key] = {"provider": provider, "created_at": entry["created_at"],
                "last_accessed_at": entry["last_accessed_at"],
                "query": query[:80]}
    _write_index(idx)
    if len(idx) > MAX_ENTRIES or _total_bytes() > MAX_BYTES:
        prune()


def cache_status() -> dict:
    idx = _read_index()
    entries_dir = _cache_root() / "entries"
    total_bytes = 0
    expired = 0
    now = time.time()
    if entries_dir.exists():
        for f in entries_dir.iterdir():
            if f.suffix == ".json":
                total_bytes += f.stat().st_size
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                    if now - d.get("created_at", 0) > d.get("ttl_seconds", 86400):
                        expired += 1
                except Exception:
                    expired += 1
    return {
        "entry_count": len(idx),
        "total_bytes": total_bytes,
        "expired_count": expired,
        "max_entries": MAX_ENTRIES,
        "max_bytes": MAX_BYTES,
        "schema_version": SCHEMA_VERSION,
        "adapter_version": CACHE_ADAPTER_VERSION,
    }


def cache_clear() -> str:
    idx_path = _cache_root() / "index.json"
    entries_dir = _cache_root() / "entries"
    count = 0
    if entries_dir.exists():
        for f in entries_dir.iterdir():
            f.unlink(missing_ok=True)
            count += 1
    idx_path.unlink(missing_ok=True)
    return f"OK 已清除 {count} 条缓存"


def prune() -> str:
    idx = _read_index()
    entries_dir = _cache_root() / "entries"
    now = time.time()
    expired = []
    for key, meta in idx.items():
        ep = _entry_path(key)
        if ep.exists():
            try:
                d = json.loads(ep.read_text(encoding="utf-8"))
                ttl = d.get("ttl_seconds", 86400)
                if now - d.get("created_at", 0) > ttl:
                    expired.append(key)
                    ep.unlink(missing_ok=True)
            except Exception:
                expired.append(key)
                ep.unlink(missing_ok=True)
        else:
            expired.append(key)
    for k in expired:
        idx.pop(k, None)
    lru_removed = 0
    # LRU: remove oldest by last_accessed_at (entry count)
    if len(idx) > MAX_ENTRIES:
        sorted_keys = sorted(idx, key=lambda k: idx[k].get("last_accessed_at", 0))
        to_remove = sorted_keys[:len(idx) - MAX_ENTRIES]
        lru_removed += len(to_remove)
        for k in to_remove:
            idx.pop(k, None)
            _entry_path(k).unlink(missing_ok=True)

    # LRU byte-based eviction
    entries_dir = _cache_root() / "entries"
    total_bytes = 0
    if entries_dir.exists():
        for f in entries_dir.iterdir():
            if f.suffix == ".json":
                total_bytes += f.stat().st_size
    if total_bytes > MAX_BYTES:
        sorted_keys = sorted(idx, key=lambda k: idx[k].get("last_accessed_at", 0))
        bytes_removed = 0
        for k in sorted_keys:
            if total_bytes <= MAX_BYTES * 0.8:
                break
            ep = _entry_path(k)
            if ep.exists():
                total_bytes -= ep.stat().st_size
                ep.unlink(missing_ok=True)
                bytes_removed += 1
            idx.pop(k, None)
        lru_removed += bytes_removed

    _write_index(idx)
    return f"OK 已清理 {len(expired)} 条过期 + {lru_removed} 条 LRU"
