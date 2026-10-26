-- Hold the queue lease row during final writes, so an expired worker cannot
-- publish after a new worker has claimed the same work.
create or replace function public.require_processing_lease(p_work uuid,p_worker text,p_user uuid)
returns void language plpgsql security invoker set search_path=public as $$
begin
  perform id from processing_work where id=p_work and user_id=p_user
    and worker_id=p_worker and state='running' and not cancel_requested
    and lease_until>now() for update;
  if not found then raise exception 'Processing lease is no longer current' using errcode='55000'; end if;
end $$;

create or replace function public.complete_leased_video_note(p_work uuid,p_worker text,
  p_user_id uuid,p_task_id text,p_version_id text,p_content text,p_style text,p_model text,p_warning text)
returns boolean language plpgsql security invoker set search_path=public as $$
begin
  perform require_processing_lease(p_work,p_worker,p_user_id);
  if not exists(select 1 from processing_work where id=p_work and kind='video' and task_id=p_task_id) then
    raise exception 'Processing task does not match';
  end if;
  return complete_user_video_note(p_user_id,p_task_id,p_version_id,p_content,p_style,p_model,p_warning);
end $$;

create or replace function public.save_leased_summary(p_work uuid,p_worker text,
  p_user_id uuid,p_episode_id text,p_title text,p_overview text,p_topics text[],p_takeaways text[],p_key_points jsonb)
returns boolean language plpgsql security invoker set search_path=public as $$
begin
  perform require_processing_lease(p_work,p_worker,p_user_id);
  return save_user_summary(p_user_id,p_episode_id,p_title,p_overview,p_topics,p_takeaways,p_key_points);
end $$;

create or replace function public.save_processing_transcript(p_work uuid,p_worker text,
  p_user_id uuid,p_episode_id text,p_language text,p_duration double precision,p_text text,p_segments jsonb)
returns boolean language plpgsql security invoker set search_path=public as $$
declare saved_transcript_id integer;
begin
  perform require_processing_lease(p_work,p_worker,p_user_id);
  insert into transcripts(user_id,episode_id,language,duration,text)
    values(p_user_id,p_episode_id,p_language,p_duration,p_text)
    on conflict(user_id,episode_id) do update set language=excluded.language,duration=excluded.duration,text=excluded.text
    returning id into saved_transcript_id;
  delete from transcript_segments where transcript_segments.transcript_id=saved_transcript_id;
  insert into transcript_segments(transcript_id,start_time,end_time,text)
    select saved_transcript_id,(segment->>'start')::double precision,(segment->>'end')::double precision,coalesce(segment->>'text','')
    from jsonb_array_elements(p_segments) as segment;
  return true;
end $$;

revoke all on function public.require_processing_lease(uuid,text,uuid) from public,anon,authenticated;
revoke all on function public.complete_leased_video_note(uuid,text,uuid,text,text,text,text,text,text) from public,anon,authenticated;
revoke all on function public.save_leased_summary(uuid,text,uuid,text,text,text,text[],text[],jsonb) from public,anon,authenticated;
revoke all on function public.save_processing_transcript(uuid,text,uuid,text,text,double precision,text,jsonb) from public,anon,authenticated;
grant execute on function public.require_processing_lease(uuid,text,uuid) to service_role;
grant execute on function public.complete_leased_video_note(uuid,text,uuid,text,text,text,text,text,text) to service_role;
grant execute on function public.save_leased_summary(uuid,text,uuid,text,text,text,text[],text[],jsonb) to service_role;
grant execute on function public.save_processing_transcript(uuid,text,uuid,text,text,double precision,text,jsonb) to service_role;
notify pgrst, 'reload schema';
