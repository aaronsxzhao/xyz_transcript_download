-- Supabase Schema for XYZ Podcast Transcript Tool
-- Run this in Supabase SQL Editor after creating your project

-- Enable Row Level Security (RLS) for all tables
-- This ensures users can only access their own data

-- Podcasts table (user's subscribed podcasts)
CREATE TABLE IF NOT EXISTS podcasts (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    pid TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    author TEXT DEFAULT '',
    description TEXT DEFAULT '',
    cover_url TEXT DEFAULT '',
    last_checked TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, pid)
);

-- Episodes table (episodes from subscribed podcasts)
CREATE TABLE IF NOT EXISTS episodes (
    id SERIAL PRIMARY KEY,
    podcast_id INTEGER NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    eid TEXT NOT NULL,
    pid TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT DEFAULT '',
    duration INTEGER DEFAULT 0,
    pub_date TEXT DEFAULT '',
    audio_url TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    error_message TEXT DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, eid)
);

-- Transcripts table (stores transcript metadata, content in storage)
CREATE TABLE IF NOT EXISTS transcripts (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    episode_id TEXT NOT NULL,
    language TEXT DEFAULT 'zh',
    duration REAL DEFAULT 0,
    text TEXT DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, episode_id)
);

-- Transcript segments (for timestamped segments)
CREATE TABLE IF NOT EXISTS transcript_segments (
    id SERIAL PRIMARY KEY,
    transcript_id INTEGER NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    text TEXT NOT NULL DEFAULT ''
);

-- Summaries table (stores summary content)
CREATE TABLE IF NOT EXISTS summaries (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    episode_id TEXT NOT NULL,
    title TEXT DEFAULT '',
    overview TEXT DEFAULT '',
    topics TEXT[] DEFAULT '{}',
    takeaways TEXT[] DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, episode_id)
);

-- Key points for summaries
CREATE TABLE IF NOT EXISTS summary_key_points (
    id SERIAL PRIMARY KEY,
    summary_id INTEGER NOT NULL REFERENCES summaries(id) ON DELETE CASCADE,
    topic TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    original_quote TEXT DEFAULT '',
    timestamp TEXT DEFAULT ''
);

-- Enable Row Level Security on all tables
ALTER TABLE podcasts ENABLE ROW LEVEL SECURITY;
ALTER TABLE episodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE transcripts ENABLE ROW LEVEL SECURITY;
ALTER TABLE transcript_segments ENABLE ROW LEVEL SECURITY;
ALTER TABLE summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE summary_key_points ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Users can only access their own data

-- Podcasts policies
CREATE POLICY "Users can view own podcasts" ON podcasts
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own podcasts" ON podcasts
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own podcasts" ON podcasts
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own podcasts" ON podcasts
    FOR DELETE USING (auth.uid() = user_id);

-- Episodes policies
CREATE POLICY "Users can view own episodes" ON episodes
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own episodes" ON episodes
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own episodes" ON episodes
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own episodes" ON episodes
    FOR DELETE USING (auth.uid() = user_id);

-- Transcripts policies
CREATE POLICY "Users can view own transcripts" ON transcripts
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own transcripts" ON transcripts
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own transcripts" ON transcripts
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own transcripts" ON transcripts
    FOR DELETE USING (auth.uid() = user_id);

-- Transcript segments policies (through transcript ownership)
CREATE POLICY "Users can view own transcript segments" ON transcript_segments
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM transcripts t WHERE t.id = transcript_segments.transcript_id AND t.user_id = auth.uid())
    );
CREATE POLICY "Users can insert own transcript segments" ON transcript_segments
    FOR INSERT WITH CHECK (
        EXISTS (SELECT 1 FROM transcripts t WHERE t.id = transcript_segments.transcript_id AND t.user_id = auth.uid())
    );
CREATE POLICY "Users can delete own transcript segments" ON transcript_segments
    FOR DELETE USING (
        EXISTS (SELECT 1 FROM transcripts t WHERE t.id = transcript_segments.transcript_id AND t.user_id = auth.uid())
    );

-- Summaries policies
CREATE POLICY "Users can view own summaries" ON summaries
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own summaries" ON summaries
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own summaries" ON summaries
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own summaries" ON summaries
    FOR DELETE USING (auth.uid() = user_id);

-- Summary key points policies (through summary ownership)
CREATE POLICY "Users can view own summary key points" ON summary_key_points
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM summaries s WHERE s.id = summary_key_points.summary_id AND s.user_id = auth.uid())
    );
CREATE POLICY "Users can insert own summary key points" ON summary_key_points
    FOR INSERT WITH CHECK (
        EXISTS (SELECT 1 FROM summaries s WHERE s.id = summary_key_points.summary_id AND s.user_id = auth.uid())
    );
CREATE POLICY "Users can delete own summary key points" ON summary_key_points
    FOR DELETE USING (
        EXISTS (SELECT 1 FROM summaries s WHERE s.id = summary_key_points.summary_id AND s.user_id = auth.uid())
    );

-- Video tasks table (video note generation tasks)
CREATE TABLE IF NOT EXISTS video_tasks (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    url TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    thumbnail TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    progress REAL DEFAULT 0,
    message TEXT DEFAULT '',
    markdown TEXT DEFAULT '',
    transcript_json TEXT DEFAULT '',
    style TEXT DEFAULT 'detailed',
    model TEXT DEFAULT '',
    formats JSONB DEFAULT '[]',
    quality TEXT DEFAULT 'medium',
    video_quality TEXT DEFAULT '720',
    extras TEXT DEFAULT '',
    video_understanding BOOLEAN DEFAULT FALSE,
    video_interval INTEGER DEFAULT 4,
    grid_cols INTEGER DEFAULT 3,
    grid_rows INTEGER DEFAULT 3,
    duration REAL DEFAULT 0,
    max_output_tokens INTEGER DEFAULT 0,
    error TEXT DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Video task versions (multiple note versions per task)
CREATE TABLE IF NOT EXISTS video_task_versions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES video_tasks(id) ON DELETE CASCADE,
    content TEXT NOT NULL DEFAULT '',
    style TEXT DEFAULT '',
    model_name TEXT DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable RLS on video tables
ALTER TABLE video_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE video_task_versions ENABLE ROW LEVEL SECURITY;

-- Video tasks policies
CREATE POLICY "Users can view own video tasks" ON video_tasks
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own video tasks" ON video_tasks
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own video tasks" ON video_tasks
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own video tasks" ON video_tasks
    FOR DELETE USING (auth.uid() = user_id);

-- Video task versions policies (through task ownership)
CREATE POLICY "Users can view own video task versions" ON video_task_versions
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM video_tasks t WHERE t.id = video_task_versions.task_id AND t.user_id = auth.uid())
    );
CREATE POLICY "Users can insert own video task versions" ON video_task_versions
    FOR INSERT WITH CHECK (
        EXISTS (SELECT 1 FROM video_tasks t WHERE t.id = video_task_versions.task_id AND t.user_id = auth.uid())
    );
CREATE POLICY "Users can delete own video task versions" ON video_task_versions
    FOR DELETE USING (
        EXISTS (SELECT 1 FROM video_tasks t WHERE t.id = video_task_versions.task_id AND t.user_id = auth.uid())
    );

-- Service role policies for server-side operations
CREATE POLICY "Service role full access video_tasks" ON video_tasks
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access video_task_versions" ON video_task_versions
    FOR ALL USING (auth.role() = 'service_role');

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_podcasts_user_id ON podcasts(user_id);
CREATE INDEX IF NOT EXISTS idx_episodes_user_id ON episodes(user_id);
CREATE INDEX IF NOT EXISTS idx_episodes_podcast_id ON episodes(podcast_id);
CREATE INDEX IF NOT EXISTS idx_transcripts_user_id ON transcripts(user_id);
CREATE INDEX IF NOT EXISTS idx_summaries_user_id ON summaries(user_id);
CREATE INDEX IF NOT EXISTS idx_video_tasks_user_id ON video_tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_video_tasks_status ON video_tasks(user_id, status);
CREATE INDEX IF NOT EXISTS idx_video_task_versions_task ON video_task_versions(task_id);

-- Storage bucket for audio files (optional, for future use)
-- Run this in the Supabase Dashboard under Storage:
-- Create bucket named "audio" with public access disabled
