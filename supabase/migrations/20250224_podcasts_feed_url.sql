-- Run in Supabase → SQL Editor if you see PGRST204 / "feed_url" schema cache errors.
-- Safe to run multiple times.

ALTER TABLE public.podcasts
  ADD COLUMN IF NOT EXISTS feed_url TEXT DEFAULT '';

ALTER TABLE public.podcasts
  ADD COLUMN IF NOT EXISTS platform TEXT DEFAULT 'xiaoyuzhou';

-- PostgREST usually reloads the schema within ~1 minute. If errors persist, restart the project
-- in Supabase Dashboard → Settings → Infrastructure, or run: NOTIFY pgrst, 'reload schema';
-- (as a superuser / via SQL Editor when allowed).
