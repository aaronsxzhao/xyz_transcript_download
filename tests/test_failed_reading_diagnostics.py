from scripts.inspect_failed_reading import safe_report


def test_diagnostics_never_export_prose_settings_or_arbitrary_failure_strings():
    report={'delivery':{'reason':'secret prompt text','status':'blocked','coverage_ratio':.8,'token':'secret'},
            'coverage_ledger':{'items':[{'status':'contradicted','statement':'private source'}],
                               'grounding_concerns':True,'requests':float('nan')},
            'verification':{'unsupported_paragraph_ids':['private'],'reviewed':3},
            'settings':{'api_key':'secret'}}
    safe=safe_report(report)
    assert safe['delivery']=={'coverage_ratio':.8,'status':'blocked'}
    assert safe['coverage_ledger']['item_status_counts']['contradicted']==1
    assert safe['verification']=={'reviewed':3}
    assert 'secret' not in str(safe) and 'private' not in str(safe)
    assert 'requests' not in safe['coverage_ledger']


def test_budget_never_sends_account_key_to_an_unrecognized_provider(monkeypatch):
    from scripts import inspect_failed_reading as diagnostic
    monkeypatch.setattr(diagnostic,'urlopen',lambda *a,**k: (_ for _ in ()).throw(AssertionError('No request allowed')))
    assert diagnostic.inspect_budget({'llm_provider':'custom','llm_base_url':'https://other.example'},'owner','seed')['status']=='blocked'


def test_provider_receipt_only_exposes_allowlisted_type_and_http_status():
    row=safe_report({'coverage_ledger':{'inventory_failures':[
        {'error_type':'InternalServerError','http_status':524,'body':'private response'}]}})['coverage_ledger']
    assert row['inventory_error_types']['InternalServerError']==1
    assert row['inventory_http_statuses']['524']==1
    assert row['inventory_failures_recorded']==1
    assert 'private response' not in str(row)


def test_round_diagnostics_allowlist_counts_and_never_leak_private_values():
    report={'coverage_rounds':[{'phase':'initial','outcome':'completed','seconds':2.5,
        'accepted_paragraphs':3,'coverage_ratio':.8,'private':'secret text',
        'status_counts':{'covered':5,'private':123},
        'unresolved_by_kind':{'claim':2,'private':12},
        'rejection_reasons':{'ungrounded':1,'secret text':3}},
        {'phase':'private','outcome':'interrupted','cancelled':True,'seconds':float('nan')}]}
    safe=safe_report(report)
    assert safe['coverage_rounds_truncated'] is False
    assert safe['coverage_rounds'][0]['accepted_paragraphs']==3
    assert safe['coverage_rounds'][0]['status_counts']=={'covered':5}
    assert safe['coverage_rounds'][0]['unresolved_by_kind']=={'claim':2}
    assert safe['coverage_rounds'][0]['rejection_reasons']=={'ungrounded':1}
    assert safe['coverage_rounds'][1]=={'outcome':'interrupted','cancelled':True}
    assert 'secret' not in str(safe) and 'private' not in str(safe)


def test_reported_episode_query_is_exact_read_only_and_metrics_are_allowlisted():
    from scripts.inspect_failed_reading import inspect_reported_episode, REPORTED_EPISODE
    calls=[]
    def get(table,query):
        calls.append((table,query))
        return [{'task_id':'sample','user_id':'private-owner','state':'failed','metrics':{
            'wall_seconds':2400,'stages':{'model.phase.inventory':{'seconds':2000,'calls':6,'body':'secret'},
            'private prompt':{'seconds':1}},'generation':{'delivery':{'reason':'source_review','status':'blocked'}}}}]
    result=inspect_reported_episode(get)
    assert calls[0][0]=='processing_work'
    assert calls[0][1]['payload->>episode_url']=='eq.'+REPORTED_EPISODE
    assert calls[0][1]['limit']=='21'
    assert result['tasks'][0]['stages']=={'model.phase.inventory':{'seconds':2000,'calls':6}}
    assert 'private' not in str(result) and 'secret' not in str(result)
    assert result['production_writes'] is False and result['provider_calls']==0


def test_reported_episode_ambiguous_owners_do_not_disclose_task_metrics():
    from scripts.inspect_failed_reading import inspect_reported_episode
    result=inspect_reported_episode(lambda *_:[{'user_id':'a'},{'user_id':'b'}])
    assert result['status']=='blocked_ambiguous_or_truncated'
    assert 'tasks' not in result


def test_budget_report_uses_authorized_shared_daily_limit_without_exposing_key(monkeypatch):
    import io,json
    from datetime import datetime,timedelta,timezone
    from cryptography.fernet import Fernet
    from scripts import inspect_failed_reading as diagnostic
    today=datetime.now(timezone(timedelta(hours=8)))
    rows=[{'created_at':int(today.timestamp()),'type':2,'quota':1000000},
          {'created_at':int((today-timedelta(days=1)).timestamp()),'type':2,'quota':500000}]
    monkeypatch.setattr(Fernet,'decrypt',lambda *args:b'private-synthetic-test-key')
    monkeypatch.setattr(diagnostic,'urlopen',lambda *args,**kwargs:io.StringIO(json.dumps({'data':rows})))
    result=diagnostic.inspect_budget({'llm_provider':'custom','llm_base_url':'https://api.aipaibox.com/v1',
                                    'llm_api_key_encrypted':'synthetic'},'authorized-test-owner','synthetic-seed')
    assert result['settled_usd']==2
    assert result['daily_limit_usd']==100
    assert result['remaining_usd']==98
    assert result['scope']=='configured_test_account_provider_token'
    assert 'private' not in str(result) and 'seed' not in str(result)
