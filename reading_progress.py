"""Actual completed work within estimated overall summary-stage weights."""
import time
STAGES = {
    'draft': (0.0, .30), 'grounding': (.30, .42),
    'inventory': (.42, .68), 'coverage': (.68, .98),
    'repair': (.68, .98), 'recheck': (.68, .98), 'render': (.98, 1.0),
}


def stage(callback, name, completed=0, total=1, *, mode='single', fraction=None):
    if callback is None:
        return
    total=max(1,total)
    completed=max(0,min(completed,total))
    ratio=completed/total if fraction is None else max(0,min(1,fraction))
    lo,hi=STAGES[name]
    labels={
        'draft': 'Writing full-transcript summary' if mode=='single' else f'Writing sections · {completed}/{total} finished',
        'grounding': f'Checking source accuracy · {completed}/{total} checks finished',
        'inventory': f'Building coverage checklist · {completed}/{total} source sections checked',
        'coverage': f'Checking coverage · {completed}/{total} items checked',
        'repair': f'Filling missing details · {completed}/{total} items checked',
        'recheck': f'Verifying additions · {completed}/{total} items checked',
        'render': 'Preparing the final summary',
    }
    callback({'stage':name,'completed':completed,'total':total,
              'fraction':lo+(hi-lo)*ratio,'message':labels[name]})


class SummaryProgress:
    """Broadcast stage changes even if rounded overall percent is unchanged."""
    def __init__(self, update, start, end, check=lambda: None):
        self.update=update
        self.start=start
        self.end=end
        self.check=check
        self.value=start
        self.message='Preparing summary'
        self.stage_message=self.message
        self.stream_chars=0
        self.stream_reported_at=0.0

    def stage(self, event):
        self.check()
        value=max(self.value,min(self.end,self.start+(self.end-self.start)*event['fraction']))
        message=event['message']
        self.stage_message=message
        self.stream_chars=0
        self.stream_reported_at=0.0
        if value!=self.value or message!=self.message:
            self.value=value
            self.message=message
            self.update(value,message)


    def stream(self, chars):
        """Output is evidence of activity, not a known fraction of total work."""
        self.check()
        if not isinstance(chars, (int, float)) or chars <= 0:
            return
        now=time.monotonic()
        if now-self.stream_reported_at < .5:
            return
        if chars >= self.stream_chars + 256 or chars < self.stream_chars:
            self.stream_reported_at=now
            self.stream_chars=chars
            self.message=f'{self.stage_message} · Receiving output: {int(chars):,} characters'
            self.update(self.value,self.message)


class MeasuredProgress(float):
    """Float-compatible progress carrying the real work behind the fraction."""
    def __new__(cls, completed, total, unit='seconds'):
        total = max(0, float(total))
        completed = max(0, min(float(completed), total))
        obj = super().__new__(cls, completed / total if total else 0)
        obj.completed, obj.total, obj.unit = completed, total, unit
        return obj


def transcription_message(progress):
    if isinstance(progress, MeasuredProgress):
        if progress.unit == 'chunks':
            return f'Transcribing audio · {int(progress.completed)}/{int(progress.total)} segments finished'
        def clock(seconds):
            return f'{int(seconds) // 60}:{int(seconds) % 60:02d}'
        return f'Transcribing audio · {clock(progress.completed)} / {clock(progress.total)} processed'
    if progress <= 0:
        return 'Waiting for transcription results · progress updates when the service responds'
    return f'Transcribing audio · {min(100, int(progress * 100))}% of this stage processed'
