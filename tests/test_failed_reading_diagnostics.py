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
