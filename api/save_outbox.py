"""Immutable, generation-scoped recovery copies; legacy copies stay readable."""
import hashlib
import json
import os
import tempfile
import time
from config import DATA_DIR, USE_SUPABASE

ROOT = DATA_DIR / 'pending_note_saves'


def _scope(user_id, task_id):
    # Encode identities rather than allowing identifiers to become paths.
    return hashlib.sha256(json.dumps([user_id, task_id]).encode()).hexdigest()


def _encoded(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()


def _location(payload):
    scope = _scope(payload['user_id'], payload['task_id'])
    name = hashlib.sha256(_encoded(payload)).hexdigest() + '.json'
    return ROOT / 'v2' / scope / name, f'pending-v2/{scope}/{name}'


def retain(payload):
    # Set before storage I/O. A delayed upload must not become a newer result.
    payload.setdefault('backup_created_at', time.time_ns())
    content = _encoded(payload)
    path, key = _location(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)  # Atomic create, never replace another copy.
        except FileExistsError:
            if path.read_bytes() != content:
                raise ValueError('Recovery copy identity conflict')
    finally:
        os.unlink(temporary)
    if USE_SUPABASE:
        from api.supabase_client import get_supabase_admin_client
        bucket = get_supabase_admin_client().storage.from_('application-backups')
        try:
            bucket.upload(key, content, file_options={'content-type': 'application/json', 'upsert': 'false'})
        except Exception:
            # A repeated upload is successful only if this exact object exists.
            if bucket.download(key) != content:
                raise ValueError('Recovery copy was not confirmed')


def clear(payload):
    # Legacy keys are shared by every attempt: never remove them here.
    if 'backup_created_at' not in payload:
        return
    path, key = _location(payload)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    if USE_SUPABASE:
        from api.supabase_client import get_supabase_admin_client
        try:
            get_supabase_admin_client().storage.from_('application-backups').remove([key])
        except Exception:
            pass  # Cleanup cannot undo an already confirmed commit.


def pending(user_id, task_id):
    scope = _scope(user_id, task_id)
    candidates = {}

    def add(content):
        payload = json.loads(content)
        if payload.get('user_id') != user_id or payload.get('task_id') != task_id:
            raise ValueError('Pending note belongs to another account')
        candidates[hashlib.sha256(_encoded(payload)).hexdigest()] = payload

    for path in (ROOT / 'v2' / scope).glob('*.json'):
        try:
            add(path.read_bytes())
        except FileNotFoundError:
            pass  # Concurrent cleanup of this exact completed generation.
    legacy = ROOT / (task_id + '.json')
    if legacy.exists():
        add(legacy.read_bytes())
    if USE_SUPABASE:
        from api.supabase_client import get_supabase_admin_client
        bucket = get_supabase_admin_client().storage.from_('application-backups')
        try:
            offset = 0
            while True:
                rows = bucket.list(f'pending-v2/{scope}', {'limit': 100, 'offset': offset,
                                                        'sortBy': {'column': 'name', 'order': 'asc'}})
                for row in rows:
                    name = row.get('name', '')
                    if len(name) == 69 and name.endswith('.json') and all(c in '0123456789abcdef' for c in name[:-5]):
                        add(bucket.download(f'pending-v2/{scope}/{name}'))
                if len(rows) < 100:
                    break
                offset += len(rows)
        except Exception:
            # Local or legacy copies remain recoverable during a storage outage.
            # The final transaction still rejects a superseded candidate.
            pass
        try:
            add(bucket.download(f'pending/{user_id}/{task_id}.json'))
        except Exception:
            pass
    if not candidates:
        raise ValueError('No pending recovery copy')

    # Queue identity, not upload arrival time, decides which attempt is current.
    from execution_store import enabled, get_store
    work = get_store().latest(user_id, 'video', task_id) if enabled() else None
    values = list(candidates.values())
    if work:
        matching = [p for p in values if (p.get('recovery_order') or {}).get('work_id') == work['id']
                    and (p.get('recovery_order') or {}).get('work_attempt') == work['attempts']]
        if matching:
            values = matching
    # The transaction in recover_note remains the authority: superseded and
    # legacy/unverified copies are retained, never promoted by this selection.
    return max(values, key=lambda p: (p.get('backup_created_at', 0), p.get('version_id', '')))
