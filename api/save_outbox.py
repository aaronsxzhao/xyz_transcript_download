"""Recoverable final-note saves, separate from processing status."""
import json
import os
from config import DATA_DIR, USE_SUPABASE

ROOT = DATA_DIR / 'pending_note_saves'


def retain(payload):
    ROOT.mkdir(parents=True, exist_ok=True)
    path = ROOT / (payload['task_id'] + '.json')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload), encoding='utf-8')
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    if USE_SUPABASE:
        from api.supabase_client import get_supabase_admin_client
        get_supabase_admin_client().storage.from_('application-backups').upload(
            f"pending/{payload['user_id']}/{payload['task_id']}.json", path.read_bytes(),
            file_options={'content-type': 'application/json', 'upsert': 'true'})


def clear(payload):
    try:
        (ROOT / (payload['task_id'] + '.json')).unlink(missing_ok=True)
    except OSError:
        pass  # Cleanup failure cannot undo an already confirmed database commit.
    if USE_SUPABASE:
        from api.supabase_client import get_supabase_admin_client
        try:
            get_supabase_admin_client().storage.from_('application-backups').remove([f"pending/{payload['user_id']}/{payload['task_id']}.json"])
        except Exception:
            pass


def pending(user_id, task_id):
    payload = None
    if USE_SUPABASE:
        from api.supabase_client import get_supabase_admin_client
        try:
            content = get_supabase_admin_client().storage.from_('application-backups').download(f'pending/{user_id}/{task_id}.json')
            payload = json.loads(content)
        except Exception:
            pass
    if payload is None:
        payload = json.loads((ROOT / (task_id + '.json')).read_text())
    if payload.get('user_id') != user_id or payload.get('task_id') != task_id:
        raise ValueError('Pending note belongs to another account')
    return payload
