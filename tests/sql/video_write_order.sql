-- Run only in a disposable PostgreSQL database. All records are synthetic.
-- Load the ordered_video_task_writes migration before the assertions below.
begin;
insert into video_tasks(id,user_id,status,updated_at,title) values
 ('ordering-test','00000000-0000-0000-0000-000000000001','pending','2026-01-01','keep');
do $$
declare result text;
begin
  result:=update_video_task_ordered('ordering-test','{"status":"cancelled","updated_at":"2026-01-03Z"}');
  assert result='applied';
  result:=update_video_task_ordered('ordering-test','{"status":"summarizing","updated_at":"2026-01-02Z"}');
  assert result='stale';
  assert (select status='cancelled' and title='keep' from video_tasks where id='ordering-test');
  -- Even a later-generated cancellation/failure cannot undo a final save.
  update video_tasks set status='success',updated_at='2026-01-04' where id='ordering-test';
  assert update_video_task_ordered('ordering-test','{"status":"cancelled","updated_at":"2026-01-05Z"}')='terminal';
  assert update_video_task_ordered('ordering-test','{"status":"failed","updated_at":"2026-01-05Z"}')='terminal';
  -- Explicit retry remains supported and preserves saved note metadata.
  assert update_video_task_ordered('ordering-test','{"status":"pending","updated_at":"2026-01-06Z"}')='applied';
  insert into processing_work(id,user_id,kind,task_id,source_id,state,worker_id,lease_until,created_at)
    values('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000001',
      'video','ordering-test','source','running','new-worker',clock_timestamp()+interval '1 hour','2026-01-06');
  assert update_video_task_ordered('ordering-test','{"status":"summarizing","updated_at":"2026-01-07Z"}',
    '00000000-0000-0000-0000-000000000002','old-worker','00000000-0000-0000-0000-000000000001')='lease_rejected';
  assert update_video_task_ordered('ordering-test','{"status":"summarizing","updated_at":"2026-01-07Z"}',
    '00000000-0000-0000-0000-000000000002','new-worker','00000000-0000-0000-0000-000000000001')='applied';
  update processing_work set cancel_requested=true where task_id='ordering-test';
  assert update_video_task_ordered('ordering-test','{"status":"summarizing","updated_at":"2026-01-08Z"}',
    '00000000-0000-0000-0000-000000000002','new-worker','00000000-0000-0000-0000-000000000001')='cancel_requested';
  assert update_video_task_ordered('ordering-test','{"status":"cancelled","updated_at":"2026-01-08Z"}',
    '00000000-0000-0000-0000-000000000002','new-worker','00000000-0000-0000-0000-000000000001')='applied';
  update processing_work set state='cancelled' where task_id='ordering-test';
  insert into processing_work(id,user_id,kind,task_id,source_id,state,created_at)
    values('00000000-0000-0000-0000-000000000003','00000000-0000-0000-0000-000000000001',
      'video','ordering-test','source','queued','2026-01-09');
  assert update_video_task_ordered('ordering-test','{"status":"cancelled","updated_at":"2026-01-10Z"}',
    '00000000-0000-0000-0000-000000000002','new-worker','00000000-0000-0000-0000-000000000001')='lease_rejected';
  assert not has_function_privilege('anon','public.update_video_task_ordered(text,jsonb,uuid,text,uuid)','execute');
  assert not has_function_privilege('authenticated','public.update_video_task_ordered(text,jsonb,uuid,text,uuid)','execute');
  assert has_function_privilege('service_role','public.update_video_task_ordered(text,jsonb,uuid,text,uuid)','execute');
end $$;
rollback;
