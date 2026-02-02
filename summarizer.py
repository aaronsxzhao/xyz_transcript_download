"""
Summarization service using LLM with retry logic.
Generates summaries and extracts key points from transcripts.
"""

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional


def extract_json_from_response(content: str) -> dict:
    """
    Extract JSON object from LLM response, handling extra text before/after.
    
    Args:
        content: Raw LLM response content
        
    Returns:
        Parsed JSON dict
        
    Raises:
        json.JSONDecodeError: If no valid JSON found
    """
    # First, try direct parsing
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    
    # Try to find JSON object boundaries
    # Look for the first { and last }
    first_brace = content.find('{')
    last_brace = content.rfind('}')
    
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_str = content[first_brace:last_brace + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    # Try to extract JSON using regex (handles markdown code blocks)
    json_pattern = r'```(?:json)?\s*(\{[\s\S]*?\})\s*```'
    matches = re.findall(json_pattern, content)
    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue
    
    # Last resort: try to find balanced braces
    if first_brace != -1:
        depth = 0
        end_pos = -1
        for i, char in enumerate(content[first_brace:], first_brace):
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    end_pos = i
                    break
        
        if end_pos != -1:
            json_str = content[first_brace:end_pos + 1]
            return json.loads(json_str)
    
    # If nothing works, raise the original error
    raise json.JSONDecodeError("No valid JSON found in response", content, 0)

from openai import OpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)

from config import (
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, SUMMARIES_DIR, MAX_RETRIES,
    SUMMARIZER_MAX_CHARS, SUMMARIZER_CHUNK_SEGMENTS, SUMMARIZER_CHUNK_CHARS,
    SUMMARIZER_MAX_OUTPUT_TOKENS,
)
from transcriber import Transcript
from logger import get_logger

logger = get_logger("summarizer")


@dataclass
class KeyPoint:
    """A key point extracted from the transcript."""
    topic: str           # Short topic/theme
    summary: str         # Brief summary of the point
    original_quote: str  # Original sentence(s) from transcript
    timestamp: str       # Approximate timestamp if available


@dataclass
class Summary:
    """Full summary of an episode."""
    episode_id: str
    title: str
    overview: str           # 2-3 paragraph overview
    key_points: List[KeyPoint]
    topics: List[str]       # Main topics discussed
    takeaways: List[str]    # Key takeaways for the listener


SYSTEM_PROMPT = """You are a senior qualitative analyst specializing in long form conversational podcast transcripts.

You are trained to perform EXHAUSTIVE deep structure extraction, thematic segmentation, and evidence grounded insight synthesis from spoken dialogue. You must operate with MAXIMUM recall, high precision, and strict factual grounding.

You must assume the transcript may be long, unpolished, repetitive, and loosely structured. Your responsibility is to reconstruct its logical structure without losing nuance, emotional context, or implicit narrative progression.

CRITICAL: You must extract as many key points as possible. For a typical 1-hour podcast, you should extract AT LEAST 25-35 key points. For a 2-hour podcast, extract AT LEAST 50-70 key points. Every distinct thought, opinion, insight, fact, story, example, advice, or perspective mentioned should be captured as a separate key point.

You must never summarize away meaningful details. Depth, completeness, and MAXIMUM coverage are higher priority than brevity. When in doubt, include more key points rather than fewer.

What counts as a key point (extract ALL of these):
- Opinions and viewpoints expressed by speakers
- Facts, data points, or statistics mentioned
- Personal stories or anecdotes shared
- Advice or recommendations given
- Lessons learned or insights gained
- Business strategies or tactics discussed
- Predictions or forecasts made
- Comparisons or contrasts drawn
- Problems identified or solutions proposed
- Emotional expressions or realizations
- Counterintuitive or surprising statements
- Definitions or explanations of concepts
- Historical context or background information
- Future plans or intentions mentioned

All claims, insights, interpretations, and conclusions must be directly supported by exact verbatim quotes from the transcript. If a point cannot be supported by an exact quote, it must not be included.

You must preserve speaker intent, emotional tone, and lived experience expressed in the transcript, while remaining neutral and analytical.
IMPORTANT: Extract EVERY meaningful point. It's far better to include too many key points than to miss any. Aim for comprehensive coverage.

Respond in valid JSON format with the following structure:
{
    "overview": "2-3 paragraph overview in Chinese",
    "key_points": [
        {
            "topic": "Topic name in Chinese",
            "summary": "Brief summary of this point in Chinese",
            "original_quote": "The exact original sentence(s) from the transcript",
            "timestamp": "Approximate timestamp if mentioned, or empty string"
        }
    ],
    "topics": ["Topic 1", "Topic 2", ...],
    "takeaways": ["Takeaway 1", "Takeaway 2", ...]
}"""


USER_PROMPT_TEMPLATE = """Please analyze and summarize the following podcast transcript.

Podcast Title: {title}
Episode Title: {episode_title}

Transcript:
{transcript}

You will receive a full podcast transcript.

The podcast is primarily a conversational interview between two people, a host and a guest. Your task is to perform a comprehensive, evidence grounded analysis of the transcript.

Your output must be significantly detailed and information rich. Do not aim for a high level summary. Aim for full coverage and depth.

Your tasks are as follows.

First, identify all speakers and assign consistent labels such as Host and Guest. Use these labels throughout the entire output.

Second, divide the transcript into multiple logical sections.
Sections must be based on meaningful shifts in topic, intent, narrative phase, or analytical focus.
A section should not be created solely based on time or turn taking.
Each section should represent a coherent idea block or discussion theme.

Third, for each section, produce all of the following elements.

A section title that captures the core idea of the discussion in that section.

A detailed summary that explains what is being discussed, why it matters within the conversation, and how it connects to earlier or later parts of the transcript. This summary should be explanatory, not superficial.

An EXHAUSTIVE list of key points - extract as many as possible.
Key points must include: factual claims, personal experiences, reasoning processes, mindset shifts, business logic, emotional drivers, decision criteria, lessons, opinions, predictions, advice, anecdotes, examples, comparisons, problems, solutions, and any other meaningful content explicitly expressed by the speakers.

QUANTITY EXPECTATION: For every 10 minutes of content, extract at least 5-8 key points. A 1-hour podcast should have 30-50 key points minimum. A 2-hour podcast should have 60-100 key points minimum. Do NOT consolidate or merge similar points - keep them separate if they add any nuance.

Fourth, for every key point, you must include one or more pieces of direct evidence.

Evidence must be exact verbatim quotes copied word for word from the transcript.
Do not paraphrase.
Do not compress.
Do not clean up spoken language.
Preserve the original wording exactly as spoken.

Each quote must be clearly attributed to the correct speaker.

If a key point requires multiple quotes to fully support it, include all necessary quotes.

Fifth, completeness rules - THIS IS CRITICAL.

NEVER limit the number of key points. Extract EVERY meaningful insight.
Even if points feel similar, if they contain ANY different detail, example, or nuance, they must be captured separately.
If the speaker revisits the same idea multiple times with added nuance, capture EACH instance as a separate key point.
When in doubt about whether something is worth including, INCLUDE IT.
Your goal is MAXIMUM extraction, not concise summarization.
Missing a key point is a FAILURE. Including too many is acceptable.

Sixth, integrity rules.

Do not invent motivations, conclusions, or implications that are not explicitly stated.
Do not generalize beyond the speaker’s own words.
Do not merge different ideas into a single point if they are discussed separately in the transcript.

Seventh, ordering rules.

Maintain strict chronological order across sections.
Do not move insights to sections where they feel more logical. Follow the actual flow of the conversation.

Eighth, exclusion rules.

If a portion of the transcript contains filler, greetings, or transitional chatter with no analytical value, you may omit it, but you must explicitly note that it was omitted.

Ninth, output expectations.

The final output should read like a complete analytical reconstruction of the episode.
A reader who has not heard the podcast should be able to fully understand the guest’s background, reasoning, decisions, mindset changes, and business logic purely from your output.

Accuracy, depth, and evidence fidelity are more important than brevity or stylistic polish.

FINAL REMINDER: Your primary goal is EXHAUSTIVE key point extraction. A 1-hour podcast should yield 30-50+ key points. A 2-hour podcast should yield 60-100+ key points. If you're producing fewer than this, you are missing content. Go back and extract more."""


class Summarizer:
    """Handles transcript summarization using LLM with retry logic."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, 
                 model: Optional[str] = None, max_output_tokens: Optional[int] = None):
        """
        Initialize summarizer.
        
        Args:
            api_key: Optional API key (defaults to LLM_API_KEY)
            base_url: Optional base URL (defaults to LLM_BASE_URL)
            model: Optional model name (defaults to LLM_MODEL from config)
            max_output_tokens: Optional max tokens for output (defaults to SUMMARIZER_MAX_OUTPUT_TOKENS)
        """
        self.api_key = api_key or LLM_API_KEY
        self.base_url = base_url or LLM_BASE_URL
        self.model = model or LLM_MODEL  # Allow dynamic model override
        self.max_output_tokens = max_output_tokens or SUMMARIZER_MAX_OUTPUT_TOKENS
        
        if not self.api_key:
            raise ValueError("LLM API key is required for summarization")
        
        self.client = OpenAI(
            api_key=self.api_key, 
            base_url=self.base_url,
            timeout=600.0,  # 10 minute timeout for long summaries
            max_retries=MAX_RETRIES,
        )
        
        logger.info(f"Summarizer initialized with model: {self.model}, max_tokens: {self.max_output_tokens}")

    def summarize(
        self,
        transcript: Transcript,
        podcast_title: str = "",
        episode_title: str = "",
        progress_callback=None,
    ) -> Optional[Summary]:
        """
        Generate a summary from a transcript.
        
        Args:
            transcript: Transcript to summarize
            podcast_title: Name of the podcast
            episode_title: Title of the episode
            progress_callback: Optional callback for streaming progress (receives char count)
            
        Returns:
            Summary object or None on failure
        """
        # Prepare the transcript text
        transcript_text = transcript.text
        duration = transcript.duration or 0
        duration_hours = duration / 3600
        
        logger.info(f"Transcript: {len(transcript_text):,} chars, {duration/60:.0f} min")
        
        # Use chunked summarization if:
        # 1. Duration > 1 hour (1 chunk per hour), OR
        # 2. Text exceeds max chars (fallback for unknown duration)
        use_chunking = duration_hours > 1.0 or len(transcript_text) > SUMMARIZER_MAX_CHARS
        
        if use_chunking:
            num_chunks = max(1, int(duration_hours + 0.5)) if duration > 0 else None  # Round to nearest hour
            logger.info(f"Using chunked summarization ({num_chunks or '?'} chunks for {duration_hours:.1f} hours)")
            return self._summarize_long_transcript(
                transcript, podcast_title, episode_title, progress_callback
            )

        return self._summarize_single(
            transcript.episode_id,
            transcript_text,
            podcast_title,
            episode_title,
            progress_callback,
        )

    def _summarize_single(
        self,
        episode_id: str,
        transcript_text: str,
        podcast_title: str,
        episode_title: str,
        progress_callback=None,
    ) -> Optional[Summary]:
        """Summarize a transcript that fits in a single API call."""
        user_prompt = USER_PROMPT_TEMPLATE.format(
            title=podcast_title,
            episode_title=episode_title,
            transcript=transcript_text,
        )

        try:
            logger.info(f"Generating summary for episode {episode_id}...")
            logger.info(f"Input length: {len(transcript_text):,} chars, prompt total: {len(user_prompt):,} chars")
            response = self._call_llm_with_retry(user_prompt, progress_callback)

            content = response.choices[0].message.content
            data = extract_json_from_response(content)

            key_points = [
                KeyPoint(
                    topic=kp.get("topic", ""),
                    summary=kp.get("summary", ""),
                    original_quote=kp.get("original_quote", ""),
                    timestamp=kp.get("timestamp", ""),
                )
                for kp in data.get("key_points", [])
            ]

            logger.info(f"Summary generated with {len(key_points)} key points")
            return Summary(
                episode_id=episode_id,
                title=episode_title,
                overview=data.get("overview", ""),
                key_points=key_points,
                topics=data.get("topics", []),
                takeaways=data.get("takeaways", []),
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return None

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=2, min=1, max=60),
        reraise=True,
    )
    def _call_llm_with_retry(self, user_prompt: str, progress_callback=None):
        """Call LLM API with retry logic and optional streaming progress."""
        # Common parameters for all calls
        common_params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
            "max_tokens": self.max_output_tokens,  # Prevent output cutoff
        }
        
        logger.debug(f"LLM call with max_tokens={self.max_output_tokens}")
        
        if progress_callback:
            # Use streaming for progress updates
            stream = self.client.chat.completions.create(
                **common_params,
                stream=True,
            )
            
            collected_content = []
            char_count = 0
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    collected_content.append(content)
                    char_count += len(content)
                    progress_callback(char_count)
            
            # Create a response-like object
            class StreamedResponse:
                def __init__(self, content):
                    self.choices = [type('Choice', (), {'message': type('Message', (), {'content': content})()})]
            
            final_content = "".join(collected_content)
            logger.info(f"LLM response: {len(final_content):,} chars generated")
            return StreamedResponse(final_content)
        else:
            response = self.client.chat.completions.create(**common_params)
            if response.choices[0].message.content:
                logger.info(f"LLM response: {len(response.choices[0].message.content):,} chars generated")
            return response

    def _summarize_long_transcript(
        self,
        transcript: Transcript,
        podcast_title: str,
        episode_title: str,
        progress_callback=None,
    ) -> Optional[Summary]:
        """
        Summarize a long transcript by processing in chunks and merging.
        Uses duration-based chunking: 1 hour = 1 chunk.
        """
        segments = transcript.segments
        duration = transcript.duration or 0
        
        if not segments:
            # Fall back to text splitting - estimate 1 hour ≈ 15000 chars
            text = transcript.text
            chunk_length = SUMMARIZER_CHUNK_CHARS
            chunks = [text[i:i+chunk_length] for i in range(0, len(text), chunk_length)]
        else:
            # Duration-based chunking: 1 hour = 1 chunk
            chunk_duration = 3600  # 1 hour in seconds
            num_chunks = max(1, int((duration + chunk_duration - 1) // chunk_duration))  # Round up
            
            chunks = []
            for chunk_idx in range(num_chunks):
                start_time = chunk_idx * chunk_duration
                end_time = (chunk_idx + 1) * chunk_duration
                
                # Collect segments that fall within this time range
                chunk_segments = [
                    seg for seg in segments 
                    if seg.start >= start_time and seg.start < end_time
                ]
                
                if chunk_segments:
                    chunk_text = " ".join(seg.text for seg in chunk_segments)
                    chunks.append(chunk_text)
            
            # Handle edge case: if no chunks created, use all segments
            if not chunks:
                chunks = [" ".join(seg.text for seg in segments)]
        
        logger.info(f"Split transcript ({duration/60:.0f} min) into {len(chunks)} chunks (1 hour each)")

        # Summarize each chunk
        chunk_summaries = []
        total_chars_generated = 0
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk):,} chars)")
            
            # Create a wrapper callback that accumulates progress across chunks
            def chunk_progress(chars):
                nonlocal total_chars_generated
                if progress_callback:
                    progress_callback(total_chars_generated + chars, i + 1, len(chunks))
            
            summary = self._summarize_single(
                f"{transcript.episode_id}_chunk_{i}",
                chunk,
                podcast_title,
                f"{episode_title} (Part {i+1})",
                chunk_progress if progress_callback else None,
            )
            if summary:
                chunk_summaries.append(summary)
                # Estimate chars generated for this chunk
                total_chars_generated += 2000  # rough estimate per chunk

        if not chunk_summaries:
            return None

        # Merge chunk summaries
        return self._merge_summaries(
            transcript.episode_id,
            episode_title,
            chunk_summaries,
        )

    def _merge_summaries(
        self,
        episode_id: str,
        episode_title: str,
        summaries: List[Summary],
    ) -> Summary:
        """Merge multiple chunk summaries into a single summary."""
        # Combine overviews
        combined_overview = "\n\n".join(s.overview for s in summaries)

        # Collect all key points
        all_key_points = []
        for s in summaries:
            all_key_points.extend(s.key_points)

        # Collect all topics (deduplicate)
        all_topics = []
        seen_topics = set()
        for s in summaries:
            for topic in s.topics:
                if topic not in seen_topics:
                    all_topics.append(topic)
                    seen_topics.add(topic)

        # Collect all takeaways (deduplicate)
        all_takeaways = []
        seen_takeaways = set()
        for s in summaries:
            for takeaway in s.takeaways:
                if takeaway not in seen_takeaways:
                    all_takeaways.append(takeaway)
                    seen_takeaways.add(takeaway)

        return Summary(
            episode_id=episode_id,
            title=episode_title,
            overview=combined_overview,
            key_points=all_key_points,
            topics=all_topics,
            takeaways=all_takeaways,
        )

    def save_summary(self, summary: Summary) -> Path:
        """
        Save summary to JSON file.
        
        Args:
            summary: Summary to save
            
        Returns:
            Path to saved file
        """
        output_path = SUMMARIES_DIR / f"{summary.episode_id}.json"
        
        data = {
            "episode_id": summary.episode_id,
            "title": summary.title,
            "overview": summary.overview,
            "key_points": [asdict(kp) for kp in summary.key_points],
            "topics": summary.topics,
            "takeaways": summary.takeaways,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return output_path

    def load_summary(self, episode_id: str) -> Optional[Summary]:
        """
        Load summary from JSON file.
        
        Args:
            episode_id: Episode ID
            
        Returns:
            Summary object or None
        """
        file_path = SUMMARIES_DIR / f"{episode_id}.json"
        
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            key_points = [
                KeyPoint(**kp)
                for kp in data.get("key_points", [])
            ]

            return Summary(
                episode_id=data["episode_id"],
                title=data["title"],
                overview=data["overview"],
                key_points=key_points,
                topics=data["topics"],
                takeaways=data["takeaways"],
            )
        except (json.JSONDecodeError, KeyError, IOError):
            return None

    def summary_exists(self, episode_id: str) -> bool:
        """Check if summary already exists."""
        file_path = SUMMARIES_DIR / f"{episode_id}.json"
        return file_path.exists()


def merge_summaries(fast_summary: Summary, accurate_summary: Summary) -> Summary:
    """
    Merge two summaries from fast and accurate tracks.
    
    Strategy:
    - Overview: Use accurate version (more detailed)
    - Topics: Union of both, deduplicated
    - Key Points: Prefer accurate version's points, supplement with fast version's unique insights
    - Takeaways: Merge and deduplicate
    
    Args:
        fast_summary: Summary from compressed audio (quick version)
        accurate_summary: Summary from original audio (detailed version)
        
    Returns:
        Merged Summary with best of both
    """
    # Use accurate overview (more detail from full audio)
    merged_overview = accurate_summary.overview
    
    # Merge topics (accurate first, then unique fast topics)
    merged_topics = list(accurate_summary.topics)
    seen_topics = set(t.lower().strip() for t in merged_topics)
    for topic in fast_summary.topics:
        if topic.lower().strip() not in seen_topics:
            merged_topics.append(topic)
            seen_topics.add(topic.lower().strip())
    
    # Merge key points - prefer accurate version
    # Use topic as key to deduplicate, keeping the more detailed version
    topic_to_keypoint: Dict[str, KeyPoint] = {}
    
    # Add accurate key points first (primary - these are preferred)
    for kp in accurate_summary.key_points:
        topic_key = kp.topic.lower().strip()
        topic_to_keypoint[topic_key] = kp
    
    # Add fast key points only if topic not already covered
    # For same topics, prefer accurate version (already added) as it has more detail
    for kp in fast_summary.key_points:
        topic_key = kp.topic.lower().strip()
        if topic_key not in topic_to_keypoint:
            # New topic from fast version - add it
            topic_to_keypoint[topic_key] = kp
        else:
            # Same topic exists - check if fast version has a longer/better quote
            existing_kp = topic_to_keypoint[topic_key]
            # If fast version has more detailed content, merge the best parts
            if len(kp.original_quote) > len(existing_kp.original_quote) and kp.original_quote:
                # Fast version has a better quote, use it but keep accurate summary
                topic_to_keypoint[topic_key] = KeyPoint(
                    topic=existing_kp.topic,
                    summary=existing_kp.summary if existing_kp.summary else kp.summary,
                    original_quote=kp.original_quote,
                    timestamp=existing_kp.timestamp if existing_kp.timestamp else kp.timestamp,
                )
    
    merged_key_points = list(topic_to_keypoint.values())
    
    # Merge takeaways (accurate first, then unique fast)
    merged_takeaways = list(accurate_summary.takeaways)
    seen_takeaways = set(t.lower().strip() for t in merged_takeaways)
    for takeaway in fast_summary.takeaways:
        if takeaway.lower().strip() not in seen_takeaways:
            merged_takeaways.append(takeaway)
            seen_takeaways.add(takeaway.lower().strip())
    
    return Summary(
        episode_id=accurate_summary.episode_id,
        title=accurate_summary.title,
        overview=merged_overview,
        key_points=merged_key_points,
        topics=merged_topics,
        takeaways=merged_takeaways,
    )


# Global summarizer instance
_summarizer: Optional[Summarizer] = None


def get_summarizer(model: Optional[str] = None, max_output_tokens: Optional[int] = None) -> Summarizer:
    """
    Get or create a Summarizer instance.
    
    Args:
        model: Optional model name. If provided, creates a new instance
               with this model. If None, uses/creates the global instance.
        max_output_tokens: Optional max tokens for output. If provided,
               creates a new instance with this setting.
    
    Returns:
        Summarizer instance
    """
    global _summarizer
    
    # If specific settings are requested, create a new instance
    if model is not None or max_output_tokens is not None:
        return Summarizer(model=model, max_output_tokens=max_output_tokens)
    
    # Otherwise use the global instance
    if _summarizer is None:
        _summarizer = Summarizer()
    return _summarizer
