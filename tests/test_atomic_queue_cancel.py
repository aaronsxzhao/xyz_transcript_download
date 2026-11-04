from unittest.mock import Mock
import pytest
from execution_store import Store

@pytest.mark.parametrize('kind',['video','podcast'])
def test_cloud_cancel_is_one_owned_database_operation(kind):
    client=Mock();Store(client=client).cancel('owner',kind,'task',deleted=True)
    client.rpc.assert_called_once_with('cancel_processing_work',{'p_user':'owner','p_kind':kind,'p_task':'task','p_deleted':True})
    client.table.assert_not_called()

@pytest.mark.parametrize('kind',['video','podcast'])
@pytest.mark.parametrize('state',['queued','running','completed','failed','cancelled'])
def test_local_cancel_preserves_terminal_rows_and_current_payload(tmp_path,kind,state):
    store=Store(path=tmp_path/'queue.db');ident=store.enqueue('owner',kind,'task','source',{'keep':'latest'})
    with store.connection() as db:
        db.execute('update processing_work set state=? where id=?',(state,ident))
    store.cancel('other',kind,'task',True)
    assert store.latest('owner',kind,'task')['state']==state
    store.cancel('owner',kind,'task',True)
    row=store.latest('owner',kind,'task')
    assert row['state']==('cancelled' if state=='queued' else state)
    assert bool(row['cancel_requested'])==(state in ('queued','running'))
    assert row['payload']==({'keep':'latest','deleted':True} if state in ('queued','running') else {'keep':'latest'})
