from types import SimpleNamespace as NS
from unittest.mock import patch
import pytest
from scripts import repair_reported_summary as recovery


@pytest.mark.parametrize('valid',[True,False])
def test_recovery_reuses_transcript_and_acknowledges_failure_only_after_verified_summary(monkeypatch,valid):
    original={'id':'transcript','duration':5117.1,'text':'saved source '*1000}
    filters=[]
    class Query:
        def __init__(self,table):self.table=table
        def select(self,*args):return self
        def eq(self,key,value):filters.append((self.table,key,value));return self
        def execute(self):
            return NS(data=[{'user_id':'owner','payload':{'episode_id':recovery.EPISODE_ID}}] if self.table=='processing_jobs' else [dict(original)])
    client=NS(table=Query)
    monkeypatch.setenv('EXPECTED_REVISION','current')
    requests=[];summary_reads=0
    def request(path,token,data=None):
        nonlocal summary_reads
        requests.append((path,data))
        if path=='/api/health':return {'revision':'current'}
        if path.startswith('/api/summaries/'):
            summary_reads+=1
            if summary_reads==1:
                error=RuntimeError();error.http_status=404;raise error
            return {'overview':'source overview '*20,'topics':['topic'] if valid else [],'key_points':[{'summary':'point'}] if valid else []}
        if path=='/api/jobs':return {'jobs':[]}
        if path.endswith('/retry'):return {'new_job_id':'new'}
        return {'status':'completed' if path.endswith('/new') else 'failed'}
    with patch('api.supabase_client.get_supabase_admin_client',return_value=client),patch.object(recovery,'request_json',side_effect=request),patch.object(recovery,'request_json_delete') as acknowledge:
        if valid:
            result=recovery.repair({'SUPABASE_JWT_SECRET':'fixture-signing-secret-only'})
            assert result['transcript_unchanged']==1
            acknowledge.assert_called_once()
        else:
            with pytest.raises(RuntimeError,match='incomplete'):recovery.repair({'SUPABASE_JWT_SECRET':'fixture-signing-secret-only'})
            acknowledge.assert_not_called()
    assert any(path.endswith('/retry') for path,_ in requests)
    assert not any('process' in path or 'transcribe' in path for path,_ in requests)
    assert ('transcripts','user_id','owner') in filters
