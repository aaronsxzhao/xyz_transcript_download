from unittest.mock import Mock
from api.supabase_db import SupabaseDatabase


def test_joined_points_keep_saved_order_after_row_updates():
    db = SupabaseDatabase.__new__(SupabaseDatabase)
    db.client = Mock()
    query = db.client.table.return_value.select.return_value
    query.eq.return_value = query
    points = [dict(id=i, topic='Topic', summary=f'Point {i}', original_quote=f'Quote {i}', timestamp='') for i in (30, 10, 20)]
    query.execute.return_value.data = [dict(id=1, user_id='owner', episode_id='episode', title='Title', overview='Overview', topics=['Topic'], takeaways=[], summary_key_points=points)]
    result = db.get_summary('owner', 'episode')
    assert [p['summary'] for p in result.key_points] == ['Point 10', 'Point 20', 'Point 30']
    assert [p['original_quote'] for p in result.key_points] == ['Quote 10', 'Quote 20', 'Quote 30']
    assert all('id' not in p for p in result.key_points)
    assert [p['id'] for p in points] == [30, 10, 20]
    assert ('user_id', 'owner') in [call.args for call in query.eq.call_args_list]
