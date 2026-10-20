SET LOCAL lock_timeout = '5s';
ALTER POLICY "Users can delete own episodes" ON public."episodes" TO authenticated USING (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can insert own episodes" ON public."episodes" TO authenticated WITH CHECK (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can update own episodes" ON public."episodes" TO authenticated USING (((SELECT auth.uid()) = user_id)) WITH CHECK (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can view own episodes" ON public."episodes" TO authenticated USING (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can delete own podcasts" ON public."podcasts" TO authenticated USING (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can insert own podcasts" ON public."podcasts" TO authenticated WITH CHECK (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can update own podcasts" ON public."podcasts" TO authenticated USING (((SELECT auth.uid()) = user_id)) WITH CHECK (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can view own podcasts" ON public."podcasts" TO authenticated USING (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can delete own summaries" ON public."summaries" TO authenticated USING (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can insert own summaries" ON public."summaries" TO authenticated WITH CHECK (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can update own summaries" ON public."summaries" TO authenticated USING (((SELECT auth.uid()) = user_id)) WITH CHECK (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can view own summaries" ON public."summaries" TO authenticated USING (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can delete own summary key points" ON public."summary_key_points" TO authenticated USING ((EXISTS ( SELECT 1
   FROM summaries s
  WHERE ((s.id = summary_key_points.summary_id) AND (s.user_id = (SELECT auth.uid()))))));
ALTER POLICY "Users can insert own summary key points" ON public."summary_key_points" TO authenticated WITH CHECK ((EXISTS ( SELECT 1
   FROM summaries s
  WHERE ((s.id = summary_key_points.summary_id) AND (s.user_id = (SELECT auth.uid()))))));
ALTER POLICY "Users can view own summary key points" ON public."summary_key_points" TO authenticated USING ((EXISTS ( SELECT 1
   FROM summaries s
  WHERE ((s.id = summary_key_points.summary_id) AND (s.user_id = (SELECT auth.uid()))))));
ALTER POLICY "Users can delete own transcript segments" ON public."transcript_segments" TO authenticated USING ((EXISTS ( SELECT 1
   FROM transcripts t
  WHERE ((t.id = transcript_segments.transcript_id) AND (t.user_id = (SELECT auth.uid()))))));
ALTER POLICY "Users can insert own transcript segments" ON public."transcript_segments" TO authenticated WITH CHECK ((EXISTS ( SELECT 1
   FROM transcripts t
  WHERE ((t.id = transcript_segments.transcript_id) AND (t.user_id = (SELECT auth.uid()))))));
ALTER POLICY "Users can view own transcript segments" ON public."transcript_segments" TO authenticated USING ((EXISTS ( SELECT 1
   FROM transcripts t
  WHERE ((t.id = transcript_segments.transcript_id) AND (t.user_id = (SELECT auth.uid()))))));
ALTER POLICY "Users can delete own transcripts" ON public."transcripts" TO authenticated USING (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can insert own transcripts" ON public."transcripts" TO authenticated WITH CHECK (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can update own transcripts" ON public."transcripts" TO authenticated USING (((SELECT auth.uid()) = user_id)) WITH CHECK (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can view own transcripts" ON public."transcripts" TO authenticated USING (((SELECT auth.uid()) = user_id));
ALTER POLICY "Service role full access video_task_versions" ON public."video_task_versions" TO service_role USING (true) WITH CHECK (true);
ALTER POLICY "Users can delete own video task versions" ON public."video_task_versions" TO authenticated USING ((EXISTS ( SELECT 1
   FROM video_tasks t
  WHERE ((t.id = video_task_versions.task_id) AND (t.user_id = (SELECT auth.uid()))))));
ALTER POLICY "Users can insert own video task versions" ON public."video_task_versions" TO authenticated WITH CHECK ((EXISTS ( SELECT 1
   FROM video_tasks t
  WHERE ((t.id = video_task_versions.task_id) AND (t.user_id = (SELECT auth.uid()))))));
ALTER POLICY "Users can view own video task versions" ON public."video_task_versions" TO authenticated USING ((EXISTS ( SELECT 1
   FROM video_tasks t
  WHERE ((t.id = video_task_versions.task_id) AND (t.user_id = (SELECT auth.uid()))))));
ALTER POLICY "Service role full access video_tasks" ON public."video_tasks" TO service_role USING (true) WITH CHECK (true);
ALTER POLICY "Users can delete own video tasks" ON public."video_tasks" TO authenticated USING (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can insert own video tasks" ON public."video_tasks" TO authenticated WITH CHECK (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can update own video tasks" ON public."video_tasks" TO authenticated USING (((SELECT auth.uid()) = user_id)) WITH CHECK (((SELECT auth.uid()) = user_id));
ALTER POLICY "Users can view own video tasks" ON public."video_tasks" TO authenticated USING (((SELECT auth.uid()) = user_id));
