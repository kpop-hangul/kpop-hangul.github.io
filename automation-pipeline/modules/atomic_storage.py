"""Cross-process locking and atomic JSON replacement for local runtime state."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile
import threading

_LOCKS = {}
_REGISTRY_LOCK = threading.Lock()
_DEPTH = threading.local()


@contextmanager
def file_lock(path):
    lock = Path(str(path) + ".lock").resolve()
    key = str(lock)
    with _REGISTRY_LOCK:
        mutex = _LOCKS.setdefault(key, threading.RLock())
    with mutex:
        held = getattr(_DEPTH, "held", set())
        if key in held:
            yield
            return
        lock.parent.mkdir(parents=True, exist_ok=True)
        with lock.open("a") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            _DEPTH.held = held | {key}
            try:
                yield
            finally:
                _DEPTH.held = held
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=".json-", delete=False, encoding="utf-8") as handle:
            temp_path = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
