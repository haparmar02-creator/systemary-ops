"""Idempotency for publish operations.

If the same publishing task runs twice -- a retry, a re-fired routine,
a human re-clicking something -- it must never upload the same video
twice. The idempotency key is the Calendar record's stable id (its
Content ID/record id), which is exactly what stays constant across
retries of "publish this record" even if everything else about the
retry (timing, task_id) differs.

JSONIdempotencyStore persists to a local file so the guarantee survives
a process restart, not just a single run. The file lives under
`.state/` (gitignored -- see .gitignore) and holds no credentials, only
{key: {video_id, recorded_at}} -- safe to inspect, never sensitive.
"""
from __future__ import annotations

import datetime
import json
import threading
from pathlib import Path
from typing import Optional, Protocol


class IdempotencyStore(Protocol):
    def get(self, key: str) -> Optional[dict]: ...
    def record(self, key: str, video_id: str) -> None: ...


class InMemoryIdempotencyStore:
    """Used in tests and dry-run -- nothing persists past the process."""

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}

    def get(self, key: str) -> Optional[dict]:
        return self._data.get(key)

    def record(self, key: str, video_id: str) -> None:
        self._data[key] = {
            "video_id": video_id,
            "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }


class JSONIdempotencyStore:
    """Production store: a small JSON file, one entry per Calendar record
    that has ever been successfully uploaded. Thread-safe for the
    single-process case (a lock around read-modify-write); this is not
    meant to coordinate across multiple concurrent processes -- if this
    ever runs from more than one process at once, replace this with an
    Airtable-field-based check (the Published URL / stored Video ID
    field on the Calendar record itself is an equally valid idempotency
    signal and is naturally shared across processes)."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("{}")

    def _read(self) -> dict:
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            return self._read().get(key)

    def record(self, key: str, video_id: str) -> None:
        with self._lock:
            data = self._read()
            data[key] = {
                "video_id": video_id,
                "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            self._path.write_text(json.dumps(data, indent=2))
