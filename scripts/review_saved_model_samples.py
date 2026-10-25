"""Generate isolated review files through an account's SAVED custom provider.

Run in an application environment with the existing database and credential
bindings. Never supply a key on the command line. Does not save summaries,
update tasks, download media, or publish review content.

Example:
  python scripts/review_saved_model_samples.py --owner ACCOUNT_ID \
    --case podcast:EPISODE_ID --case video:TASK_ID --output /tmp/private-review
"""
import argparse
import contextlib
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def generate_case(owner, kind, identifier):
    from api.user_settings import get_user_settings
    from api.llm_settings import resolve_llm_settings
    preferences = get_user_settings(owner)
    if preferences.get('llm_provider') != 'custom':
        raise ValueError('Select and save the intended custom summary provider first.')
    # Missing/unreadable keys fail here. No server/Groq fallback is permitted.
    settings = resolve_llm_settings(preferences)
    started = time.monotonic()
    if kind == 'podcast':
        from api.db import get_db
        from transcriber import Transcript, TranscriptSegment
        from summarizer import Summarizer
        from dataclasses import asdict
        from podcast_prompts import SYSTEM_PROMPT
        db = get_db(owner)
        episode, saved = db.get_episode(identifier), db.get_transcript(identifier)
        if not episode or not saved:
            raise ValueError('The selected account has no matching episode/transcript.')
        transcript = Transcript(identifier, saved.language, saved.duration, saved.text,
            [TranscriptSegment(**segment) for segment in saved.segments])
        podcast = db.get_podcast(episode.pid)
        engine = Summarizer(**settings)
        try:
            result = engine.summarize(transcript, podcast.title if podcast else '', episode.title)
        finally:
            engine.client.close()
        if result is None:
            raise ValueError('No generated sample was returned.')
        content = asdict(result)
        source = saved.text
        prompt_hash = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()
    elif kind == 'video':
        from video_task_db import get_video_task_db
        from source_coverage import video_source_text
        from note_summarizer import NoteSummarizer, _build_system_prompt
        task = get_video_task_db().get_task(identifier, owner)
        if not task:
            raise ValueError('The selected account has no matching video.')
        if task.get('style') == 'original':
            raise ValueError('Original-text articles do not require summarization.')
        saved = json.loads(task.get('transcript_json') or '{}')
        source = saved.get('text') or ''
        if not source.strip():
            raise ValueError('This video has no saved source transcript.')
        text = video_source_text(source, saved.get('segments') or [])
        style, formats = task.get('style') or 'detailed', task.get('formats') or []
        engine = NoteSummarizer(**settings)
        try:
            content = engine.generate_note(task['title'], text, style=style, formats=formats,
                                           duration=task.get('duration') or 0)
        finally:
            engine.client.close()
        if not content:
            raise ValueError('No generated sample was returned.')
        prompt_hash = hashlib.sha256(_build_system_prompt(style, formats,
            duration=task.get('duration') or 0, source_text=source).encode()).hexdigest()
    else:
        raise ValueError('Use podcast:ID or video:ID.')
    return {'kind': kind, 'id': identifier, 'model': settings['model'],
            'scope': 'saved_transcript_summary_only',
            'provider': 'saved_custom', 'source_chars': len(source),
            'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'system_prompt_sha256': prompt_hash,
            'elapsed_seconds': round(time.monotonic() - started, 2), 'result': content}


def write_review(path, data):
    # Review content is private, and existing files are never overwritten.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        json.dump(data, output, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--case', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    for case in args.case:
        kind, _, identifier = case.partition(':')
        if kind not in ('podcast', 'video') or not identifier:
            parser.error('Each --case must be podcast:ID or video:ID.')
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    failures = 0
    for index, case in enumerate(args.case, 1):
        kind, _, identifier = case.partition(':')
        destination = args.output / f'case-{index:03}.json'
        if destination.exists():
            raise SystemExit('Review files already exist; choose a fresh output directory.')
        previous = logging.root.manager.disable
        try:
            # No provider messages, credentials, source or generated prose in logs.
            logging.disable(logging.CRITICAL)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                data = generate_case(args.owner, kind, identifier)
            write_review(destination, data)
            print(json.dumps({'sample': index, 'ok': True, 'source_chars': data['source_chars'],
                              'elapsed_seconds': data['elapsed_seconds']}), flush=True)
        except Exception as error:
            from api.custom_models import public_model_error
            failures += 1
            print(json.dumps({'sample': index, 'ok': False,
                              'error': public_model_error(error, 'summary')}), flush=True)
        finally:
            logging.disable(previous)
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
