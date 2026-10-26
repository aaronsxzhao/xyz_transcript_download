-- Service-owned durable admission, leases and successful per-segment results.
create table public.processing_work (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null check (kind in ('podcast','video')),
  task_id text not null,
  source_id text not null,
  payload jsonb not null default '{}'::jsonb,
  state text not null default 'queued' check (state in ('queued','running','completed','failed','cancelled')),
  cancel_requested boolean not null default false,
  worker_id text,
  worker_group text,
  lease_until timestamptz,
  attempts integer not null default 0,
  metrics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index processing_work_active_state on public.processing_work(user_id,kind,task_id,state) where state in ('queued','running');
create index processing_work_ready on public.processing_work(state,created_at,lease_until);
create index processing_work_owned_task on public.processing_work(user_id,kind,task_id,created_at desc);

create table public.processing_checkpoints (
  user_id uuid not null references auth.users(id) on delete cascade,
  source_id text not null,
  stage text not null,
  fingerprint text not null,
  result jsonb not null check (pg_column_size(result) <= 1048576),
  created_at timestamptz not null default now(),
  primary key(user_id,source_id,stage,fingerprint)
);
create index processing_checkpoints_age on public.processing_checkpoints(created_at);
create table public.processing_controls (
  name text primary key,
  target_revision text not null,
  expires_at timestamptz not null
);

alter table public.processing_work enable row level security;
alter table public.processing_checkpoints enable row level security;
alter table public.processing_controls enable row level security;
revoke all on public.processing_work,public.processing_checkpoints,public.processing_controls from public,anon,authenticated;
grant all on public.processing_work,public.processing_checkpoints,public.processing_controls to service_role;

create function public.enqueue_processing_work(p_user uuid,p_kind text,p_task text,p_source text,p_payload jsonb)
returns uuid language plpgsql security invoker set search_path=public as $$
declare existing uuid; result uuid;
begin
  -- Serialize admission for this owned task, including simultaneous retries.
  perform pg_advisory_xact_lock(hashtextextended(p_user::text||':'||p_kind||':'||p_task,0));
  select id into existing from processing_work where user_id=p_user and kind=p_kind and task_id=p_task
    and state in ('queued','running') and not cancel_requested order by created_at desc limit 1;
  if existing is not null then return existing; end if;
  insert into processing_work(user_id,kind,task_id,source_id,payload)
    values(p_user,p_kind,p_task,p_source,p_payload) returning id into result;
  return result;
end $$;

create function public.claim_processing_work(p_worker text,p_group text,p_revision text,p_lease integer default 90)
returns setof public.processing_work language plpgsql security invoker set search_path=public as $$
begin
  if p_group='embedded' and exists(select 1 from processing_controls where name='drain_embedded'
    and expires_at>now() and target_revision<>p_revision) then return; end if;
  return query with candidate as (
    select q.id from processing_work q
    where ((q.state='queued' and not q.cancel_requested) or (q.state='running' and q.lease_until<now()))
    and not exists(select 1 from processing_work other where other.user_id=q.user_id and other.kind=q.kind
      and other.task_id=q.task_id and other.id<>q.id and other.state='running' and other.lease_until>=now())
    order by q.created_at,q.id for update of q skip locked limit 1
  ) update processing_work q set
    state=case when q.cancel_requested then 'cancelled' when q.attempts>=3 then 'failed' else 'running' end,
    worker_id=p_worker,worker_group=p_group,
    lease_until=now()+make_interval(secs=>greatest(30,least(p_lease,300))),
    attempts=q.attempts+1,updated_at=now()
    from candidate where q.id=candidate.id returning q.*;
end $$;

create function public.heartbeat_processing_work(p_id uuid,p_worker text,p_metrics jsonb,p_lease integer default 90)
returns setof public.processing_work language sql security invoker set search_path=public as $$
  update processing_work set lease_until=now()+make_interval(secs=>greatest(30,least(p_lease,300))),
    metrics=p_metrics,updated_at=now()
  where id=p_id and worker_id=p_worker and state='running' and lease_until>now() returning *;
$$;

create function public.finish_processing_work(p_id uuid,p_worker text,p_state text,p_metrics jsonb)
returns boolean language plpgsql security invoker set search_path=public as $$
begin
  if p_state not in ('completed','failed','cancelled','queued') then raise exception 'Invalid work state'; end if;
  update processing_work set state=case when cancel_requested then 'cancelled' else p_state end,
    attempts=case when p_state='queued' then greatest(0,attempts-1) else attempts end,
    metrics=p_metrics,updated_at=now(),worker_id=null,lease_until=null
    where id=p_id and worker_id=p_worker and state='running' and lease_until>now();
  return found;
end $$;

revoke all on function public.enqueue_processing_work(uuid,text,text,text,jsonb) from public,anon,authenticated;
revoke all on function public.claim_processing_work(text,text,text,integer) from public,anon,authenticated;
revoke all on function public.heartbeat_processing_work(uuid,text,jsonb,integer) from public,anon,authenticated;
revoke all on function public.finish_processing_work(uuid,text,text,jsonb) from public,anon,authenticated;
grant execute on function public.enqueue_processing_work(uuid,text,text,text,jsonb) to service_role;
grant execute on function public.claim_processing_work(text,text,text,integer) to service_role;
grant execute on function public.heartbeat_processing_work(uuid,text,jsonb,integer) to service_role;
grant execute on function public.finish_processing_work(uuid,text,text,jsonb) to service_role;
