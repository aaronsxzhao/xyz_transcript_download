-- Evaluate cancellation against the locked current row, never a client snapshot.
create function public.cancel_processing_work(p_user uuid,p_kind text,p_task text,p_deleted boolean default false)
returns void language sql security invoker set search_path='' as $$
  update public.processing_work
  set cancel_requested=true,
      state=case when state='queued' then 'cancelled' else state end,
      payload=case when p_deleted then payload || '{"deleted":true}'::jsonb else payload end,
      updated_at=now()
  where user_id=p_user and kind=p_kind and task_id=p_task
    and state in ('queued','running');
$$;
revoke all on function public.cancel_processing_work(uuid,text,text,boolean) from public,anon,authenticated;
grant execute on function public.cancel_processing_work(uuid,text,text,boolean) to service_role;
