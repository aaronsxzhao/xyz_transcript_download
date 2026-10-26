"""One language/editorial identity across parallel chunks and durable resumes."""
import hashlib
import inspect
import threading
from functools import wraps

VERSION = 'argument-reading-v1'


def generation_session(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        from reading_language import LANGUAGE, source_language
        values = inspect.signature(method).bind(self, *args, **kwargs).arguments
        transcript = values.get('transcript')
        source = getattr(transcript, 'text', '') or values.get('transcript_text', '')
        language = source_language(source, getattr(transcript, 'language', ''))
        token = LANGUAGE.set(language)
        self.generation_report = {
            'prompt_version': VERSION, 'source_language': language,
            'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'model': self.model, 'model_options': dict(getattr(self, 'model_options', {})),
            'editor': {}, 'language': {},
        }
        self._generation_lock = threading.RLock()
        try:
            result=method(self, *args, **kwargs)
            self.generation_report['generated']=bool(result)
            return result
        finally:
            from processing_execution import CURRENT
            execution = CURRENT.get()
            if execution:
                with execution.lock:
                    execution.generation = dict(self.generation_report)
            LANGUAGE.reset(token)
    return wrapped


def record_review(engine, complete, reason=''):
    """Only bounded check names/counts, never transcript, key or provider text."""
    if not hasattr(engine,'_generation_lock'): return
    with engine._generation_lock:
        report=engine.generation_report.setdefault('coverage',{'reviewed':0,'retained':0})
        report['reviewed']+=1
        if not complete:
            report['retained']+=1
            reasons=report.setdefault('reasons',{})
            reasons[reason or 'unresolved_checks']=reasons.get(reason or 'unresolved_checks',0)+1
