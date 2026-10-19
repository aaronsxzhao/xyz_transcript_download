"""Bounded, account-scoped page timings; no URLs, content, or client identifiers."""
from collections import OrderedDict, deque
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from api.auth import User, get_current_user

router = APIRouter()
_samples = OrderedDict()


class PageTiming(BaseModel):
    page: Literal["dashboard", "podcasts", "videos", "channel", "episodes", "viewer", "video_note", "settings"]
    elapsed_ms: int = Field(ge=0, le=300000)
    document_ms: int = Field(ge=0, le=300000)
    api_ms: int = Field(ge=0, le=300000)
    server_ms: int = Field(default=0, ge=0, le=300000)
    outcome: Literal['ready', 'slow', 'error'] = 'ready'
    cached: bool

    class Config:
        extra = "forbid"


@router.post("", status_code=204)
async def record_timing(timing: PageTiming, user: User = Depends(get_current_user)):
    records = _samples.setdefault(user.id, deque(maxlen=64))
    records.append(timing.model_dump())
    _samples.move_to_end(user.id)
    while len(_samples) > 128:
        _samples.popitem(last=False)


@router.get("")
async def get_timings(user: User = Depends(get_current_user)):
    # Return only this account's latest measurements, aggregated by fixed page.
    records = list(_samples.get(user.id, []))
    pages = {}
    for page in {r['page'] for r in records}:
        rows = [r for r in records if r['page'] == page]
        elapsed = sorted(r['elapsed_ms'] for r in rows)
        pages[page] = {**rows[-1], 'samples': len(rows), 'worst_ms': elapsed[-1],
                       'error_count': sum(r['outcome'] == 'error' for r in rows),
                       'slow_count': sum(r['outcome'] == 'slow' for r in rows)}
    return {'pages': pages}
