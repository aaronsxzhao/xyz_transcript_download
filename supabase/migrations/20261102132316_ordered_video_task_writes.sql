-- Additive, service-only entry point. Existing readers/final-save RPCs remain
-- compatible. Install before deploying the Python caller; no data rewrite.
create function public.update_video_task_ordered(
  p_task text, p_patch jsonb, p_work uuid default null,
  p_worker text default null, p_user uuid default null)
returns text language plpgsql security invoker set search_path=public as $$
declare
  task_row public.video_tasks%rowtype;
  work_row public.processing_work%rowtype;
  event_time timestamptz;
  next_status text;
  assignments text;
  allowed text[] := array['status','progress','message','markdown','transcript_json',
    'task_dismissed','title','thumbnail','duration','error','model','platform',
    'source_metadata','channel','channel_url','channel_avatar','published_at',
    'style','formats','quality','video_quality','extras','video_understanding',
    'video_interval','grid_cols','grid_rows','updated_at'];
begin
  if jsonb_typeof(p_patch) is distinct from 'object' or not (p_patch ? 'updated_at')
    or exists(select 1 from jsonb_object_keys(p_patch) k where not (k=any(allowed))) then
    raise exception 'Invalid task patch';
  end if;
  event_time := (p_patch->>'updated_at')::timestamptz;
  if event_time is null then raise exception 'Missing event version'; end if;
  next_status := p_patch->>'status';
  if p_patch ? 'status' and next_status is null then raise exception 'Missing task status'; end if;

  if p_work is not null then
    -- Same admission lock as enqueue_processing_work. Lock queue before task,
    -- matching complete_leased_video_note's order.
    perform pg_advisory_xact_lock(hashtextextended(p_user::text||':video:'||p_task,0));
    select * into work_row from processing_work where id=p_work for update;
    if not found or work_row.user_id is distinct from p_user
      or work_row.kind<>'video' or work_row.task_id<>p_task
      or work_row.worker_id is distinct from p_worker or p_worker is null
      or work_row.lease_until is null or work_row.lease_until<=clock_timestamp()
      or exists(select 1 from processing_work where user_id=p_user and kind='video'
        and task_id=p_task and id<>p_work and created_at>=work_row.created_at) then
      return 'lease_rejected';
    end if;
    if work_row.state<>'running' and not
      (work_row.state in ('failed','cancelled') and next_status=work_row.state) then
      return 'lease_rejected';
    end if;
    if work_row.cancel_requested and next_status is distinct from 'cancelled' then
      return 'cancel_requested';
    end if;
  end if;

  select * into task_row from video_tasks where id=p_task for update;
  if not found then return 'not_found'; end if;
  if p_work is not null and task_row.user_id is distinct from p_user then return 'lease_rejected'; end if;
  -- Compare under the row lock, not a prior SELECT in the API process.
  if task_row.updated_at>event_time then return 'stale'; end if;
  if next_status is not null and (
    (task_row.status in ('success','failed','cancelled') and next_status not in (task_row.status,'pending'))
    or (task_row.status='cancelling' and next_status not in ('cancelling','cancelled'))
  ) then return 'terminal'; end if;

  -- Only whitelisted columns are identifiers. Values remain a bound parameter,
  -- parsed using the existing table's types; absent fields are never cleared.
  select string_agg(format('%I = (jsonb_populate_record(null::public.video_tasks,$1)).%I',k,k), ',')
    into assignments from jsonb_object_keys(p_patch) k;
  execute format('update public.video_tasks set %s where id=$2',assignments) using p_patch,p_task;
  return 'applied';
end $$;

revoke all on function public.update_video_task_ordered(text,jsonb,uuid,text,uuid) from public,anon,authenticated;
grant execute on function public.update_video_task_ordered(text,jsonb,uuid,text,uuid) to service_role;
notify pgrst, 'reload schema';
