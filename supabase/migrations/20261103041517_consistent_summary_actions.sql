-- Install before the application. No historical records are rewritten.
create function public.save_processing_jobs_ordered(p_rows jsonb, p_work uuid default null,
  p_worker text default null, p_create boolean default false)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare r jsonb; old public.processing_jobs%rowtype; w public.processing_work%rowtype;
  result jsonb := '[]'; outcome text; next_status text; owner uuid; task text;
begin
  for r in select value from jsonb_array_elements(p_rows) order by value->>'id' loop
    owner := (r->>'user_id')::uuid; task := r->>'id'; next_status := r->'payload'->>'status';
    if owner is null or task is null or r->'payload'->>'job_id' is distinct from task
      or r->'payload'->>'user_id' is distinct from owner::text then raise exception 'Invalid job identity'; end if;
    outcome := 'applied';
    perform pg_advisory_xact_lock(hashtextextended(owner::text||':podcast:'||task,0));
    if p_work is not null then
      select * into w from processing_work where id=p_work for update;
      if not found or w.user_id is distinct from owner or w.kind<>'podcast' or w.task_id<>task
        or w.worker_id is distinct from p_worker or p_worker is null
        or w.lease_until is null or w.lease_until<=clock_timestamp()
        or exists(select 1 from processing_work where user_id=owner and kind='podcast'
          and task_id=task and id<>p_work and created_at>=w.created_at)
        or (w.state<>'running' and not (w.state in ('failed','cancelled') and next_status=w.state)) then
        outcome := 'lease_rejected';
      elsif w.cancel_requested and next_status is distinct from 'cancelled' then outcome := 'cancel_requested'; end if;
    end if;
    select * into old from processing_jobs where id=task for update;
    if outcome='applied' then
      if not found then
        if p_create and p_work is null then
          insert into processing_jobs(id,user_id,payload,updated_at) values(task,owner,r->'payload',clock_timestamp());
        else outcome := 'not_found'; end if;
      elsif old.user_id is distinct from owner then outcome := 'not_found';
      elsif coalesce((old.payload->>'revision')::bigint,0)>=coalesce((r->'payload'->>'revision')::bigint,0) then outcome := 'stale';
      elsif (old.payload->>'status' in ('completed','failed','cancelled') and next_status is distinct from old.payload->>'status')
        or (old.payload->>'status'='cancelling' and next_status not in ('cancelling','cancelled')) then
        outcome := 'terminal';
        -- Publish the winning state with a newer revision than the rejected event.
        update processing_jobs set payload=jsonb_set(payload,'{revision}',to_jsonb((r->'payload'->>'revision')::bigint+1)),updated_at=clock_timestamp()
          where id=task returning * into old;
      else
        update processing_jobs set payload=r->'payload',updated_at=clock_timestamp() where id=task;
      end if;
    end if;
    result := result || jsonb_build_array(jsonb_build_object('id',task,'outcome',outcome,
      'payload',case when outcome in ('stale','terminal') then old.payload else null end));
  end loop;
  return result;
end $$;
revoke all on function public.save_processing_jobs_ordered(jsonb,uuid,text,boolean) from public,anon,authenticated;
grant execute on function public.save_processing_jobs_ordered(jsonb,uuid,text,boolean) to service_role;

create function public.delete_user_video_summary(p_user uuid,p_task text)
returns text language plpgsql security invoker set search_path=public as $$
declare t public.video_tasks%rowtype;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_user::text||':video:'||p_task,0));
  perform 1 from processing_work where user_id=p_user and kind='video' and task_id=p_task for update;
  if exists(select 1 from processing_work where user_id=p_user and kind='video' and task_id=p_task and state in ('queued','running')) then return 'busy'; end if;
  select * into t from video_tasks where id=p_task and user_id=p_user for update;
  if not found then return 'not_found'; end if;
  if t.status not in ('success','failed','cancelled','discovered') then return 'busy'; end if;
  delete from video_task_versions where task_id=p_task;
  update video_tasks set markdown='',status='discovered',progress=0,message='',error='',updated_at=clock_timestamp() where id=p_task;
  return 'applied';
end $$;
revoke all on function public.delete_user_video_summary(uuid,text) from public,anon,authenticated;
grant execute on function public.delete_user_video_summary(uuid,text) to service_role;
notify pgrst, 'reload schema';

create function public.delete_user_podcast_summary(p_user uuid,p_episode text)
returns text language plpgsql security invoker set search_path=public as $$
declare sid public.summaries.id%type;
begin
  -- Same queue-before-content lock order as leased summary saves.
  perform 1 from processing_work w where w.user_id=p_user and w.kind='podcast'
    and exists(select 1 from processing_jobs j where j.id=w.task_id and j.user_id=p_user
      and j.payload->>'episode_id'=p_episode) order by w.id for update;
  if exists(select 1 from processing_jobs j where j.user_id=p_user and j.payload->>'episode_id'=p_episode
    and (j.payload->>'status' not in ('completed','failed','cancelled') or exists(
      select 1 from processing_work w where w.task_id=j.id and w.user_id=p_user and w.kind='podcast' and w.state in ('queued','running')))) then return 'busy'; end if;
  select id into sid from summaries where user_id=p_user and episode_id=p_episode for update;
  if not found then return 'not_found'; end if;
  delete from summary_key_points where summary_id=sid;
  delete from summaries where id=sid;
  return 'applied';
end $$;
revoke all on function public.delete_user_podcast_summary(uuid,text) from public,anon,authenticated;
grant execute on function public.delete_user_podcast_summary(uuid,text) to service_role;
notify pgrst, 'reload schema';
