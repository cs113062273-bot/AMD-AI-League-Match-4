import json
import os
import tempfile
import time
import threading
import weakref
from pathlib import Path

from .urls import safe_id

_locks=weakref.WeakValueDictionary()
_locks_guard=threading.Lock()


def _path_lock(path):
    key=os.path.normcase(os.path.abspath(path))
    with _locks_guard:
        lock=_locks.get(key)
        if lock is None:
            lock=threading.RLock();_locks[key]=lock
        return lock


def output_payload(result, profile="minimal"):
    answer = result.get("answer", "")
    sources = result.get("sources", []) if answer else []
    data = {"answer": answer, "sources": sources}
    if profile == "compat":
        data.update(citations=sources, source_url=sources[0] if sources else "", confidence=float(result.get("confidence", 0)))
    return data


def atomic_json(path, data):
    with _path_lock(path):
        _atomic_json(path,data)


def _atomic_json(path,data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        # Windows readers may briefly deny DELETE sharing; retry the atomic replace, never truncate.
        deadline=time.monotonic()+.8
        delay=.005
        while True:
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if os.name != "nt" or time.monotonic()>=deadline:
                    raise
                time.sleep(min(delay,max(0,deadline-time.monotonic())))
                delay=min(.05,delay*1.5)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def output_path(directory, qid):
    return Path(directory) / (f"{safe_id(qid)}_output.json" if qid is not None else "output.json")


def read_json(path):
    """Windows can expose a brief sharing violation while another process atomically replaces a file."""
    with _path_lock(path):
        deadline=time.monotonic()+.8
        delay=.005
        while True:
            try:
                return json.loads(Path(path).read_text(encoding="utf-8"))
            except PermissionError:
                if os.name != "nt" or time.monotonic()>=deadline:raise
                time.sleep(min(delay,max(0,deadline-time.monotonic())))
                delay=min(.05,delay*1.5)
