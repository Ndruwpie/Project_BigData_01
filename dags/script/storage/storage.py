"""Atomic JSON writes with flushed data and a validated previous snapshot."""

import sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import json
import os
import tempfile
import time
from contextlib import contextmanager


@contextmanager
def crawler_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            acquire = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(handle, fcntl.LOCK_UN)
        try:
            acquire()
        except OSError as error:
            raise RuntimeError('Crawler lain masih berjalan untuk dataset ini.') from error
        try:
            yield
        finally:
            handle.seek(0)
            release()


def _replace_bytes(path, data):
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(10):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(min(attempt + 1, 5))
    finally:
        if temporary.exists():
            temporary.unlink()


def save_json(path, value):
    path = Path(path)
    data = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        old = path.read_bytes()
        # Do not overwrite a good backup with corrupt data.
        try:
            json.loads(old.decode('utf-8-sig'))
        except (ValueError, UnicodeError) as error:
            raise ValueError(f'File {path} rusak; pulihkan sebelum menyimpan.') from error
        _replace_bytes(path.with_suffix(path.suffix + '.bak'), old)
    _replace_bytes(path, data)
