"""
Mock transcriber for testing.
"""
from dataclasses import dataclass
from typing import List, Optional, Callable
from pathlib import Path


@dataclass
class MockTranscriptSegment:
    """Mock transcript segment."""
    start: float
    end: float
    text: str


@dataclass
class MockTranscript:
    """Mock transcript result."""
    episode_id: str
    language: str
    duration: float
    text: str
    segments: List[MockTranscriptSegment]


class MockTranscriber:
    """Mock transcriber for testing without actual Whisper."""
    
    def __init__(self):
        self.transcriptions = {}
        self.call_count = 0
        self.should_fail = False
        self.delay_seconds = 0
    
    def transcribe(
        self,
        audio_path: Path,
        episode_id: str,
        language: str = "zh",
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> Optional[MockTranscript]:
        """Mock transcription."""
        self.call_count += 1
        
        if self.should_fail:
            return None
        
        # Simulate progress
        if progress_callback:
            for i in range(10):
                progress_callback((i + 1) / 10)
        
        # Return cached or generate mock transcript
        if episode_id in self.transcriptions:
            return self.transcriptions[episode_id]
        
        # Generate default mock transcript
        segments = [
            MockTranscriptSegment(start=0.0, end=5.0, text="这是测试转录的第一段。"),
            MockTranscriptSegment(start=5.0, end=10.0, text="这是测试转录的第二段。"),
            MockTranscriptSegment(start=10.0, end=15.0, text="这是测试转录的第三段。"),
        ]
        
        return MockTranscript(
            episode_id=episode_id,
            language=language,
            duration=15.0,
            text=" ".join(s.text for s in segments),
            segments=segments,
        )
    
    def set_transcript(self, episode_id: str, transcript: MockTranscript):
        """Set a specific transcript for testing."""
        self.transcriptions[episode_id] = transcript
    
    def set_should_fail(self, should_fail: bool):
        """Configure whether transcription should fail."""
        self.should_fail = should_fail
    
    def reset(self):
        """Reset mock state."""
        self.transcriptions = {}
        self.call_count = 0
        self.should_fail = False
