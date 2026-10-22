"""Durable filesystem writes and portable, reentrant process locks.

The same lock object is shared by local callers. FileLock supplies a Windows
or POSIX OS lock, while thread-local ownership prevents unrelated threads
from treating one another as nested lock holders.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from filelock import FileLock

_LOCKS: dict[str, FileLock] = {}
_LOCKS_GUARD = threading.Lock()


@contextmanager
def path_lock(path: Path, *, timeout: float = -1) -> Iterator[None]:
    """Serialize a logical transaction, including across worker processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    key = str(path.resolve())
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(key, FileLock(key, preserve_lock_file=True))
    with lock.acquire(timeout=timeout):
        yield


def fsync_directory(directory: Path) -> None:
    """Persist a replaced directory entry where the platform supports it."""
    if os.name == "nt":
        return  # Windows does not expose POSIX directory fsync via os.open.
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_text(path: Path, text: str, *, newline: str | None = "") -> None:
    """Publish only complete UTF-8 contents; callers lock multi-step writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline=newline) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        # Retain executable/read-only attributes instead of silently changing
        # existing research code permissions to mkstemp's restrictive default.
        if os.name != "nt" and path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        replace_complete_file(temporary, path)
        fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def replace_complete_file(temporary: Path | str, path: Path | str, *, timeout: float = 5.0) -> None:
    """Allow a Windows reader to close its handle before atomic replacement.

    Windows readers and virus scanners can briefly deny delete sharing. Keep
    the complete temporary file intact and retry only these OS errors, for at
    most five seconds. Permanent permissions and other errors still propagate.
    Never move the old target away or fall back to truncating it. This also
    accepts prepared binary files, SQLite snapshots and directories.
    """
    _move_complete_path(temporary, path, timeout=timeout, replace=True)


def rename_path(source: Path | str, destination: Path | str, *, timeout: float = 5.0) -> None:
    """Retry Windows sharing violations while retaining os.rename semantics."""
    _move_complete_path(source, destination, timeout=timeout, replace=False)


def _move_complete_path(source: Path | str, destination: Path | str, *, timeout: float, replace: bool) -> None:
    deadline = time.monotonic() + timeout
    delay = 0.01
    while True:
        try:
            if replace:
                os.replace(source, destination)
            else:
                os.rename(source, destination)
            return
        except OSError as error:
            if (os.name != "nt" or getattr(error, "winerror", None) not in {5, 32, 33}
                    or time.monotonic() >= deadline):
                raise
            time.sleep(min(delay, max(0.0, deadline - time.monotonic())))
            delay = min(0.2, delay * 2)


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_write_text(path, json.dumps(dict(payload), indent=2, ensure_ascii=False,
                                     sort_keys=True, allow_nan=False) + "\n")


def append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    """Persist one complete event under a shared per-stream lock."""
    encoded = json.dumps(dict(payload), ensure_ascii=False, allow_nan=False) + "\n"
    with path_lock(path.with_name(f".{path.name}.lock")):
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        fsync_directory(path.parent)
