CREATE SCHEMA rollback_20261019;
REVOKE ALL ON SCHEMA rollback_20261019 FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA rollback_20261019 TO service_role;
DO $snapshot$ DECLARE t TEXT; BEGIN
FOREACH t IN ARRAY ARRAY['podcasts','episodes','transcripts','summaries','summary_key_points','transcript_segments','video_tasks','video_task_versions','user_settings'] LOOP
  EXECUTE format('CREATE TABLE rollback_20261019.%I AS TABLE public.%I',t,t);
  EXECUTE format('ALTER TABLE rollback_20261019.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON rollback_20261019.%I FROM PUBLIC, anon, authenticated',t);
  EXECUTE format('GRANT SELECT ON rollback_20261019.%I TO service_role',t);
END LOOP; END $snapshot$;
