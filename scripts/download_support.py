"""Process-safe local download bookkeeping. No platform-specific accelerator code."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import time


def atomic_json(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=path.name, suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def file_lock(path, timeout=7200):
    """OS releases the lock on process death; a leftover pathname never blocks resume."""
    with Path(str(path)+'.lock').open('a+b') as stream:
        stream.seek(0, 2)
        if not stream.tell():
            stream.write(b'0'); stream.flush()
        limit = time.monotonic()+timeout
        while True:
            try:
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= limit:
                    raise TimeoutError('Download is owned by another process: '+str(path))
                time.sleep(.2)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def resume_parts(marker, partial, size, count, chunk=4*1024*1024):
    if not partial.exists() or partial.stat().st_size != size:
        return set()
    try:
        state = json.loads(marker.read_text(encoding='utf-8'))
        old_chunk=state.get('chunk_bytes',4*1024*1024) if isinstance(state,dict) else 4*1024*1024
        parts=state.get('parts',[]) if isinstance(state,dict) else state
        if type(old_chunk) is not int or old_chunk<=0:return set()
        if isinstance(parts,list) and all(type(i) is int and 0<=i<(size+old_chunk-1)//old_chunk for i in parts):
            old=set(parts)
            return {i for i in range(count) if all(j in old for j in range(i*chunk//old_chunk,(min(size,(i+1)*chunk)-1)//old_chunk+1))}
    except (OSError, ValueError):
        pass
    return set()
