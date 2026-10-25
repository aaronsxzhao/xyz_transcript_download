"""Regeneration state must not hide the last saved, readable note."""
import pytest


@pytest.mark.asyncio
async def test_local_source_catalog_keeps_saved_regenerations_and_filters_exactly(client, mock_database):
    from video_task_db import VideoTaskDB
    db = VideoTaskDB(mock_database.db_path)
    for channel in ('Course', 'Course extra'):
        task = db.create_task({'user_id': 'local', 'url': 'fixture://' + channel, 'channel': channel, 'platform': 'youtube'})
        db.complete_task(task, '# Saved note', 'detailed', 'test-model', 'local')
        db.update_task(task, {'status': 'failed'})
    failed = db.create_task({'user_id': 'local', 'url': 'fixture://failed', 'channel': 'No saved note'})
    db.update_task(failed, {'status': 'failed'})
    catalog = await client.get('/api/library/sources', params={'kind': 'video', 'limit': 1})
    assert catalog.json() == {'sources': ['Course'], 'next_cursor': 'Course'}
    assert (await client.get('/api/library/sources', params={'kind': 'video', 'cursor': 'Course'})).json() == {'sources': ['Course extra'], 'next_cursor': None}
    assert [r['source'] for r in (await client.get('/api/library', params={'source': 'Course'})).json()['items']] == ['Course']


@pytest.mark.asyncio
@pytest.mark.parametrize('status',['pending','summarizing','failed','cancelled'])
async def test_library_keeps_saved_notes_during_or_after_regeneration(client, mock_database, status):
    from video_task_db import VideoTaskDB
    db = VideoTaskDB(mock_database.db_path)
    saved = db.create_task({'user_id':'local','url':'fixture://saved','title':'Saved note','platform':'youtube'})
    db.complete_task(saved, '# Last saved note\n\nComplete saved content.', 'detailed', 'test-model', 'local')
    db.update_task(saved, {'status':status,'error':'New attempt did not finish'})
    partial = db.create_task({'user_id':'local','url':'fixture://partial','title':'Never saved','platform':'youtube'})
    db.update_task(partial, {'status':'failed','markdown':'# Incomplete streaming output'})
    empty = db.create_task({'user_id':'local','url':'fixture://empty','title':'Empty note','platform':'youtube'})
    db.add_version(empty, '# Previous version')
    db.update_task(empty, {'status':'failed','markdown':' \n\t '})
    response = await client.get('/api/library',params={'kind':'video'})
    assert response.status_code == 200
    rows = response.json()['items']
    assert {row['id'] for row in rows} == {saved}
    assert rows[0]['status'] == 'completed'
    assert 'markdown' not in rows[0] and 'versions' not in rows[0]
    assert db.get_task(saved,'local')['status'] == status
    assert db.get_task(saved,'local')['markdown'].startswith('# Last saved note')


@pytest.mark.asyncio
@pytest.mark.parametrize('saved_note',[True,False])
@pytest.mark.parametrize('success',[True,False])
async def test_new_streaming_output_does_not_replace_a_previous_note_before_commit(client,mock_database,saved_note,success):
    import json
    from unittest.mock import Mock,patch
    from video_task_db import VideoTaskDB
    from api.routers import video_notes
    db=VideoTaskDB(mock_database.db_path)
    task_id=db.create_task({'user_id':'local','url':'fixture://video','platform':'youtube','title':'Saved lesson','thumbnail':'https://example.com/cover.jpg'})
    if saved_note:db.complete_task(task_id,'# Complete original note','detailed','old-model','local')
    db.update_task(task_id,{'status':'pending','transcript_json':json.dumps({'text':'Complete source transcript. '*20,'segments':[],'duration':120})})
    def generate(**kwargs):
        kwargs['progress_callback'](100,'# Incomplete new draft')
        current=db.get_task(task_id,'local')['markdown']
        assert current==('# Complete original note' if saved_note else '# Incomplete new draft')
        if not success:raise RuntimeError('Synthetic generation interrupted')
        return '# Complete replacement note'
    engine=Mock();engine.generate_note.side_effect=generate
    with patch('api.llm_settings.resolve_llm_settings',return_value={'api_key':'synthetic','base_url':'https://models.example/v1','model':'selected-model'}),patch('note_summarizer.get_note_summarizer',return_value=engine):
        await video_notes.process_video_note_async(task_id,url='fixture://video',platform='youtube',style='detailed',formats=['summary'],quality='medium',llm_model='',extras='',video_understanding=False,video_interval=4,grid_cols=3,grid_rows=3,user_id='local')
    task=db.get_task(task_id,'local')
    assert task['status']==('success' if success else 'failed')
    assert task['markdown']==('# Complete replacement note' if success else '# Complete original note' if saved_note else '# Incomplete new draft')
    assert len(db.get_versions(task_id))==int(saved_note)+int(success)
    assert ((await client.get('/api/library',params={'kind':'video'})).json()['items']!=[])==(saved_note or success)
