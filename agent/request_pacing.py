"""A shared crates.io API admission slot, including independent query workers."""
import asyncio
from contextlib import asynccontextmanager
import errno
import math
import os
from pathlib import Path
import struct
import time
from urllib.parse import unquote, urlsplit
import zlib


INTERVAL = 1.05


def paced(url):
    parsed = urlsplit(url)
    return (parsed.hostname in {'crates.io', 'www.crates.io'}
            and unquote(parsed.path).startswith('/api/'))


def _try_lock(file):
    file.seek(0)
    if os.name == 'nt':
        import msvcrt
        try:
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                return False
            raise
    else:
        import fcntl
        try:
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
    return True


def _pause(record):
    if not record:
        return 0
    # A partial write, an old format or a clock reset costs one full interval.
    # The OS lock establishes that no other owner is still using this slot.
    if len(record) != 16 or record[:3] != b'AP2' or record[3:4] not in {b'A', b'D'}:
        return INTERVAL
    payload = record[:12]
    if struct.unpack('!I', record[12:])[0] != zlib.crc32(payload):
        return INTERVAL
    # An owner killed in flight never recorded when its last network activity
    # happened. Cool down from recovery even if admission was a long time ago.
    if record[3:4] == b'A':
        return INTERVAL
    stamp = struct.unpack('!d', record[4:12])[0]
    now = time.monotonic()
    if not math.isfinite(stamp) or not 0 <= stamp <= now:
        return INTERVAL
    return max(0, INTERVAL - (now - stamp))


def _mark(file, active=False):
    payload = b'AP2' + (b'A' if active else b'D') + struct.pack('!d', time.monotonic())
    record = payload + struct.pack('!I', zlib.crc32(payload))
    file.seek(0)
    if file.write(record) != len(record):
        raise OSError('Incomplete API pacing record')
    file.truncate(len(record))


@asynccontextmanager
async def crates_slot():
    """Hold the OS lock through the response, then leave a shared cooldown.

    The caller's timeout includes all waits. Closing the descriptor releases
    the lock on cancellation or process termination, without stale PID locks.
    The file must never be deleted while workers use this state directory.
    """
    default = Path(__file__).resolve().parents[1] / '.state' if os.name == 'nt' else Path('/tmp/aperture')
    state = Path(os.getenv('APERTURE_STATE', str(default)))
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(state / 'crates-api.pacing', os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'r+b', buffering=0) as file:
        admitted = False
        try:
            while not _try_lock(file):
                await asyncio.sleep(.025)
            file.seek(0)
            pause = _pause(file.read(32))
            if pause:
                await asyncio.sleep(pause)
            # Persist admission before starting HTTP, including a worker killed
            # before it could record response completion.
            _mark(file, active=True)
            admitted = True
            yield
        finally:
            if admitted:
                _mark(file)
