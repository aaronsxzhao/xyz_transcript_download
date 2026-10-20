SET LOCAL lock_timeout = '5s';
CREATE TABLE IF NOT EXISTS public.processing_jobs (
    id TEXT PRIMARY KEY, user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    payload JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.processing_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.processing_jobs FROM anon, authenticated;
GRANT ALL ON public.processing_jobs TO service_role;
CREATE INDEX IF NOT EXISTS processing_jobs_owner_idx ON public.processing_jobs(user_id);
CREATE INDEX IF NOT EXISTS transcript_segments_transcript_id_idx ON public.transcript_segments(transcript_id);
CREATE INDEX IF NOT EXISTS summary_key_points_summary_id_idx ON public.summary_key_points(summary_id);

CREATE OR REPLACE FUNCTION public.complete_user_video_note(
    p_user_id UUID, p_task_id TEXT, p_version_id TEXT, p_content TEXT,
    p_style TEXT, p_model TEXT, p_warning TEXT
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
BEGIN
    PERFORM id FROM video_tasks WHERE id=p_task_id AND user_id=p_user_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Task not found'; END IF;
    IF EXISTS (SELECT 1 FROM video_task_versions WHERE id=p_version_id
        AND (task_id<>p_task_id OR content IS DISTINCT FROM p_content)) THEN
        RAISE EXCEPTION 'Version already belongs to another save';
    END IF;
    INSERT INTO video_task_versions(id,task_id,content,style,model_name)
        VALUES(p_version_id,p_task_id,p_content,p_style,p_model)
        ON CONFLICT(id) DO NOTHING;
    UPDATE video_tasks SET markdown=p_content, status='success', progress=100,
        message=CASE WHEN p_warning='' THEN 'Notes saved' ELSE 'Notes saved; screenshots need attention' END,
        error=p_warning, updated_at=now() WHERE id=p_task_id AND user_id=p_user_id;
    RETURN true;
END; $$;
REVOKE ALL ON FUNCTION public.complete_user_video_note(UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.complete_user_video_note(UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT) TO service_role;
NOTIFY pgrst, 'reload schema';
