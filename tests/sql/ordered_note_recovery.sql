do $$
declare owner uuid := '10000000-0000-0000-0000-000000000001'; p jsonb; outcome text;
begin
  p := jsonb_build_object('task_id','recover','user_id',owner,'version_id','recovered-v','content','synthetic recovery','style','detailed','model','test','recovery_order',jsonb_build_object('base_versions','[]'::jsonb,'work_id',null));
  insert into video_tasks(id,user_id,status,updated_at,markdown) values('recover',owner,'failed','2026-11-01Z','');
  assert recover_video_note_ordered(owner,'recover','2026-10-31Z',p)='changed';
  assert recover_video_note_ordered(owner,'recover','2026-11-01Z',p-'recovery_order')='unverified';
  assert recover_video_note_ordered('10000000-0000-0000-0000-000000000002','recover','2026-11-01Z',p)='not_found';
  assert recover_video_note_ordered(owner,'recover','2026-11-01Z',p)='applied';
  assert recover_video_note_ordered(owner,'recover',(select updated_at from video_tasks where id='recover'),p)='already_saved';
  assert (select count(*) from video_task_versions where task_id='recover')=1;
  -- A later saved version wins even after its task is subsequently marked failed.
  perform complete_user_video_note(owner,'recover','newer-v','newer result','detailed','test','');
  update video_tasks set status='failed' where id='recover';
  assert recover_video_note_ordered(owner,'recover',(select updated_at from video_tasks where id='recover'),p)='superseded';
  assert (select markdown from video_tasks where id='recover')='newer result';
  insert into processing_work(id,user_id,kind,task_id,state,created_at) values('30000000-0000-0000-0000-000000000001',owner,'video','recover','queued',now());
  assert recover_video_note_ordered(owner,'recover',(select updated_at from video_tasks where id='recover'),p)='busy';
  update processing_work set state='failed' where task_id='recover';
  assert recover_video_note_ordered(owner,'recover',(select updated_at from video_tasks where id='recover'),p)='superseded';
  -- Reclaiming the same work ID must also invalidate the former attempt.
  update processing_work set attempts=2 where task_id='recover';
  p := jsonb_set(p,'{recovery_order,work_id}','"30000000-0000-0000-0000-000000000001"');
  p := jsonb_set(p,'{recovery_order,work_attempt}','1');
  assert recover_video_note_ordered(owner,'recover',(select updated_at from video_tasks where id='recover'),p)='superseded';
  insert into video_tasks(id,user_id,status,updated_at,markdown) values('recover-attempt',owner,'failed','2026-11-01Z','');
  insert into processing_work(id,user_id,kind,task_id,state,created_at,attempts) values('30000000-0000-0000-0000-000000000002',owner,'video','recover-attempt','failed',now(),2);
  p := jsonb_set(jsonb_set(p,'{task_id}','"recover-attempt"'),'{version_id}','"attempt-v"');
  p := jsonb_set(p,'{recovery_order,work_id}','"30000000-0000-0000-0000-000000000002"');
  assert recover_video_note_ordered(owner,'recover-attempt','2026-11-01Z',p)='superseded';
  p := jsonb_set(p,'{recovery_order,work_attempt}','2');
  assert recover_video_note_ordered(owner,'recover-attempt','2026-11-01Z',p)='applied';
  assert not has_function_privilege('anon','recover_video_note_ordered(uuid,text,timestamptz,jsonb)','EXECUTE');
  assert not has_function_privilege('authenticated','recover_video_note_ordered(uuid,text,timestamptz,jsonb)','EXECUTE');
end $$;
