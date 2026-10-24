"""Pydantic schemas for API requests and responses."""
from typing import List, Optional
import time
from pydantic import model_validator, BaseModel


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
    summarized_count: int = 0
    platform: str = "xiaoyuzhou"
    feed_url: str = ""
    episode_preview: Optional[List["EpisodeResponse"]] = None
    resolved_episode_id: Optional[str] = None
    resolved_episode_title: Optional[str] = None
    
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
    quality_status: str = "not_processed"
    source_status: str = "unknown"
    source_message: str = ""

    @model_validator(mode="after")
    def describe_source(self):
        from source_access import source_message
        self.source_message = source_message(self.source_status)
        from api.summary_quality import needs_review
        self.quality_status = "needs_review" if self.has_summary and needs_review(self.duration,self.topics_count,self.key_points_count) else "ready" if self.has_summary else "not_processed"
        return self
    eid: str
    pid: str
    audio_url: str = ""
    status: str = "pending"
    has_transcript: bool = False
    has_summary: bool = False
    topics_count: int = 0
    key_points_count: int = 0
    created_at: str = ""
    
    class Config:
        from_attributes = True


PodcastResponse.model_rebuild()


class LocalAudioUploadResponse(BaseModel):
    podcast: PodcastResponse
    episode: EpisodeResponse


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
    quality_warning: str = ""
    source_status: str = "unknown"
    source_message: str = ""
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
    podcast_title: str = ""
    podcast_cover: str = ""
    created_at: str = ""


# Processing schemas
class ProcessRequest(BaseModel):
    episode_url: Optional[str] = None
    transcribe_only: bool = False
    force: bool = False
    whisper_model: Optional[str] = None
    llm_model: Optional[str] = None


class ResummarizeRequest(BaseModel):
    llm_model: Optional[str] = None


class BatchProcessRequest(BaseModel):
    podcast_url: str
    limit: Optional[int] = None
    skip_existing: bool = True
    transcribe_only: bool = False


class ProcessingStatus(BaseModel):
    job_id: str
    # Ordering survives checkpoints and does not depend on network arrival time.
    revision: int = 0
    source_url: str = ""
    transcribe_only: bool = False
    resummarize: bool = False
    whisper_model: Optional[str] = None
    llm_model: Optional[str] = None
    user_id: Optional[str] = None  # User who owns this job (for isolation)
    # Status values:
    # - pending: Job queued
    # - fetching: Getting episode info
    # - downloading: Downloading audio
    # - transcribing: Transcribing audio
    # - summarizing: Generating summary
    # - completed: All done
    # - failed: Error occurred
    # - cancelled: User cancelled
    # - cancelling: Cancellation in progress
    status: str
    started_at: float = 0
    progress: float = 0
    message: str = ""
    episode_id: Optional[str] = None
    episode_title: Optional[str] = None

    def advance_revision(self):
        # Microsecond epoch values fit in JavaScript's safe integer range. A
        # restart can restore an older checkpoint than a browser last saw, so
        # a counter alone would incorrectly reject the recovery status.
        self.revision = max(self.revision + 1, time.time_ns() // 1000)


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


# Import subscriptions schemas
class ImportSubscriptionsRequest(BaseModel):
    username: str  # Xiaoyuzhou username or user ID


class ImportSubscriptionsResponse(BaseModel):
    total_found: int
    newly_added: int
    already_subscribed: int
    failed: int
    podcasts: List[str]  # Names of imported podcasts
