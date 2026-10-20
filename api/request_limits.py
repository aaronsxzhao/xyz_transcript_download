"""Bounded per-account request limits; independent of provider pricing tiers."""
import time
import threading
from collections import OrderedDict
from fastapi import HTTPException

_records = OrderedDict()
_lock = threading.Lock()


def check_limit(key, maximum=30, window=3600):
    now = time.monotonic()
    with _lock:
        recent = [t for t in _records.get(key, []) if t > now - window]
        if len(recent) >= maximum:
            raise HTTPException(status_code=429, detail='Too many requests. Please wait before trying again.', headers={'Retry-After': str(max(1, int(window - (now - recent[0]))))})
        _records[key] = [*recent, now]
        _records.move_to_end(key)
        while len(_records) > 4096:
            _records.popitem(last=False)
