do $$ begin
  if not exists(select from pg_roles where rolname='anon') then create role anon; end if;
  if not exists(select from pg_roles where rolname='authenticated') then create role authenticated; end if;
  if not exists(select from pg_roles where rolname='service_role') then create role service_role; end if;
end $$;
create table video_tasks(id text primary key,user_id uuid,status text,updated_at timestamptz,title text,progress real,message text,markdown text,transcript_json text,task_dismissed boolean,thumbnail text,duration real,error text,model text,platform text,source_metadata jsonb,channel text,channel_url text,channel_avatar text,published_at text,style text,formats jsonb,quality text,video_quality text,extras text,video_understanding boolean,video_interval integer,grid_cols integer,grid_rows integer);
create table processing_work(id uuid primary key,user_id uuid,kind text,task_id text,source_id text,state text,worker_id text,lease_until timestamptz,created_at timestamptz,cancel_requested boolean default false);
