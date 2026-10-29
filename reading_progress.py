"""Actual completed work within estimated overall summary-stage weights."""
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

    def stage(self, event):
        self.check()
        value=max(self.value,min(self.end,self.start+(self.end-self.start)*event['fraction']))
        message=event['message']
        if value!=self.value or message!=self.message:
            self.value=value
            self.message=message
            self.update(value,message)
