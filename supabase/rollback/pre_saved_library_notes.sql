-- Additive date metadata; the existing owner predicates and invoker rights remain.
CREATE OR REPLACE VIEW public.library_items WITH (security_invoker = true) AS
WITH source_items AS (
SELECT s.user_id, s.episode_id AS id, 'podcast'::text AS kind, s.title,
       coalesce(nullif(p.title,''),'Podcast') AS source, s.created_at AS date,
       CASE WHEN coalesce(e.duration,0)>=1800 AND coalesce(cardinality(s.topics),0)=0 AND NOT EXISTS (SELECT 1 FROM public.summary_key_points k WHERE k.summary_id=s.id) THEN 'needs_review' ELSE 'completed' END::text AS status,
       to_char(coalesce(s.created_at, 'epoch'::timestamptz) AT TIME ZONE 'UTC', 'YYYYMMDDHH24MISSUS') || ':podcast:' || s.episode_id AS sort_key,
       coalesce(s.title,'') || ' ' || coalesce(p.title,'') AS search_text,
       coalesce(p.cover_url,'') AS thumbnail, coalesce(nullif(p.platform,''),'xiaoyuzhou') AS platform,
       coalesce(e.duration,0)::double precision AS duration, coalesce(cardinality(s.topics),0) AS topics_count,
       (SELECT count(*)::integer FROM public.summary_key_points k WHERE k.summary_id=s.id) AS key_points_count,
       CASE WHEN p.platform='local' THEN '' ELSE coalesce(e.pub_date,'') END::text AS published_at
FROM public.summaries s
LEFT JOIN public.episodes e ON e.user_id=s.user_id AND e.eid=s.episode_id
LEFT JOIN public.podcasts p ON p.user_id=s.user_id AND p.id=e.podcast_id
UNION ALL
SELECT v.user_id, v.id, 'video'::text, coalesce(nullif(v.title,''),'Untitled video'),
       coalesce(nullif(v.channel,''),nullif(v.platform,''),'Video'), coalesce(v.updated_at,v.created_at),
       CASE WHEN v.status='success' THEN 'completed' ELSE v.status END,
       to_char(coalesce(v.updated_at,v.created_at,'epoch'::timestamptz) AT TIME ZONE 'UTC','YYYYMMDDHH24MISSUS') || ':video:' || v.id,
       coalesce(v.title,'') || ' ' || coalesce(nullif(v.channel,''),v.platform,''),
       coalesce(v.thumbnail,''), coalesce(v.platform,''), coalesce(v.duration,0)::double precision, 0, 0, coalesce(v.published_at,'')::text
FROM public.video_tasks v WHERE v.status <> 'discovered'
)
SELECT source_items.*,
       regexp_replace(coalesce(nullif(left(published_at,10),''),'0000-00-00'),'[^0-9]','','g') || ':' || kind || ':' || id AS publication_sort_key
FROM source_items;
NOTIFY pgrst, 'reload schema';
