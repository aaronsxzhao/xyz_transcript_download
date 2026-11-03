-- Opaque diagnostic tokens are managed by operators, never by public API users.
create table public.platform_test_tokens (
    token_digest text primary key check (token_digest ~ '^[0-9a-f]{64}$'),
    owner_id uuid not null references auth.users(id) on delete cascade,
    scopes text[] not null check (scopes <@ array['content:read','diagnostics:run','models:probe']::text[]),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null check (expires_at > created_at and expires_at <= created_at + interval '90 days'),
    revoked_at timestamptz,
    read_window timestamptz not null default now(),
    read_count integer not null default 0,
    probe_window timestamptz not null default now(),
    probe_count integer not null default 0,
    total_requests bigint not null default 0,
    last_used_at timestamptz,
    last_route text
);
alter table public.platform_test_tokens enable row level security;
revoke all on public.platform_test_tokens from public, anon, authenticated;
grant select, insert, update, delete on public.platform_test_tokens to service_role;

create function public.consume_platform_test_token(p_digest text, p_scope text, p_route text)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    t public.platform_test_tokens%rowtype;
    stamp timestamptz := clock_timestamp();
begin
    select * into t from public.platform_test_tokens where token_digest=p_digest for update;
    if not found or t.revoked_at is not null or t.expires_at <= stamp then
        return jsonb_build_object('status','invalid');
    end if;
    if not (p_scope = any(t.scopes)) then
        return jsonb_build_object('status','denied');
    end if;
    if p_scope = 'content:read' then
        if t.read_window <= stamp - interval '1 minute' then
            t.read_count := 0; t.read_window := stamp;
        end if;
        if t.read_count >= 120 then return jsonb_build_object('status','limited'); end if;
        t.read_count := t.read_count + 1;
    else
        if t.probe_window <= stamp - interval '1 hour' then
            t.probe_count := 0; t.probe_window := stamp;
        end if;
        if t.probe_count >= 6 then return jsonb_build_object('status','limited'); end if;
        t.probe_count := t.probe_count + 1;
    end if;
    update public.platform_test_tokens set
        read_count=t.read_count, read_window=t.read_window,
        probe_count=t.probe_count, probe_window=t.probe_window,
        total_requests=total_requests+1, last_used_at=stamp, last_route=left(p_route,160)
        where token_digest=p_digest;
    return jsonb_build_object('status','ok','owner_id',t.owner_id);
end;
$$;
revoke all on function public.consume_platform_test_token(text,text,text) from public, anon, authenticated;
grant execute on function public.consume_platform_test_token(text,text,text) to service_role;
