"""Pydantic schemas for API requests and responses."""
from typing import List, Optional
from pydantic import BaseModel


# Podcast schemas
class PodcastBase(BaseModel):
    title: str
    author: str = ""
    description: str = ""
    cover_url: str = ""


class PodcastCreate(BaseModel):
    url: str


class PodcastResponse(PodcastBase):
    pid: str
    episode_count: int = 0
    
    class Config:
        from_attributes = True


# Episode schemas
class EpisodeBase(BaseModel):
    title: str
    description: str = ""
    duration: int = 0
    pub_date: str = ""
    cover_url: str = ""


class EpisodeResponse(EpisodeBase):
    eid: str
    pid: str
    audio_url: str = ""
    status: str = "pending"
    has_transcript: bool = False
    has_summary: bool = False
    
    class Config:
        from_attributes = True


# Transcript schemas
class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptResponse(BaseModel):
    episode_id: str
    language: str = "zh"
    duration: float = 0
    text: str
    segments: List[TranscriptSegment] = []


# Summary schemas
class KeyPoint(BaseModel):
    topic: str
    summary: str
    original_quote: str = ""
    timestamp: str = ""


class SummaryResponse(BaseModel):
    episode_id: str
    title: str
    overview: str
    key_points: List[KeyPoint] = []
    topics: List[str] = []
    takeaways: List[str] = []


class SummaryListItem(BaseModel):
    episode_id: str
    title: str
    topics_count: int
    key_points_count: int


# Processing schemas
class ProcessRequest(BaseModel):
    episode_url: Optional[str] = None
    transcribe_only: bool = False
    force: bool = False


class BatchProcessRequest(BaseModel):
    podcast_url: str
    limit: Optional[int] = None
    skip_existing: bool = True
    transcribe_only: bool = False


class ProcessingStatus(BaseModel):
    job_id: str
    status: str  # pending, downloading, transcribing, summarizing, completed, failed
    progress: float = 0
    message: str = ""
    episode_id: Optional[str] = None
    episode_title: Optional[str] = None


# Stats schemas
class StatsResponse(BaseModel):
    total_podcasts: int
    total_episodes: int
    total_transcripts: int
    total_summaries: int
    processing_queue: int = 0


# Settings schemas
class SettingsResponse(BaseModel):
    whisper_mode: str
    whisper_model: str
    whisper_backend: str
    whisper_device: str
    llm_model: str
    check_interval: int


class SettingsUpdate(BaseModel):
    whisper_model: Optional[str] = None
    whisper_backend: Optional[str] = None
    whisper_device: Optional[str] = None
    llm_model: Optional[str] = None
    check_interval: Optional[int] = None
