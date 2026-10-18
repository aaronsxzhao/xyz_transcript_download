-- Run before deploying the account-isolation fixes.
-- Shared cookies cannot safely be assigned to an account. Users must reconnect.
SET LOCAL lock_timeout = '5s';
CREATE TABLE IF NOT EXISTS public.platform_cookies (
    id BIGSERIAL PRIMARY KEY, platform TEXT UNIQUE NOT NULL,
    cookie_data TEXT NOT NULL DEFAULT '', updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.platform_cookies ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.platform_cookies FROM anon, authenticated;
GRANT ALL ON TABLE public.platform_cookies TO service_role;
DROP POLICY IF EXISTS "Service role full access platform_cookies" ON public.platform_cookies;
DROP POLICY IF EXISTS "Service role full access" ON public.platform_cookies;

CREATE TABLE IF NOT EXISTS public.user_platform_cookies (
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    cookie_data TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, platform)
);
ALTER TABLE public.user_platform_cookies ENABLE ROW LEVEL SECURITY;
-- The API checks ownership and accesses credentials through its service role.
REVOKE ALL ON TABLE public.user_platform_cookies FROM anon, authenticated;
GRANT ALL ON TABLE public.user_platform_cookies TO service_role;

CREATE TABLE IF NOT EXISTS public.user_settings (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    preferences JSONB NOT NULL DEFAULT '{}'
);
ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.user_settings FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.user_settings TO authenticated;
DROP POLICY IF EXISTS "Users manage own settings" ON public.user_settings;
CREATE POLICY "Users manage own settings" ON public.user_settings
    FOR ALL TO authenticated USING ((SELECT auth.uid()) = user_id) WITH CHECK ((SELECT auth.uid()) = user_id);
GRANT ALL ON TABLE public.user_settings TO service_role;

-- Replace metadata and key points in one transaction. A failed replacement
-- leaves the last successful summary intact.
CREATE OR REPLACE FUNCTION public.save_user_summary(
    p_user_id UUID, p_episode_id TEXT, p_title TEXT, p_overview TEXT,
    p_topics TEXT[], p_takeaways TEXT[], p_key_points JSONB
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE summary_row_id INTEGER;
BEGIN
    INSERT INTO summaries (user_id, episode_id, title, overview, topics, takeaways)
    VALUES (p_user_id, p_episode_id, p_title, p_overview, p_topics, p_takeaways)
    ON CONFLICT (user_id, episode_id) DO UPDATE SET
        title = EXCLUDED.title, overview = EXCLUDED.overview,
        topics = EXCLUDED.topics, takeaways = EXCLUDED.takeaways
    RETURNING id INTO summary_row_id;
    DELETE FROM summary_key_points WHERE summary_id = summary_row_id;
    INSERT INTO summary_key_points (summary_id, topic, summary, original_quote, timestamp)
    SELECT summary_row_id, COALESCE(point->>'topic', ''), COALESCE(point->>'summary', ''),
        COALESCE(point->>'original_quote', ''), COALESCE(point->>'timestamp', '')
    FROM jsonb_array_elements(p_key_points) AS point;
    RETURN TRUE;
END;
$$;
REVOKE ALL ON FUNCTION public.save_user_summary(UUID, TEXT, TEXT, TEXT, TEXT[], TEXT[], JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.save_user_summary(UUID, TEXT, TEXT, TEXT, TEXT[], TEXT[], JSONB) TO service_role;

NOTIFY pgrst, 'reload schema';

-- Keep existing media working until the new API is deployed. Make the media
-- buckets private after deployment using the rollout SQL in README.md.
