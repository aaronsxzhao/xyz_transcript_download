-- One service-only read returns metadata plus bounded episode content.
CREATE OR REPLACE FUNCTION public.podcast_content_index(
    owner_id uuid, preview_limit integer DEFAULT 12,
    only_pid text DEFAULT NULL, page_offset integer DEFAULT 0
) RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
WITH owned AS MATERIALIZED (
    SELECT p.* FROM public.podcasts p
    WHERE p.user_id = owner_id AND (only_pid IS NULL OR p.pid = only_pid)
), metadata AS (
    SELECT p.id, p.pid, jsonb_build_object(
        'pid',p.pid,'title',p.title,'author',coalesce(p.author,''),
        'description',coalesce(p.description,''),'cover_url',coalesce(p.cover_url,''),
        'platform',coalesce(nullif(p.platform,''),'xiaoyuzhou'),'feed_url',coalesce(p.feed_url,''),
        'episode_count',(SELECT count(*) FROM public.episodes e WHERE e.user_id=owner_id AND e.pid=p.pid),
        'summarized_count',(SELECT count(*) FROM public.episodes e JOIN public.summaries s ON s.user_id=e.user_id AND s.episode_id=e.eid WHERE e.user_id=owner_id AND e.pid=p.pid)
    ) AS item FROM owned p
), preview_podcasts AS (
    SELECT p.pid FROM owned p ORDER BY p.id DESC LIMIT 24
), previews AS (
    SELECT p.pid, coalesce((SELECT jsonb_agg(row.item ORDER BY row.pub_date DESC, row.id DESC) FROM (
        SELECT e.id, e.pub_date, jsonb_build_object(
            'eid',e.eid,'pid',e.pid,'title',e.title,'description',left(coalesce(e.description,''),280),
            'duration',coalesce(e.duration,0),'pub_date',coalesce(e.pub_date,''),
            'status',coalesce(e.status,'pending'),'created_at',coalesce(e.created_at::text,''),
            'has_transcript',EXISTS(SELECT 1 FROM public.transcripts t WHERE t.user_id=owner_id AND t.episode_id=e.eid),
            'has_summary',s.id IS NOT NULL,'topics_count',coalesce(cardinality(s.topics),0),
            'key_points_count',(SELECT count(*) FROM public.summary_key_points k WHERE k.summary_id=s.id)
        ) AS item
        FROM public.episodes e LEFT JOIN public.summaries s ON s.user_id=e.user_id AND s.episode_id=e.eid
        WHERE e.user_id=owner_id AND e.pid=p.pid
        ORDER BY e.pub_date DESC, e.id DESC
        LIMIT greatest(1,least(preview_limit,50)) OFFSET greatest(page_offset,0)
    ) row),'[]'::jsonb) AS items FROM preview_podcasts p
)
SELECT jsonb_build_object(
    'podcasts',coalesce((SELECT jsonb_agg(item ORDER BY id DESC) FROM metadata),'[]'::jsonb),
    'previews',coalesce((SELECT jsonb_object_agg(pid,items) FROM previews),'{}'::jsonb)
);
$$;
REVOKE ALL ON FUNCTION public.podcast_content_index(uuid,integer,text,integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.podcast_content_index(uuid,integer,text,integer) TO service_role;
NOTIFY pgrst, 'reload schema';
