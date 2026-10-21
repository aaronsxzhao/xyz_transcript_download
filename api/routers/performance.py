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
    visit_id: str = Field(default='', max_length=64, pattern=r'^[a-zA-Z0-9_-]*$')
    navigation: Literal['document', 'navigation', 'unknown'] = 'unknown'
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
    return {'pages': aggregate(records)}


def aggregate(records):
    # A timeout warning and later success describe one visit, not two samples.
    visits = {}
    for index, row in enumerate(records):
        key = (row['page'], row.get('visit_id') or f'legacy-{index}', 'image' if row.get('stage') == 'image' else 'page')
        previous = visits.get(key)
        rank = lambda value: (value.get('outcome') == 'ready', value.get('stage') == 'content', value.get('outcome') == 'error')
        if previous is None or rank(row) >= rank(previous):
            visits[key] = row
    pages = {}
    for page in {r['page'] for r in records}:
        all_rows = [r for (name, _, _), r in visits.items() if name == page]
        rows = [r for r in all_rows if r.get('stage') != 'image']
        if not rows:
            continue
        success = [r for r in rows if r.get('outcome', 'ready') == 'ready']
        errors = sum(r.get('outcome') == 'error' for r in rows)
        groups = {}
        for navigation in ('document', 'navigation', 'unknown'):
            for cached in (True, False):
                group = [r for r in rows if r.get('navigation', 'unknown') == navigation and r.get('cached', False) == cached]
                if group:
                    groups[f'{navigation}:{"cache" if cached else "network"}'] = {'samples': len(group), 'errors': sum(r.get('outcome') == 'error' for r in group), **percentiles([r for r in group if r.get('outcome', 'ready') == 'ready'])}
        pages[page] = {**rows[-1], 'samples': len(rows), 'worst_ms': max((r['elapsed_ms'] for r in success), default=0),
                       'error_count': errors, 'failure_rate': errors / len(rows),
                       'slow_count': sum(r.get('outcome') == 'slow' for r in rows), **percentiles(success),
                       'groups': groups,
                       'stages': {stage: percentiles([r for r in all_rows if r.get('stage','application') == stage and r.get('outcome','ready') == 'ready']) for stage in {r.get('stage','application') for r in all_rows}}}
        if not success:
            pages[page].pop('p50_ms', None)
            pages[page].pop('p95_ms', None)
    return pages
