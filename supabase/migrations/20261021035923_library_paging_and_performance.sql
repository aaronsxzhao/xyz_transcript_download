-- Additive, service-only read model. Every API query must also bind user_id.
CREATE OR REPLACE VIEW public.library_items WITH (security_invoker = true) AS
SELECT s.user_id, s.episode_id AS id, 'podcast'::text AS kind, s.title,
       coalesce(nullif(p.title,''),'Podcast') AS source, s.created_at AS date,
       'completed'::text AS status,
       to_char(coalesce(s.created_at, 'epoch'::timestamptz) AT TIME ZONE 'UTC', 'YYYYMMDDHH24MISSUS') || ':podcast:' || s.episode_id AS sort_key,
       coalesce(s.title,'') || ' ' || coalesce(p.title,'') AS search_text
FROM public.summaries s
LEFT JOIN public.episodes e ON e.user_id=s.user_id AND e.eid=s.episode_id
LEFT JOIN public.podcasts p ON p.user_id=s.user_id AND p.id=e.podcast_id
UNION ALL
SELECT v.user_id, v.id, 'video'::text, coalesce(nullif(v.title,''),'Untitled video'),
       coalesce(nullif(v.channel,''),nullif(v.platform,''),'Video'), coalesce(v.updated_at,v.created_at),
       CASE WHEN v.status='success' THEN 'completed' ELSE v.status END,
       to_char(coalesce(v.updated_at,v.created_at,'epoch'::timestamptz) AT TIME ZONE 'UTC','YYYYMMDDHH24MISSUS') || ':video:' || v.id,
       coalesce(v.title,'') || ' ' || coalesce(nullif(v.channel,''),v.platform,'')
FROM public.video_tasks v WHERE v.status <> 'discovered';
REVOKE ALL ON public.library_items FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.library_items TO service_role;

CREATE TABLE IF NOT EXISTS public.page_performance (
  user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  samples jsonb NOT NULL DEFAULT '[]'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.page_performance ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.page_performance FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.page_performance TO service_role;
-- Atomic bounded append; callable only by the backend. No private URLs/content.
CREATE OR REPLACE FUNCTION public.append_page_performance(owner_id uuid, sample jsonb)
RETURNS void LANGUAGE sql SECURITY INVOKER SET search_path = '' AS $$
  INSERT INTO public.page_performance(user_id,samples,updated_at)
  VALUES (owner_id,jsonb_build_array(sample),now())
  ON CONFLICT(user_id) DO UPDATE SET samples = (
    SELECT coalesce(jsonb_agg(value ORDER BY ord),'[]'::jsonb)
    FROM jsonb_array_elements(public.page_performance.samples || EXCLUDED.samples) WITH ORDINALITY AS t(value,ord)
    WHERE ord > greatest(jsonb_array_length(public.page_performance.samples)+1-128,0)
  ), updated_at=now();
$$;
REVOKE ALL ON FUNCTION public.append_page_performance(uuid,jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.append_page_performance(uuid,jsonb) TO service_role;
NOTIFY pgrst, 'reload schema';
