"""Resume coverage checks of an immutable saved video note and source snapshot."""
import json
import time

from processing_execution import fingerprint
from scripts.complete_saved_coverage import remove_audit_notice, review_document, saved_media_scope
from summary_errors import _leading_notices, _EN_NOTICES, AUDIT_WARNING


def needs_review(markdown):
    notices, _ = _leading_notices(markdown or '')
    return bool(set(notices) & {AUDIT_WARNING, _EN_NOTICES['audit']})


def saved_transcript(task):
    """Storage adapters expose parsed transcript, while maintenance reads raw JSON."""
    value = task.get('transcript') or task.get('transcript_json') or {}
    value = json.loads(value) if isinstance(value,str) else value
    return value if isinstance(value,dict) else {}


def snapshot_key(task):
    return fingerprint({'version':1, 'markdown':task.get('markdown'),
                        'source':saved_transcript(task), 'duration':task.get('duration')})


def review_saved_note(db, task_id, owner, expected, update, check, media_warning=''):
    from execution_store import get_store
    from api.user_settings import get_user_settings
    from api.llm_settings import resolve_llm_settings
    from note_summarizer import NoteSummarizer
    from processing_execution import CURRENT, assert_lease
    from source_coverage import video_source_text
    task = db.get_task(task_id, owner)
    if not task or snapshot_key(task) != expected:
        raise ValueError('The saved note or transcript changed. Reload before restarting its review.')
    transcript = saved_transcript(task)
    if saved_media_scope(transcript, task.get('duration'))['requires_source_resolution']:
        raise ValueError('The saved transcript does not span the recorded duration. Check the source before retrying coverage.')
    source = video_source_text(transcript.get('text') or '', transcript.get('segments') or [])
    if not source.strip() or not needs_review(task.get('markdown')):
        raise ValueError('A saved transcript and an unfinished coverage review are required.')
    store = get_store()
    source_id, stage = 'saved-coverage:video:'+task_id, 'saved.coverage.v1'
    resume = store.get_checkpoint(owner, source_id, stage, expected)
    attempt = (resume or {}).get('attempt', 0) + 1
    engine = NoteSummarizer(**resolve_llm_settings(get_user_settings(owner)))
    engine._reading_source = source
    position = [0, 1]
    last_update = [0.0]
    def progress(done, total):
        check()
        position[:] = [done, total]
        update(5 + 88 * done / total, f'Coverage review · {done}/{total} source sections reviewed')
        last_update[0] = time.monotonic()
    def call(system, payload, timeout):
        check()
        if time.monotonic()-last_update[0] >= 2:
            progress(*position)
        result = engine._editorial_json(system+f'\nSaved coverage review attempt {attempt}.', payload, timeout)
        check()
        return result
    def checkpoint(result):
        check()
        store.put_checkpoint(owner, source_id, stage, expected, {**result, 'attempt':attempt})
    try:
        checkpoint(resume or {'checks':[], 'additions':[]})
        result = review_document(source, {'body':remove_audit_notice(task['markdown'])}, call,
            deadline=time.monotonic()+2400, resume=resume, checkpoint=checkpoint, progress=progress)
        check()
        checkpoint(result)
        execution = CURRENT.get()
        if execution:
            execution.generation = {'saved_coverage':{key:result[key] for key in ('complete','source_chunks','resumed_chunks')},
                'verification_scope':'saved_transcript_only', 'semantic_proof':False}
        if not result['complete']:
            raise ValueError('Coverage review is still incomplete. Your saved note is unchanged; retry to resume completed sections.')
        # A reviewer may add independently grounded details; it cannot rewrite
        # existing prose, remove media, or clear other delivery warnings.
        markdown = remove_audit_notice(task['markdown'])
        if result['additions']:
            markdown += '\n\n## Coverage additions\n\n' + '\n\n'.join(
                '### '+addition['topic']+'\n\n'+addition['summary']+'\n\n'+
                '\n'.join('> '+line for line in addition['original_quote'].splitlines())
                for addition in result['additions'])
        check()
        current = db.get_task(task_id, owner)
        if not current or snapshot_key(current) != expected:
            raise ValueError('The saved note changed during review. The newer note was kept.')
        assert_lease()
        update(96, 'Coverage review complete · saving reviewed note')
        db.complete_task(task_id, markdown, task.get('style') or 'detailed', task.get('model') or '',
                         owner, media_warning)
    finally:
        engine.client.close()
