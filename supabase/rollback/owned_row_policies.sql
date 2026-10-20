-- Restore only the previous policies; never restore historical rows over newer notes.
DROP POLICY IF EXISTS "Users can delete own episodes" ON public."episodes";
CREATE POLICY "Users can delete own episodes" ON public."episodes" FOR DELETE TO public USING ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can insert own episodes" ON public."episodes";
CREATE POLICY "Users can insert own episodes" ON public."episodes" FOR INSERT TO public WITH CHECK ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can update own episodes" ON public."episodes";
CREATE POLICY "Users can update own episodes" ON public."episodes" FOR UPDATE TO public USING ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can view own episodes" ON public."episodes";
CREATE POLICY "Users can view own episodes" ON public."episodes" FOR SELECT TO public USING ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can delete own podcasts" ON public."podcasts";
CREATE POLICY "Users can delete own podcasts" ON public."podcasts" FOR DELETE TO public USING ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can insert own podcasts" ON public."podcasts";
CREATE POLICY "Users can insert own podcasts" ON public."podcasts" FOR INSERT TO public WITH CHECK ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can update own podcasts" ON public."podcasts";
CREATE POLICY "Users can update own podcasts" ON public."podcasts" FOR UPDATE TO public USING ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can view own podcasts" ON public."podcasts";
CREATE POLICY "Users can view own podcasts" ON public."podcasts" FOR SELECT TO public USING ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can delete own summaries" ON public."summaries";
CREATE POLICY "Users can delete own summaries" ON public."summaries" FOR DELETE TO public USING ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can insert own summaries" ON public."summaries";
CREATE POLICY "Users can insert own summaries" ON public."summaries" FOR INSERT TO public WITH CHECK ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can update own summaries" ON public."summaries";
CREATE POLICY "Users can update own summaries" ON public."summaries" FOR UPDATE TO public USING ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can view own summaries" ON public."summaries";
CREATE POLICY "Users can view own summaries" ON public."summaries" FOR SELECT TO public USING ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can delete own summary key points" ON public."summary_key_points";
CREATE POLICY "Users can delete own summary key points" ON public."summary_key_points" FOR DELETE TO public USING ((EXISTS ( SELECT 1
   FROM summaries s
  WHERE ((s.id = summary_key_points.summary_id) AND (s.user_id = auth.uid())))));
DROP POLICY IF EXISTS "Users can insert own summary key points" ON public."summary_key_points";
CREATE POLICY "Users can insert own summary key points" ON public."summary_key_points" FOR INSERT TO public WITH CHECK ((EXISTS ( SELECT 1
   FROM summaries s
  WHERE ((s.id = summary_key_points.summary_id) AND (s.user_id = auth.uid())))));
DROP POLICY IF EXISTS "Users can view own summary key points" ON public."summary_key_points";
CREATE POLICY "Users can view own summary key points" ON public."summary_key_points" FOR SELECT TO public USING ((EXISTS ( SELECT 1
   FROM summaries s
  WHERE ((s.id = summary_key_points.summary_id) AND (s.user_id = auth.uid())))));
DROP POLICY IF EXISTS "Users can delete own transcript segments" ON public."transcript_segments";
CREATE POLICY "Users can delete own transcript segments" ON public."transcript_segments" FOR DELETE TO public USING ((EXISTS ( SELECT 1
   FROM transcripts t
  WHERE ((t.id = transcript_segments.transcript_id) AND (t.user_id = auth.uid())))));
DROP POLICY IF EXISTS "Users can insert own transcript segments" ON public."transcript_segments";
CREATE POLICY "Users can insert own transcript segments" ON public."transcript_segments" FOR INSERT TO public WITH CHECK ((EXISTS ( SELECT 1
   FROM transcripts t
  WHERE ((t.id = transcript_segments.transcript_id) AND (t.user_id = auth.uid())))));
DROP POLICY IF EXISTS "Users can view own transcript segments" ON public."transcript_segments";
CREATE POLICY "Users can view own transcript segments" ON public."transcript_segments" FOR SELECT TO public USING ((EXISTS ( SELECT 1
   FROM transcripts t
  WHERE ((t.id = transcript_segments.transcript_id) AND (t.user_id = auth.uid())))));
DROP POLICY IF EXISTS "Users can delete own transcripts" ON public."transcripts";
CREATE POLICY "Users can delete own transcripts" ON public."transcripts" FOR DELETE TO public USING ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can insert own transcripts" ON public."transcripts";
CREATE POLICY "Users can insert own transcripts" ON public."transcripts" FOR INSERT TO public WITH CHECK ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can update own transcripts" ON public."transcripts";
CREATE POLICY "Users can update own transcripts" ON public."transcripts" FOR UPDATE TO public USING ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can view own transcripts" ON public."transcripts";
CREATE POLICY "Users can view own transcripts" ON public."transcripts" FOR SELECT TO public USING ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Service role full access video_task_versions" ON public."video_task_versions";
CREATE POLICY "Service role full access video_task_versions" ON public."video_task_versions" FOR ALL TO public USING ((auth.role() = 'service_role'::text));
DROP POLICY IF EXISTS "Users can delete own video task versions" ON public."video_task_versions";
CREATE POLICY "Users can delete own video task versions" ON public."video_task_versions" FOR DELETE TO public USING ((EXISTS ( SELECT 1
   FROM video_tasks t
  WHERE ((t.id = video_task_versions.task_id) AND (t.user_id = auth.uid())))));
DROP POLICY IF EXISTS "Users can insert own video task versions" ON public."video_task_versions";
CREATE POLICY "Users can insert own video task versions" ON public."video_task_versions" FOR INSERT TO public WITH CHECK ((EXISTS ( SELECT 1
   FROM video_tasks t
  WHERE ((t.id = video_task_versions.task_id) AND (t.user_id = auth.uid())))));
DROP POLICY IF EXISTS "Users can view own video task versions" ON public."video_task_versions";
CREATE POLICY "Users can view own video task versions" ON public."video_task_versions" FOR SELECT TO public USING ((EXISTS ( SELECT 1
   FROM video_tasks t
  WHERE ((t.id = video_task_versions.task_id) AND (t.user_id = auth.uid())))));
DROP POLICY IF EXISTS "Service role full access video_tasks" ON public."video_tasks";
CREATE POLICY "Service role full access video_tasks" ON public."video_tasks" FOR ALL TO public USING ((auth.role() = 'service_role'::text));
DROP POLICY IF EXISTS "Users can delete own video tasks" ON public."video_tasks";
CREATE POLICY "Users can delete own video tasks" ON public."video_tasks" FOR DELETE TO public USING ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can insert own video tasks" ON public."video_tasks";
CREATE POLICY "Users can insert own video tasks" ON public."video_tasks" FOR INSERT TO public WITH CHECK ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can update own video tasks" ON public."video_tasks";
CREATE POLICY "Users can update own video tasks" ON public."video_tasks" FOR UPDATE TO public USING ((auth.uid() = user_id));
DROP POLICY IF EXISTS "Users can view own video tasks" ON public."video_tasks";
CREATE POLICY "Users can view own video tasks" ON public."video_tasks" FOR SELECT TO public USING ((auth.uid() = user_id));
