"""Bounded, account-scoped page timings; no URLs, content, or client identifiers."""
from collections import OrderedDict, deque
from typing import Literal
from fastapi import APIRouter, Depends, BackgroundTasks
from api import performance_store
import logging
import math
import time
from pydantic import BaseModel, Field
from api.auth import User, get_current_user

router = APIRouter()
_samples = OrderedDict()


class PageTiming(BaseModel):
    page: Literal["library", "dashboard", "podcasts", "videos", "channel", "episodes", "viewer", "video_note", "settings"]
    stage: Literal['application', 'bootstrap', 'content', 'image'] = 'application'
    program_embedded: bool = False
    module_requests: int = Field(default=0, ge=0, le=1000)
    module_failures: int = Field(default=0, ge=0, le=1000)
    script_errors: int = Field(default=0, ge=0, le=1000)
    elapsed_ms: int = Field(ge=0, le=300000)
    first_paint_ms: int = Field(default=0, ge=0, le=300000)
    document_ms: int = Field(ge=0, le=300000)
    api_ms: int = Field(ge=0, le=300000)
    server_ms: int = Field(default=0, ge=0, le=300000)
    outcome: Literal['ready', 'slow', 'error'] = 'ready'
    cached: bool

    class Config:
        extra = "forbid"


def persist(owner, sample):
    try: performance_store.append(owner, sample)
    except Exception: logging.getLogger(__name__).warning('Performance persistence unavailable')


def percentiles(rows):
    elapsed = sorted(row['elapsed_ms'] for row in rows)
    return {f'p{p}_ms': elapsed[max(0, math.ceil(len(elapsed)*p/100)-1)] for p in (50,95)} if elapsed else {}


@router.post("", status_code=204)
async def record_timing(timing: PageTiming, background_tasks: BackgroundTasks, user: User = Depends(get_current_user)):
    records = _samples.setdefault(user.id, deque(maxlen=64))
    sample = {**timing.model_dump(), "recorded_at": int(time.time())}
    records.append(sample)
    background_tasks.add_task(persist, user.id, sample)
    _samples.move_to_end(user.id)
    while len(_samples) > 128:
        _samples.popitem(last=False)


@router.get("")
def get_timings(user: User = Depends(get_current_user)):
    # Return only this account's latest measurements, aggregated by fixed page.
    try: records = performance_store.read(user.id)
    except Exception: records = list(_samples.get(user.id, []))
    pages = {}
    for page in {r['page'] for r in records}:
        all_rows = [r for r in records if r['page'] == page]
        rows = [r for r in all_rows if r.get('stage') != 'image'] or all_rows
        elapsed = sorted(r['elapsed_ms'] for r in rows)
        pages[page] = {**rows[-1], 'samples': len(rows), 'worst_ms': elapsed[-1],
                       'error_count': sum(r['outcome'] == 'error' for r in rows),
                       'slow_count': sum(r['outcome'] == 'slow' for r in rows), **percentiles(rows),
                       'stages': {stage: percentiles([r for r in all_rows if r.get('stage','application') == stage]) for stage in {r.get('stage','application') for r in all_rows}}}
    return {'pages': pages}
