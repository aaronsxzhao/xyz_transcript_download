create table public.content_updates (
  user_id uuid not null references auth.users(id) on delete cascade,
  item_key text not null,
  kind text not null check (kind in ('podcast','video')),
  title text not null,
  source_title text not null default '',
  source_id text not null default '',
  created_at timestamptz not null default now(),
  dismissed_at timestamptz,
  primary key (user_id,item_key)
);
alter table public.content_updates enable row level security;
revoke all on public.content_updates from anon, authenticated;
grant all on public.content_updates to service_role;
create index content_updates_unread on public.content_updates(user_id,created_at desc,item_key) where dismissed_at is null;

create function public.record_content_update() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
  if TG_OP = 'DELETE' then
    if TG_TABLE_NAME='episodes' then
      delete from public.content_updates where user_id=OLD.user_id and item_key='podcast:'||OLD.eid;
    else
      delete from public.content_updates where user_id=OLD.user_id and item_key='video:'||OLD.id;
    end if;
    return OLD;
  end if;
  if NEW.user_id is null then return NEW; end if;
  if TG_TABLE_NAME='episodes' then
    insert into public.content_updates(user_id,item_key,kind,title,source_title,source_id)
    values (NEW.user_id,'podcast:'||NEW.eid,'podcast',NEW.title,
      coalesce((select p.title from public.podcasts p where p.id=NEW.podcast_id and p.user_id=NEW.user_id),''),NEW.pid)
    on conflict(user_id,item_key) do nothing;
  else
    insert into public.content_updates(user_id,item_key,kind,title,source_title,source_id)
    values (NEW.user_id,'video:'||NEW.id,'video',NEW.title,coalesce(NEW.channel,''),NEW.id)
    on conflict(user_id,item_key) do update set title=excluded.title,source_title=excluded.source_title;
  end if;
  return NEW;
end; $$;
revoke all on function public.record_content_update() from public,anon,authenticated;
grant execute on function public.record_content_update() to service_role;
create trigger episode_content_update after insert or delete on public.episodes
  for each row execute function public.record_content_update();
create trigger video_content_update after insert or delete or update of title,channel on public.video_tasks
  for each row execute function public.record_content_update();

-- Recover recent discoveries missed by the previous ephemeral notifications.
insert into public.content_updates(user_id,item_key,kind,title,source_title,source_id,created_at)
select e.user_id,'podcast:'||e.eid,'podcast',e.title,p.title,e.pid,e.created_at
from public.episodes e join public.podcasts p on p.id=e.podcast_id and p.user_id=e.user_id
where e.created_at>now()-interval '7 days'
on conflict do nothing;
insert into public.content_updates(user_id,item_key,kind,title,source_title,source_id,created_at)
select user_id,'video:'||id,'video',title,coalesce(channel,''),id,created_at from public.video_tasks
where user_id is not null and created_at>now()-interval '7 days'
on conflict do nothing;
