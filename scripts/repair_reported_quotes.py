"""Restore reviewed source excerpts without regenerating the reported notes.

The public manifest contains only hashes and reviewed segment ranges. All source
text, saved notes and rollback receipts stay in verified private storage.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.repair_source_coverage import BUCKET, digest, main, verified_upload


def segment_digest(segments):
    return digest([{'start': float(s['start']), 'end': float(s['end']), 'text': s['text']}
                   for s in segments])


def quote_updates(source, rows, plan):
    """Resolve reviewed ranges to exact saved-source substrings, never guesses."""
    if (hashlib.md5(source.text.encode()).hexdigest() != plan['source_md5']
            or segment_digest(source.segments) != plan['segments_sha256']):
        raise RuntimeError('Reviewed source changed')
    positions = [i for i, c in enumerate(source.text) if not c.isspace()]
    compact = ''.join(source.text[i] for i in positions)
    segments = source.segments
    texts = [''.join(s['text'].split()) for s in segments]
    if ''.join(texts) != compact:
        raise RuntimeError('Saved segments do not cover the source')
    offsets = [0]
    for text in texts:
        offsets.append(offsets[-1] + len(text))
    keyed = {hashlib.sha256(row['summary'].encode()).hexdigest(): row for row in rows}
    if len(keyed) != len(rows) or set(keyed) != {p['point_sha256'] for p in plan['points']}:
        raise RuntimeError('Reviewed note changed')
    updates = []
    for item in plan['points']:
        first, end = item['segments']
        if not 0 <= first < end <= len(segments) or offsets[first] == offsets[end]:
            raise RuntimeError('Invalid reviewed range')
        quote = source.text[positions[offsets[first]]:positions[offsets[end] - 1] + 1]
        seconds = int(segments[first]['start'])
        timestamp = f'{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}'
        row = keyed[item['point_sha256']]
        # Idempotent resume after a partial repair; never overwrite another edit.
        if row.get('original_quote'):
            if row['original_quote'] == quote and row.get('timestamp') == timestamp:
                continue
            raise RuntimeError('Existing quote differs from reviewed repair')
        updates.append((row, {'original_quote': quote, 'timestamp': timestamp}))
    return updates


def repair():
    from api.supabase_db import SupabaseDatabase
    from dataclasses import asdict
    db = SupabaseDatabase()
    bucket = db.client.storage.get_bucket(BUCKET)
    public = bucket.get('public', False) if isinstance(bucket, dict) else bucket.public
    if public:
        raise RuntimeError('Repair backup bucket must be private')
    storage = db.client.storage.from_(BUCKET)
    plans = json.loads(Path(__file__).with_name('reported_quote_spans.json').read_text())
    report = {'operation': 'restore_verbatim_quotes', 'repaired': 0, 'already_repaired': 0}
    for plan in plans:
        sid, eid = plan['summary_id'], plan['episode_id']
        records = db.client.table('summaries').select('*').eq('id', sid).eq('episode_id', eid).execute().data
        if len(records) != 1:
            raise RuntimeError('Reported note unavailable')
        original = records[0]
        owner = original['user_id']
        source = db.get_transcript(owner, eid)
        rows = db.client.table('summary_key_points').select('*').eq('summary_id', sid).execute().data
        updates = quote_updates(source, rows, plan)
        if not updates:
            report['already_repaired'] += len(rows)
            continue
        active = (db.client.table('processing_jobs').select('id').eq('user_id', owner)
                  .eq('payload->>episode_id', eid).in_('payload->>status',
                  ['pending', 'fetching', 'downloading', 'transcribing', 'summarizing']).execute().data)
        if active:
            raise RuntimeError('Reported note has an active processing task')
        prefix = f"quote-repairs/{owner}/{eid}/{os.environ.get('GITHUB_RUN_ID', 'manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
        verified_upload(storage, prefix + '/before.json', {
            'summary': original, 'key_points': rows, 'source': asdict(source), 'plan': plan})
        if digest(asdict(db.get_transcript(owner, eid))) != digest(asdict(source)):
            raise RuntimeError('Source changed during repair')
        for row, patch in updates:
            query = (db.client.table('summary_key_points').update(patch).eq('id', row['id'])
                     .eq('summary_id', sid).eq('summary', row['summary']))
            for field in ('original_quote', 'timestamp'):
                query = query.is_(field, 'null') if row.get(field) is None else query.eq(field, row[field])
            saved = query.execute().data
            if len(saved) != 1 or any(saved[0].get(k) != v for k, v in patch.items()):
                raise RuntimeError('Quote update conflicted; backup retained')
        after = db.client.table('summary_key_points').select('*').eq('summary_id', sid).execute().data
        expected = {row['id']: {**row, **patch} for row, patch in updates}
        expected.update({row['id']: row for row in rows if row['id'] not in expected})
        if {row['id']: row for row in after} != expected or quote_updates(source, after, plan):
            raise RuntimeError('Quote repair readback failed')
        current = db.client.table('summaries').select('*').eq('id', sid).eq('user_id', owner).execute().data
        if current != [original] or digest(asdict(db.get_transcript(owner, eid))) != digest(asdict(source)):
            raise RuntimeError('Summary or source changed during verification')
        verified_upload(storage, prefix + '/complete.json', {
            'summary_id': sid, 'quotes': len(after), 'source_hash': digest(asdict(source)),
            'key_points_hash': digest(after), 'backup_path': prefix + '/before.json'})
        report['repaired'] += len(updates)
    return report


if __name__ == '__main__':
    try:
        print(json.dumps(main(repair)))
    except Exception as error:
        print(json.dumps({'operation': 'restore_verbatim_quotes', 'failed': 1, 'error_type': type(error).__name__}))
        sys.exit(1)
