create policy content_updates_service_access on public.content_updates
  for all to service_role using (true) with check (true);
