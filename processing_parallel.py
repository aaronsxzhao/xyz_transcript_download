"""Bounded independent work with inherited execution and cooperative cancellation."""
import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextlib import contextmanager

_STOPS = contextvars.ContextVar('parallel_stops', default=())
_MODEL_SLOTS = threading.BoundedSemaphore(4)
_OWNER_LOCK = threading.Lock()
_OWNER_SLOTS = {}


def check_cancelled():
    from processing_execution import CURRENT
    from summary_errors import ProcessingCancelledError
    if any(stop.is_set() for stop in _STOPS.get()):
        raise ProcessingCancelledError('Parallel work stopped')
    execution = CURRENT.get()
    if execution:
        execution.check()


@contextmanager
def background_work(function):
    """Join owned work before unwinding, so it cannot outlive its source/session."""
    stop = threading.Event()
    token = _STOPS.set((*_STOPS.get(), stop))
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='source_inventory')
    future = pool.submit(contextvars.copy_context().run, function)
    try:
        yield future
    finally:
        stop.set()
        future.cancel()
        pool.shutdown(wait=True, cancel_futures=True)
        _STOPS.reset(token)


def bounded_map(function, items, workers=2, stop_when=None):
    """At most workers submitted; completion order never changes source order."""
    items = iter(enumerate(items))
    results = {}
    pending = {}
    stop = threading.Event()
    token = _STOPS.set((*_STOPS.get(), stop))
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='source_inventory_batch')
    def submit():
        check_cancelled()
        item = next(items, None)
        if item is not None:
            index, value = item
            pending[pool.submit(contextvars.copy_context().run, function, value)] = index
    try:
        for _ in range(workers):
            submit()
        halted = False
        while pending:
            check_cancelled()
            completed, _ = wait(pending, timeout=.1, return_when=FIRST_COMPLETED)
            for future in completed:
                index = pending.pop(future)
                value = future.result()
                results[index] = value
                halted |= bool(stop_when and stop_when(value))
            if not halted:
                for _ in completed:
                    submit()
        return [results[index] for index in sorted(results)]
    finally:
        stop.set()
        for future in pending:
            future.cancel()
        pool.shutdown(wait=True, cancel_futures=True)
        _STOPS.reset(token)


@contextmanager
def model_slot():
    """Process-wide cap plus a shared per-owner cap across that owner's tasks.

    These are per-process limits, not a distributed provider quota manager.
    Streaming/legacy clients are outside this gate; current JSON and vision
    generation use it. No credential values are used as registry keys.
    """
    from processing_execution import CURRENT
    execution = CURRENT.get()
    owner = execution.owner if execution else 'local'
    with _OWNER_LOCK:
        entry = _OWNER_SLOTS.setdefault(owner, [threading.BoundedSemaphore(3), 0])
        entry[1] += 1
    acquired = []
    try:
        for semaphore in (entry[0], _MODEL_SLOTS):
            while not semaphore.acquire(timeout=.1):
                check_cancelled()
            acquired.append(semaphore)
            check_cancelled()
        yield
    finally:
        for semaphore in reversed(acquired):
            semaphore.release()
        with _OWNER_LOCK:
            entry[1] -= 1
            if not entry[1]:
                _OWNER_SLOTS.pop(owner, None)
