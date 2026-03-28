-- Align older video_tasks tables with current app (PGRST204 / schema cache).
-- Run in Supabase → SQL Editor if video note creation fails for unknown columns.

ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS thumbnail TEXT DEFAULT '';
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS markdown TEXT DEFAULT '';
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS transcript_json TEXT DEFAULT '';
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS style TEXT DEFAULT 'detailed';
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS model TEXT DEFAULT '';
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS formats JSONB DEFAULT '[]'::jsonb;
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS quality TEXT DEFAULT 'medium';
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS video_quality TEXT DEFAULT '720';
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS extras TEXT DEFAULT '';
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS video_understanding BOOLEAN DEFAULT FALSE;
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS video_interval INTEGER DEFAULT 4;
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS grid_cols INTEGER DEFAULT 3;
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS grid_rows INTEGER DEFAULT 3;
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS duration REAL DEFAULT 0;
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS max_output_tokens INTEGER DEFAULT 0;
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS error TEXT DEFAULT '';
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS channel TEXT DEFAULT '';
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS channel_url TEXT DEFAULT '';
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS channel_avatar TEXT DEFAULT '';
ALTER TABLE public.video_tasks ADD COLUMN IF NOT EXISTS published_at TEXT DEFAULT '';
