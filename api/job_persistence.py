"""Durable cloud job records; existing local JSON storage remains supported."""
from datetime import datetime, timezone
from contextlib import ExitStack
import threading
from config import USE_SUPABASE

_locks = {}
_locks_guard = threading.Lock()
_deleted = set()


def _job_lock(job_id):
    with _locks_guard:
        return _locks.setdefault(job_id, threading.RLock())


def client():
    from api.supabase_client import get_supabase_admin_client
    return get_supabase_admin_client()


def save_jobs(jobs):
    if not USE_SUPABASE:
        return
    with ExitStack() as stack:
        for job_id in sorted({job.job_id for job in jobs}):
            stack.enter_context(_job_lock(job_id))
        rows = [{'id': job.job_id, 'user_id': job.user_id, 'payload': job.model_dump(),
                 'updated_at': datetime.now(timezone.utc).isoformat()} for job in jobs
                if job.user_id and job.job_id not in _deleted]
        if rows:
            client().table('processing_jobs').upsert(rows).execute()


def save_job(job):
    save_jobs([job])


def restore_jobs():
    if not USE_SUPABASE:
        return []
    rows = client().table('processing_jobs').select('payload').order('updated_at', desc=True).limit(500).execute().data
    return [r['payload'] for r in rows]


def delete_job(job_id, user_id):
    if USE_SUPABASE and user_id:
        with _job_lock(job_id):
            client().table('processing_jobs').delete().eq('id', job_id).eq('user_id', user_id).execute()
            # An older worker checkpoint must not resurrect deleted history.
            _deleted.add(job_id)


def reconcile_video_jobs():
    if not USE_SUPABASE:
        return
    # Only startup invokes this, before this process accepts work. Retain notes
    # and transcripts so Retry can resume without downloading/transcribing again.
    client().table('video_tasks').update({'status': 'failed', 'error': 'Processing was interrupted by a server restart. Retry to continue from saved data.',
        'message': 'Interrupted — ready to retry', 'updated_at': datetime.now(timezone.utc).isoformat()}).in_('status',
        ['pending', 'parsing', 'downloading', 'transcribing', 'summarizing', 'saving']).execute()
