"""One language/editorial identity across parallel chunks and durable resumes."""
import hashlib
import inspect
import threading
import time
from functools import wraps

from reading_budget import VERSION


def generation_session(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        from reading_language import LANGUAGE, source_language
        values = inspect.signature(method).bind(self, *args, **kwargs).arguments
        transcript = values.get('transcript')
        source = getattr(transcript, 'text', '') or values.get('transcript_text', '')
        language = source_language(source, getattr(transcript, 'language', ''))
        token = LANGUAGE.set(language)
        from reading_budget import PLAN, make_plan, diagnostics
        plan = make_plan(source, getattr(transcript, 'duration', 0) or values.get('duration', 0), language, values.get('style', 'detailed'))
        budget_token = PLAN.set(plan)
        self.generation_report = {
            'prompt_version': VERSION, 'source_language': language,
            'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'model': self.model, 'model_options': dict(getattr(self, 'model_options', {})),
            'editor': {}, 'language': {},
        }
        self._generation_lock = threading.RLock()
        started = time.monotonic()
        try:
            result=method(self, *args, **kwargs)
            self.generation_report['generated']=bool(result)
            if result:
                try:
                    self.generation_report['reading'] = diagnostics(result, source, plan)
                except Exception:
                    # Optional telemetry must never fail an available summary.
                    self.generation_report['reading'] = {'measurement_failed': True}
            return result
        finally:
            self.generation_report['wall_seconds'] = round(time.monotonic() - started, 3)
            from processing_execution import CURRENT
            execution = CURRENT.get()
            if execution:
                with execution.lock:
                    execution.generation = dict(self.generation_report)
            PLAN.reset(budget_token)
            LANGUAGE.reset(token)
    return wrapped


def record_review(engine, complete, reason='', review=None):
    """Only bounded check names/counts, never transcript, key or provider text."""
    if not hasattr(engine,'_generation_lock'): return
    with engine._generation_lock:
        report=engine.generation_report.setdefault('coverage',{'reviewed':0,'retained':0})
        report['reviewed']+=1
        if not complete:
            report['retained']+=1
            reasons=report.setdefault('reasons',{})
            reasons[reason or 'unresolved_checks']=reasons.get(reason or 'unresolved_checks',0)+1
        if review is not None:
            recheck = getattr(review, 'receipt_recheck', {})
            for key in ('attempted', 'resolved'):
                if recheck.get(key):
                    name = 'receipt_recheck_' + key
                    report[name] = report.get(name, 0) + recheck[key]
            from source_coverage import AUDIT_ISSUES
            issues=report.setdefault('issues',{})
            for issue in set(getattr(review,'issues',[])):
                if issue in AUDIT_ISSUES:
                    issues[issue]=issues.get(issue,0)+1
            report['unverified_units']=report.get('unverified_units',0)+len(getattr(review,'unverified_units',[]))
            report['identified_gap_units']=report.get('identified_gap_units',0)+len(getattr(review,'identified_gaps',{}))
