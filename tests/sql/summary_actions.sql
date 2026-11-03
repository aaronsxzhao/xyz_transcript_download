do $$
declare owner uuid := '10000000-0000-0000-0000-000000000001'; receipt jsonb; row_data jsonb; work uuid := '20000000-0000-0000-0000-000000000001';
begin
  row_data := jsonb_build_object('id','pod','user_id',owner,'payload',jsonb_build_object('job_id','pod','user_id',owner,'status','pending','revision',1,'episode_id','ep'));
  receipt := save_processing_jobs_ordered(jsonb_build_array(row_data),null,null,false);
  assert receipt->0->>'outcome'='not_found';
  receipt := save_processing_jobs_ordered(jsonb_build_array(row_data),null,null,true);
  assert receipt->0->>'outcome'='applied';
  row_data := jsonb_set(jsonb_set(row_data,'{payload,status}','"completed"'),'{payload,revision}','3');
  assert save_processing_jobs_ordered(jsonb_build_array(row_data))->0->>'outcome'='applied';
  row_data := jsonb_set(jsonb_set(row_data,'{payload,status}','"transcribing"'),'{payload,revision}','2');
  assert save_processing_jobs_ordered(jsonb_build_array(row_data))->0->>'outcome'='stale';
  row_data := jsonb_set(row_data,'{payload,revision}','4');
  receipt := save_processing_jobs_ordered(jsonb_build_array(row_data));
  assert receipt->0->>'outcome'='terminal';
  assert receipt->0->'payload'->>'status'='completed';
  assert (receipt->0->'payload'->>'revision')::int=5;
  insert into processing_work(id,user_id,kind,task_id,state,worker_id,lease_until,created_at)
    values(work,owner,'podcast','pod','running','new-worker',now()+interval '1 hour',now());
  assert save_processing_jobs_ordered(jsonb_build_array(row_data),work,'old-worker')->0->>'outcome'='lease_rejected';
  update processing_work set cancel_requested=true where id=work;
  assert save_processing_jobs_ordered(jsonb_build_array(row_data),work,'new-worker')->0->>'outcome'='cancel_requested';
  update processing_work set cancel_requested=false,lease_until=now()-interval '1 second' where id=work;
  assert save_processing_jobs_ordered(jsonb_build_array(row_data),work,'new-worker')->0->>'outcome'='lease_rejected';
  delete from processing_jobs where id='pod';
  update processing_work set lease_until=now()+interval '1 hour' where id=work;
  assert save_processing_jobs_ordered(jsonb_build_array(row_data),work,'new-worker',true)->0->>'outcome'='not_found';
  assert not exists(select from processing_jobs where id='pod');

  insert into video_tasks(id,user_id,status,markdown,transcript_json) values('summary-delete',owner,'success','notes','transcript');
  insert into video_task_versions(id,task_id,content) values('version','summary-delete','old notes');
  assert delete_user_video_summary('10000000-0000-0000-0000-000000000002','summary-delete')='not_found';
  update video_tasks set status='summarizing' where id='summary-delete';
  assert delete_user_video_summary(owner,'summary-delete')='busy';
  assert exists(select from video_task_versions where task_id='summary-delete');
  update video_tasks set status='success' where id='summary-delete';
  assert delete_user_video_summary(owner,'summary-delete')='applied';
  assert exists(select from video_tasks where id='summary-delete' and markdown='' and transcript_json='transcript' and status='discovered');
  assert not exists(select from video_task_versions where task_id='summary-delete');

  insert into summaries(user_id,episode_id) values(owner,'ep');
  insert into summary_key_points(summary_id) select id from summaries where episode_id='ep';
  assert delete_user_podcast_summary('10000000-0000-0000-0000-000000000002','ep')='not_found';
  insert into processing_jobs values('pod',owner,jsonb_build_object('episode_id','ep','status','completed'),now());
  assert delete_user_podcast_summary(owner,'ep')='busy';
  update processing_work set state='done' where id=work;
  assert delete_user_podcast_summary(owner,'ep')='applied';
  assert not exists(select from summaries where episode_id='ep');
  assert not exists(select from summary_key_points);
  assert not has_function_privilege('authenticated','public.save_processing_jobs_ordered(jsonb,uuid,text,boolean)','EXECUTE');
  assert not has_function_privilege('anon','public.delete_user_video_summary(uuid,text)','EXECUTE');
  assert not has_function_privilege('authenticated','public.delete_user_podcast_summary(uuid,text)','EXECUTE');
end $$;
