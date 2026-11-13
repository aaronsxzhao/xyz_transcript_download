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
