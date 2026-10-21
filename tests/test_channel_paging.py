import pytest
from api.channel_paging import page, decode_cursor
from video_task_db import _SQLiteVideoTaskDB


def test_channel_pages_are_bounded_stable_and_owner_scoped(tmp_path):
    db = _SQLiteVideoTaskDB(tmp_path/'channel.db')
    for i in range(93):
        db.create_task({'id': f'v{i:03}', 'user_id':'owner', 'platform':'youtube', 'channel':'Large channel', 'title':f'Lesson {i}', 'url':f'fixture://{i}'})
    db.create_task({'user_id':'other', 'platform':'youtube', 'channel':'Large channel', 'title':'Private', 'url':'fixture://private'})
    all_rows=[]; cursor=''
    while True:
        result=page(db,'Large channel','youtube','owner',cursor=cursor)
        assert len(result['tasks'])<=40
        assert all('markdown' not in row for row in result['tasks'])
        all_rows.extend(result['tasks'])
        cursor=result['next_cursor']
        if not cursor:break
    assert len(all_rows)==len({r['id'] for r in all_rows})==93
    oldest=page(db,'Large channel','youtube','owner',sort='oldest')['tasks']
    assert oldest[0]['id']==all_rows[-1]['id']
    matched=page(db,'Large channel','youtube','owner',q='Lesson 92')['tasks']
    assert len(matched)==1 and matched[0]['title']=='Lesson 92'
    assert page(db,'Large channel','youtube','owner',q='%')['tasks']==[]
    assert page(db,'Large channel','youtube','owner',status='success')['tasks']==[]


def test_channel_cursor_rejects_malformed_or_injected_expressions():
    import base64,json
    for cursor in ['bad',base64.urlsafe_b64encode(json.dumps(['2026-01-01','a),user_id.neq.x']).encode()).decode()]:
        with pytest.raises(ValueError):decode_cursor(cursor)


@pytest.mark.asyncio
async def test_channel_http_contract_bounds_requests(client):
    from video_task_db import get_video_task_db
    db=get_video_task_db()
    for i in range(45):db.create_task({'user_id':'local','platform':'youtube','channel':'Big','title':f'Lesson {i}','url':f'fixture://{i}'})
    response=await client.get('/api/video-notes/tasks/by-channel',params={'channel':'Big','platform':'youtube'})
    assert response.status_code==200
    result=response.json();assert len(result['tasks'])==40 and result['next_cursor']
    response=await client.get('/api/video-notes/tasks/by-channel',params={'channel':'Big','platform':'youtube','cursor':result['next_cursor']})
    assert len(response.json()['tasks'])==5 and response.json()['next_cursor'] is None
    assert (await client.get('/api/video-notes/tasks/by-channel',params={'channel':'Big','platform':'youtube','limit':1000})).status_code==422
