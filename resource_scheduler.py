"""One bounded task queue; CPU-heavy media commands have separate admission."""
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from pathlib import Path
import subprocess
NETWORK_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix='media_network')
TASK_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='content_processor')
_MEDIA = BoundedSemaphore(1)

def run_media_process(command, **kwargs):
    program = Path(str(command[0])).name.lower() if command else ''
    if 'ffmpeg' in program:
        with _MEDIA:
            return subprocess.run(command, **kwargs)
    return subprocess.run(command, **kwargs)

from collections import OrderedDict
import time
from threading import Lock
_TIMES = OrderedDict()
_TIME_LOCK = Lock()

def start_task(kind, ident):
    with _TIME_LOCK:
        _TIMES[(kind, ident)] = time.time()
        _TIMES.move_to_end((kind, ident))
        while len(_TIMES)>2048: _TIMES.popitem(last=False)

def task_started_at(kind, ident):
    with _TIME_LOCK:
        return _TIMES.get((kind, ident), 0)
