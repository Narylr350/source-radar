"""Short-term session context for ask/verify/research continuity."""

import json
import os
import pathlib
import time
from typing import Optional

SESSION_DIR = pathlib.Path(".source-radar") / "sessions"
MAX_RECORDS = 100
MAX_BYTES = 5 * 1024 * 1024  # 5MB
MAX_SNIPPET = 300
MAX_SUMMARY = 500
MAX_GAPS = 10
MAX_SKIPPED = 10
MAX_EVIDENCE_REFS = 20


def _session_path(session_id: str) -> pathlib.Path:
    return SESSION_DIR / f"{session_id}.jsonl"


def _ensure_dir() -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def append_session_record(session_id: str, record: dict) -> None:
    _ensure_dir()
    record["ts"] = record.get("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ"))
    # Trim large fields
    if "evidence_refs" in record:
        record["evidence_refs"] = [
            {k: (v[:MAX_SNIPPET] if k == "snippet" and isinstance(v, str) else v)
             for k, v in ref.items()}
            for ref in record["evidence_refs"][:MAX_EVIDENCE_REFS]
        ]
    if record.get("answer_summary", ""):
        record["answer_summary"] = str(record["answer_summary"])[:MAX_SUMMARY]
    if len(record.get("gaps", [])) > MAX_GAPS:
        record["gaps"] = record["gaps"][:MAX_GAPS]
    if len(record.get("tools_skipped", [])) > MAX_SKIPPED:
        record["tools_skipped"] = record["tools_skipped"][:MAX_SKIPPED]

    path = _session_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    # Prune if needed
    if path.stat().st_size > MAX_BYTES:
        _prune_session(path)


def _prune_session(path: pathlib.Path) -> None:
    lines = []
    try:
        with open(path, encoding="utf-8") as f:
            lines = [line for line in f.readlines() if line.strip()]
    except Exception:
        return
    # Trim by record count (most recent first)
    if len(lines) > MAX_RECORDS:
        lines = lines[-MAX_RECORDS:]
    # Trim by byte count
    total = sum(len(line.encode("utf-8")) + 1 for line in lines)
    while total > MAX_BYTES and len(lines) > 1:
        removed = lines.pop(0)
        total -= len(removed.encode("utf-8")) + 1
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def load_recent_session_context(session_id: str, limit: int = 10,
                                max_age_hours: int = 24) -> list[dict]:
    path = _session_path(session_id)
    if not path.exists():
        return []
    records = []
    cutoff = time.time() - max_age_hours * 3600
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = r.get("ts", "")
            try:
                t = time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
            except Exception:
                t = 0
            if t >= cutoff:
                records.append(r)
    except Exception:
        return []
    return records[-limit:]


def clear_session(session_id: str) -> str:
    path = _session_path(session_id)
    if path.exists():
        path.unlink()
        return f"OK 已清除 session: {session_id}"
    return f"SKIP session 不存在: {session_id}"


def session_status(session_id: Optional[str] = None) -> dict:
    _ensure_dir()
    sessions = {}
    for f in SESSION_DIR.iterdir():
        if not f.name.endswith(".jsonl"):
            continue
        sid = f.name[:-6]
        if session_id and sid != session_id:
            continue
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
            sessions[sid] = {
                "record_count": len([l for l in lines if l.strip()]),
                "total_bytes": f.stat().st_size,
                "path": str(f),
            }
        except Exception:
            sessions[sid] = {"record_count": 0, "total_bytes": 0, "path": str(f)}
    return sessions


def new_session() -> str:
    sid = f"session-{int(time.time())}"
    return sid


def lexical_is_related(current_query: str, history_records: list[dict]) -> bool:
    """Quick lexical check: is the current query related to recent history?"""
    if not history_records:
        return False
    follow_words = ("那", "这个", "刚才", "继续", "上面", "它", "安全吗",
                    "怎么调", "还有呢", "然后", "接着", "也", "再",
                    "内存", "电压", "频率", "兼容")
    cq = current_query.lower()
    if any(w in cq for w in follow_words):
        return True
    for r in history_records[-3:]:
        hq = (r.get("query", "") or r.get("normalized_query", "")).lower()
        words = set(hq.split()) & set(cq.split())
        if len(words) >= 2:
            return True
    return False
