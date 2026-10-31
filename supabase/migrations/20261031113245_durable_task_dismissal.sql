-- Acknowledging task history must not delete the saved note or depend on a browser.
alter table public.video_tasks add column if not exists task_dismissed boolean;

-- NULL preserves browser-only acknowledgements from older clients until a new attempt.
-- New processing attempts become visible even if the previous attempt was dismissed.
create or replace function public.reset_video_task_dismissal() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
  if NEW.status not in ('success','failed','cancelled') then
    NEW.task_dismissed := false;
  end if;
  return NEW;
end; $$;
revoke all on function public.reset_video_task_dismissal() from public,anon,authenticated;
grant execute on function public.reset_video_task_dismissal() to service_role;
create trigger video_task_dismissal_attempt before update of status on public.video_tasks
for each row execute function public.reset_video_task_dismissal();
