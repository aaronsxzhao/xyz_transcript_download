-- Manual recovery is a conditional commit, never an ordinary worker final save.
create function public.recover_video_note_ordered(p_user uuid,p_task text,p_expected timestamptz,p_payload jsonb)
returns text language plpgsql security invoker set search_path=public as $$
declare t public.video_tasks%rowtype; w public.processing_work%rowtype; baseline jsonb;
begin
  if p_payload->>'task_id' is distinct from p_task or p_payload->>'user_id' is distinct from p_user::text then
    return 'not_found';
  end if;
  perform pg_advisory_xact_lock(hashtextextended(p_user::text||':video:'||p_task,0));
  perform 1 from processing_work where user_id=p_user and kind='video' and task_id=p_task order by id for update;
  if exists(select 1 from processing_work where user_id=p_user and kind='video' and task_id=p_task and state in ('queued','running')) then return 'busy'; end if;
  select * into t from video_tasks where id=p_task and user_id=p_user for update;
  if not found then return 'not_found'; end if;
  if t.status not in ('failed','cancelled','success') then return 'busy'; end if;
  if t.updated_at is distinct from p_expected then return 'changed'; end if;
  if t.status='success' and t.markdown=p_payload->>'content'
    and exists(select 1 from video_task_versions where task_id=p_task and id=p_payload->>'version_id' and content=p_payload->>'content') then
    return 'already_saved';
  end if;
  if jsonb_typeof(p_payload->'recovery_order'->'base_versions') is distinct from 'array' then return 'unverified'; end if;
  select * into w from processing_work where user_id=p_user and kind='video' and task_id=p_task order by created_at desc,id desc limit 1;
  if w.id::text is distinct from p_payload->'recovery_order'->>'work_id' then return 'superseded'; end if;
  if w.id is not null and w.attempts is distinct from (p_payload->'recovery_order'->>'work_attempt')::integer then return 'superseded'; end if;
  select coalesce(jsonb_agg(id order by id),'[]'::jsonb) into baseline from video_task_versions
    where task_id=p_task and id<>p_payload->>'version_id';
  if baseline is distinct from p_payload->'recovery_order'->'base_versions' then return 'superseded'; end if;
  if t.status='success' and t.markdown is distinct from p_payload->>'content' then return 'superseded'; end if;
  perform complete_user_video_note(p_user,p_task,p_payload->>'version_id',p_payload->>'content',
    p_payload->>'style',p_payload->>'model',coalesce(p_payload->>'warning',''));
  return 'applied';
end $$;
revoke all on function public.recover_video_note_ordered(uuid,text,timestamptz,jsonb) from public,anon,authenticated;
grant execute on function public.recover_video_note_ordered(uuid,text,timestamptz,jsonb) to service_role;
notify pgrst, 'reload schema';
