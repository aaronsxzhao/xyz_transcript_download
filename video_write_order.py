"""Serialize one task's local writes without blocking unrelated tasks.

Database-side ordering and lease checks remain authoritative across processes.
"""
import threading
from functools import wraps

_guard = threading.Lock()
_locks = {}


def serialized_video_write(method):
    @wraps(method)
    def wrapped(self, task_id, *args, **kwargs):
        with _guard:
            entry = _locks.setdefault(task_id, [threading.RLock(), 0])
            entry[1] += 1
        try:
            with entry[0]:
                return method(self, task_id, *args, **kwargs)
        finally:
            with _guard:
                entry[1] -= 1
                if not entry[1]:
                    del _locks[task_id]
    return wrapped
