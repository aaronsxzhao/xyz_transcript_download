import json
import unittest
from scripts.inspect_pending_imports import inspect, timestamp

class PendingImportDiagnostics(unittest.TestCase):
    def test_queries_are_bounded_and_snapshots_redact_private_fields(self):
        calls=[]
        def get(table, query):
            calls.append((table,query))
            if table=='processing_controls':return [{'target_revision':'a'*40,'expires_at':'2026-11-11T10:00:00Z','secret':'hidden'}]
            if 'c9a6' not in query['task_id']:return []
            return [{'task_id':'c9a6a826-ac40-4000-8000-000000000000','user_id':'private-owner','state':'cancelled','attempts':0,'deleted':True,'worker_id':'12345678-1234-1234-1234-123456789abc','worker_group':'embedded','created_at':'2026-11-11T00:00:00Z','updated_at':'bad-private-value','payload':{'url':'private-source'},'metrics':{'text':'private-prose'}}]
        result=inspect(get)
        self.assertEqual(result['tasks'][0]['snapshots'][0]['attempts'],0)
        self.assertEqual(result['tasks'][1]['status'],'not_found')
        self.assertFalse(result['historical_events_available'])
        raw=json.dumps(result)
        for secret in ['private-owner','private-source','private-prose','hidden','bad-private-value','12345678-1234-1234-1234-123456789abc']:
            self.assertNotIn(secret,raw)
        self.assertTrue(all(q['limit'] in ('21','2') for _,q in calls))
        self.assertNotIn('payload',calls[0][1]['select'].replace('deleted:payload->deleted',''))

    def test_ambiguous_owner_or_task_and_truncation_fail_closed(self):
        one={'task_id':'c9a6a826-ac40-4000-8000-000000000000','user_id':'a'}
        for rows in ([one]*21,[one,{**one,'user_id':'b'}],[one,{**one,'task_id':'c9a6a826-ac41-4000-8000-000000000000'}],[{**one,'task_id':'other'}]):
            self.assertEqual(inspect(lambda *_:rows)['status'],'blocked_ambiguous_or_truncated')

    def test_timestamp_rejects_untrusted_or_unzoned_text(self):
        for value in (None,{},'secret','2026-11-11T10:00:00'):
            self.assertIsNone(timestamp(value))
        self.assertEqual(timestamp('2026-11-11T10:00:00Z'),'2026-11-11T10:00:00+00:00')

if __name__=='__main__':unittest.main()
