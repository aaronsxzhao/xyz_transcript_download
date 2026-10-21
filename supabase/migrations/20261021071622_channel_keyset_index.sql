-- Supports bounded owner/channel reads in either chronological direction.
CREATE INDEX IF NOT EXISTS video_tasks_channel_page_idx
ON public.video_tasks (user_id, platform, channel, created_at DESC, id DESC);
