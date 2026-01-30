"""
Mock summarizer for testing.
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class MockKeyPoint:
    """Mock key point."""
    topic: str
    summary: str
    original_quote: str
    timestamp: str


@dataclass
class MockSummary:
    """Mock summary result."""
    episode_id: str
    title: str
    overview: str
    key_points: List[MockKeyPoint]
    topics: List[str]
    takeaways: List[str]


class MockSummarizer:
    """Mock summarizer for testing without actual LLM."""
    
    def __init__(self):
        self.summaries = {}
        self.call_count = 0
        self.should_fail = False
    
    def summarize(self, transcript, episode_title: str = None) -> Optional[MockSummary]:
        """Mock summarization."""
        self.call_count += 1
        
        if self.should_fail:
            return None
        
        episode_id = transcript.episode_id if hasattr(transcript, 'episode_id') else "unknown"
        
        # Return cached or generate mock summary
        if episode_id in self.summaries:
            return self.summaries[episode_id]
        
        # Generate default mock summary
        key_points = [
            MockKeyPoint(
                topic="主要观点",
                summary="这是测试生成的主要观点摘要",
                original_quote="这是测试转录的第一段",
                timestamp="00:00:00",
            ),
            MockKeyPoint(
                topic="次要观点",
                summary="这是测试生成的次要观点摘要",
                original_quote="这是测试转录的第二段",
                timestamp="00:00:05",
            ),
        ]
        
        return MockSummary(
            episode_id=episode_id,
            title=episode_title or "Test Episode",
            overview="这是测试生成的节目概述。本期节目讨论了多个重要话题。",
            key_points=key_points,
            topics=["话题1", "话题2", "话题3"],
            takeaways=["收获1", "收获2"],
        )
    
    def set_summary(self, episode_id: str, summary: MockSummary):
        """Set a specific summary for testing."""
        self.summaries[episode_id] = summary
    
    def set_should_fail(self, should_fail: bool):
        """Configure whether summarization should fail."""
        self.should_fail = should_fail
    
    def reset(self):
        """Reset mock state."""
        self.summaries = {}
        self.call_count = 0
        self.should_fail = False
