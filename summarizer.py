"""
Summarization service using LLM with retry logic.
Generates summaries and extracts key points from transcripts.
"""

import json
import re
from dataclasses import dataclass, asdict, replace
from pathlib import Path
from typing import List, Optional


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
    from summary_format import extract_model_json
    return extract_model_json(content)

from openai import OpenAI
from summary_errors import SummaryOutputError, ProcessingCancelledError
from reading_language import chinese_source
from source_coverage import SOURCE_CHUNK_CHARS, split_source, audit_source, spoken_source, quote_timestamp
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_not_exception_type,
)

from config import (
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, SUMMARIES_DIR, MAX_RETRIES,
    SUMMARIZER_MAX_CHARS, SUMMARIZER_CHUNK_SEGMENTS, SUMMARIZER_CHUNK_CHARS,
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
    overview: str           # Labelled core conclusions and episode overview
    key_points: List[KeyPoint]
    topics: List[str]       # Main topics discussed
    takeaways: List[str]    # Key takeaways for the listener


from podcast_prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE, MERGE_PROMPT, MERGE_SYSTEM_PROMPT, CHUNK_INSTRUCTION


class Summarizer:
    """Handles transcript summarization using LLM with retry logic."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, 
                 model: Optional[str] = None, custom_endpoint: bool = False):
        """
        Initialize summarizer.
        
        Args:
            api_key: Optional API key (defaults to LLM_API_KEY)
            base_url: Optional base URL (defaults to LLM_BASE_URL)
            model: Optional model name (defaults to LLM_MODEL from config)
        """
        self.api_key = api_key or LLM_API_KEY
        self.base_url = base_url or LLM_BASE_URL
        self.model = model or LLM_MODEL
        self.custom_endpoint = custom_endpoint
        self._groq = self.base_url.rstrip('/') == "https://api.groq.com/openai/v1"
        # Context capacity is not an editorial coverage budget. A long interview
        # fitting in one request still loses details when reduced in one pass.
        self.chunk_chars = min(SOURCE_CHUNK_CHARS, SUMMARIZER_CHUNK_CHARS)
        # Outline synthesis never rewrites point bodies and has its own context
        # budget; a small extraction unit must not prevent a full-episode outline.
        self.outline_chars = 30000 if self._groq else SUMMARIZER_CHUNK_CHARS
        
        if not self.api_key:
            raise ValueError("LLM API key is required for summarization")
        
        from api.custom_models import custom_http_client
        self.client = OpenAI(
            api_key=self.api_key, 
            base_url=self.base_url,
            timeout=600.0,
            max_retries=MAX_RETRIES,
            **({"http_client": custom_http_client()} if custom_endpoint else {}),
        )
        
        logger.info(f"Summarizer initialized with model: {self.model}")

    def summarize(
        self,
        transcript: Transcript,
        podcast_title: str = "",
        episode_title: str = "",
        progress_callback=None,
        existing_topics: Optional[List[str]] = None,
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
        from transcript_quality import validate_transcript
        validate_transcript(transcript)
        # Prepare the transcript text
        transcript_text = self._transcript_text(transcript)
        duration = transcript.duration or 0
        duration_hours = duration / 3600
        
        logger.info(f"Transcript: {len(transcript_text):,} chars, {duration/60:.0f} min")
        
        use_chunking = len(transcript_text) > self.chunk_chars
        last_chars = 0
        original_progress = progress_callback
        if original_progress:
            def progress_callback(chars, *args):
                nonlocal last_chars
                last_chars = max(last_chars, chars)
                original_progress(chars, *args)
        
        if use_chunking:
            logger.info(f"Using bounded source extraction for {duration_hours:.1f} hours")
            result = self._summarize_long_transcript(
                transcript, podcast_title, episode_title, progress_callback, existing_topics
            )
        else:
            result = self._summarize_single(
                transcript.episode_id, transcript_text, podcast_title, episode_title,
                progress_callback, existing_topics)
        return self._edit_reading(result, (lambda:original_progress(last_chars)) if original_progress else None)

    def _editorial_json(self, system, payload, timeout):
        from reading_editor import call_editor
        return call_editor(self.client, self.model, system, payload, timeout)

    def _edit_reading(self, summary, checkpoint=None):
        from reading_editor import edit_sections, has_unedited_source
        if not summary or len(summary.key_points) < 2 or has_unedited_source(summary.overview):
            return summary
        items = [{'id':f'N{i+1}', 'topic':point.topic, 'text':point.summary,
                  'evidence':point.original_quote} for i,point in enumerate(summary.key_points)]
        lookup = {item['id']:point for item,point in zip(items,summary.key_points)}
        try:
            paragraphs = edit_sections(items, self._editorial_json, checkpoint)
            points = []
            for paragraph in paragraphs:
                evidence = lookup[paragraph['evidence_id']]
                if not evidence.original_quote:
                    evidence = next((lookup[ident] for ident in paragraph['ids'] if lookup[ident].original_quote), evidence)
                points.append(KeyPoint(paragraph['topic'], paragraph['text'], evidence.original_quote, evidence.timestamp))
            return replace(summary, key_points=points, topics=list(dict.fromkeys(point.topic for point in points)))
        except Exception as error:
            from summary_errors import is_cancellation
            if is_cancellation(error):
                raise
            logger.info('Keeping complete podcast notes after optional editing failure: %s', type(error).__name__)
            return summary

    def _summarize_single(
        self,
        episode_id: str,
        transcript_text: str,
        podcast_title: str,
        episode_title: str,
        progress_callback=None,
        existing_topics: Optional[List[str]] = None,
        source_context=None,
    ) -> Optional[Summary]:
        """Summarize a transcript that fits in a single API call."""
        user_prompt = USER_PROMPT_TEMPLATE.format(
            title=podcast_title,
            episode_title=episode_title,
            transcript=transcript_text,
            existing_topics=json.dumps(existing_topics or [], ensure_ascii=False),
            source_context=json.dumps(source_context or {}, ensure_ascii=False),
        )

        try:
            logger.info(f"Generating summary for episode {episode_id}...")
            logger.info(f"Input length: {len(transcript_text):,} chars, prompt total: {len(user_prompt):,} chars")
            if source_context is not None:
                response = self._call_llm_with_retry(user_prompt, progress_callback, system_prompt=SYSTEM_PROMPT + CHUNK_INSTRUCTION)
            else:
                response = self._call_llm_with_retry(user_prompt, progress_callback)

            content = response.choices[0].message.content
            try:
                data = extract_json_from_response(content)
                result = self._parse_summary(data, episode_id, episode_title)
            except json.JSONDecodeError:
                # Preserve readable provider text even when its JSON envelope is broken.
                raw = content.strip('\r\n')
                if not raw.strip():
                    raise SummaryOutputError('empty')
                from summary_errors import delivery_notice
                return Summary(episode_id, episode_title,
                    delivery_notice('', 'format', transcript_text),
                    [KeyPoint('生成正文' if chinese_source(transcript_text) else 'Generated notes', raw, '', '')], ['生成正文' if chinese_source(transcript_text) else 'Generated notes'], [])
            if not result.key_points:
                from summary_errors import delivery_notice
                return replace(result, overview=delivery_notice('', 'format', transcript_text),
                    key_points=[KeyPoint('生成正文' if chinese_source(transcript_text) else 'Generated notes', result.overview, '', '')], topics=['生成正文' if chinese_source(transcript_text) else 'Generated notes'])
            try:
                result = self._audit_summary(result, transcript_text, progress_callback, source_context)
            except Exception as audit_error:
                from summary_errors import delivery_notice, is_cancellation
                if is_cancellation(audit_error):
                    raise
                logger.warning("Delivering draft after audit failure: %s", getattr(audit_error, "audit_feedback", {}).get("issue", type(audit_error).__name__))
                # A failed editorial pass must not discard an available draft.
                # Keep only quotations actually present in this source; leave
                # unverified evidence/timestamps empty instead of guessing.
                compact = lambda value: re.sub(r"\s+", "", value)
                spoken = compact(spoken_source(transcript_text))
                points = []
                for point in result.key_points:
                    quote = point.original_quote if compact(point.original_quote) and compact(point.original_quote) in spoken else ""
                    points.append(replace(point, original_quote=quote, timestamp=quote_timestamp(transcript_text, quote, point.timestamp)))
                result = replace(result, overview=delivery_notice(result.overview, "audit", transcript_text), key_points=points)
            key_points = result.key_points

            logger.info(f"Summary generated with {len(key_points)} key points")
            return result

        except ProcessingCancelledError:
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            raise SummaryOutputError('invalid') from None
        except Exception as e:
            from summary_errors import is_cancellation
            if is_cancellation(e):
                raise
            logger.error(f"Summarization failed: {type(e).__name__ if self.custom_endpoint else e}")
            if self.custom_endpoint:
                from api.custom_models import public_model_error
                raise RuntimeError(public_model_error(e, "summary")) from None
            if self._groq and "cancel" not in type(e).__name__.lower():
                from api.llm_settings import safe_provider_error
                raise RuntimeError(safe_provider_error(e)) from None
            return None

    def _audit_summary(self, summary: Summary, source: str, progress_callback=None, source_context=None) -> Summary:
        """Review extraction against the source before any outline synthesis."""
        fields = {"overview": summary.overview}
        fields.update({f"point:{i+1}": point.summary for i, point in enumerate(summary.key_points)})
        fields.update({f"takeaway:{i+1}": value for i, value in enumerate(summary.takeaways)})

        def call(system, payload):
            response = self._call_llm_with_retry(payload, progress_callback, system_prompt=system)
            return extract_json_from_response(response.choices[0].message.content)

        context = {**(source_context or {}), "chapter_titles": summary.topics}
        review = audit_source(source, fields, call, context, repair=False, best_effort=True)
        updated, additions, citations = review
        evidence_incomplete = False
        compact = lambda value: re.sub(r"\s+", "", value)
        spoken = compact(spoken_source(source))
        points = []
        for i, point in enumerate(summary.key_points):
            field = f"point:{i+1}"
            verified_quote = bool(compact(point.original_quote)) and compact(point.original_quote) in spoken
            # Keep the selected verbatim excerpt when the reviewed claim is
            # unchanged; coverage receipts can span much broader source units.
            quote = (point.original_quote if verified_quote and updated[field] == point.summary
                     else citations.get(field, ""))
            if not compact(quote) or compact(quote) not in spoken:
                # Missing evidence affects this citation, not the other notes.
                quote = ""
                evidence_incomplete = True
            points.append(replace(point, summary=updated[field], original_quote=quote,
                                  timestamp=quote_timestamp(source, quote, point.timestamp)))
        for i, addition in enumerate(additions):
            points.append(KeyPoint(addition["topic"], updated[addition["id"]],
                                   addition["source_quote"], quote_timestamp(source, addition["source_quote"], addition["timestamp"])))
        gaps = getattr(review, 'identified_gaps', {})
        if gaps:
            gap_topic = '核对标出的原文' if chinese_source(source) else 'Source passages flagged by review'
            for passage in gaps.values():
                points.append(KeyPoint(gap_topic, passage, passage, quote_timestamp(source, passage)))
        overview = updated['overview']
        from summary_errors import delivery_notice
        if gaps:
            overview = delivery_notice(overview, 'coverage_gap', source)
        elif not getattr(review, 'complete', True) or evidence_incomplete:
            overview = delivery_notice(overview, 'audit', source)
        if not getattr(review, 'complete', True):
            logger.warning('Podcast review retained valid items; unresolved checks: %s', ','.join(review.issues))
        return replace(summary, overview=overview, key_points=points,
                       topics=list(dict.fromkeys([*summary.topics, *(p.topic for p in points)])),
                       takeaways=[updated[f"takeaway:{i+1}"] for i in range(len(summary.takeaways))])

    @retry(
        retry=retry_if_not_exception_type(ProcessingCancelledError),
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=2, min=1, max=60),
        reraise=True,
    )
    def _call_llm_with_retry(self, user_prompt: str, progress_callback=None, system_prompt: str = SYSTEM_PROMPT):
        """Call LLM API with retry logic and optional streaming progress."""
        # Common parameters for all calls
        common_params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        
        if self._groq:
            common_params.update(max_completion_tokens=32768, reasoning_effort='medium')
        if progress_callback:
            # Usage-only SSE events may have no choices.
            # Use streaming for progress updates
            stream = self.client.chat.completions.create(
                **common_params,
                stream=True,
            )
            
            collected_content = []
            char_count = 0
            finish_reason = None
            try:
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    if choice.delta.content:
                        content = choice.delta.content
                        collected_content.append(content)
                        char_count += len(content)
                        progress_callback(char_count)
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
            finally:
                # Close the provider connection on cancellation and parse/read
                # errors as well as success; cleanup must not mask the cause.
                try:
                    close = getattr(stream, 'close', None)
                    if close:
                        close()
                except Exception:
                    logger.warning('Could not close the summary stream')
            
            final_content = "".join(collected_content)
            if finish_reason and finish_reason != "stop":
                raise SummaryOutputError(finish_reason)
            if not final_content.strip():
                raise SummaryOutputError('empty')
            logger.info(f"LLM response: {len(final_content):,} chars generated")

            class StreamedResponse:
                def __init__(self, content):
                    self.choices = [type('Choice', (), {'message': type('Message', (), {'content': content})()})]
            
            return StreamedResponse(final_content)
        else:
            response = self.client.chat.completions.create(**common_params)
            if not response.choices or not (response.choices[0].message.content or '').strip():
                raise SummaryOutputError('empty')
            finish_reason = response.choices[0].finish_reason
            if finish_reason and finish_reason != "stop":
                raise SummaryOutputError(finish_reason)
            if response.choices[0].message.content:
                logger.info(f"LLM response: {len(response.choices[0].message.content):,} chars generated")
            return response

    def _summarize_long_transcript(
        self,
        transcript: Transcript,
        podcast_title: str,
        episode_title: str,
        progress_callback=None,
        existing_topics: Optional[List[str]] = None,
    ) -> Optional[Summary]:
        """Process bounded source chunks, then synthesize a complete outline."""
        text = self._transcript_text(transcript)
        chunks = split_source(text, self.chunk_chars)
        logger.info(f"Split transcript ({(transcript.duration or 0)/60:.0f} min) into {len(chunks)} bounded chunks")

        # Summarize each chunk
        chunk_summaries = []
        generated = 0
        total_chars_generated = 0
        
        chapter_titles = list(existing_topics or [])
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk):,} chars)")
            
            # Create a wrapper callback that accumulates progress across chunks
            def chunk_progress(chars):
                nonlocal total_chars_generated
                if progress_callback:
                    progress_callback(total_chars_generated + chars, i + 1, len(chunks))
            
            try:
                summary = self._summarize_single(
                    f"{transcript.episode_id}_chunk_{i}",
                    chunk,
                    podcast_title,
                    f"{episode_title} (Part {i+1})",
                    chunk_progress if progress_callback else None,
                    chapter_titles,
                    source_context={"before": chunks[i - 1][-500:] if i else "",
                                    "after": chunks[i + 1][:500] if i + 1 < len(chunks) else ""},
                )
            except Exception as error:
                from summary_errors import is_cancellation
                if is_cancellation(error):
                    raise
                logger.warning("Source chunk %s/%s unavailable: %s", i + 1, len(chunks), type(error).__name__)
                summary = None
            if summary:
                generated += 1
                chunk_summaries.append(summary)
                chapter_titles = list(dict.fromkeys([*chapter_titles, *summary.topics]))
                # Estimate chars generated for this chunk
                total_chars_generated += 2000  # rough estimate per chunk
            else:
                from summary_errors import delivery_notice
                topic = (f"第 {i + 1}/{len(chunks)} 部分：原始转写" if chinese_source(text) else f"Part {i + 1}/{len(chunks)}: Original transcript")
                chunk_summaries.append(Summary(transcript.episode_id, episode_title,
                    delivery_notice(topic, source=text),
                    [KeyPoint(topic, spoken_source(chunk), "", "")], [topic], []))

        if not generated:
            return None

        # Merge chunk summaries
        return self._merge_summaries(
            transcript.episode_id,
            episode_title,
            chunk_summaries,
            (lambda chars: progress_callback(total_chars_generated + chars)) if progress_callback else None,
        )

    @staticmethod
    def _segment_text(segment) -> str:
        seconds = max(0, int(segment.start))
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return f"[{hours:02d}:{minutes:02d}:{seconds:02d}] {segment.text}"

    @classmethod
    def _transcript_text(cls, transcript: Transcript) -> str:
        # Keep any text not represented by segments, rather than dropping it to
        # obtain timestamps. In that case the prompt requires empty timestamps.
        compact = lambda value: re.sub(r"\s+", "", value)
        if transcript.segments and compact("".join(s.text for s in transcript.segments)) == compact(transcript.text):
            # A marker on every tiny ASR segment can double a Chinese prompt.
            # Use genuine source anchors about every 30 seconds instead.
            lines = []
            previous_anchor = -30
            for segment in transcript.segments:
                if segment.start - previous_anchor >= 30:
                    lines.append(cls._segment_text(segment))
                    previous_anchor = segment.start
                else:
                    lines.append(segment.text)
            return "\n".join(lines)
        return transcript.text

    @staticmethod
    def _parse_summary(data, episode_id: str, episode_title: str) -> Summary:
        from summary_format import normalize_summary_fields
        data = normalize_summary_fields(data)
        points = data['key_points']
        topics = data['topics']
        takeaways = data['takeaways']
        # Providers may still emit a point topic missing from the chapter list.
        # Repair the outline without throwing away the point or its source.
        topics = list(dict.fromkeys(t.strip() for t in topics if t.strip()))
        key_points = []
        for point in points:
            topic = point.get('topic', '').strip() or '其他内容'
            if topic not in topics:
                topics.append(topic)
            key_points.append(KeyPoint(topic, point['summary'],
                point.get('original_quote', ''), point.get('timestamp', '')))
        return Summary(episode_id, episode_title, data['overview'], key_points, topics, takeaways)

    def _merge_summaries(
        self, episode_id: str, episode_title: str, summaries: List[Summary], progress_callback=None,
    ) -> Summary:
        from summary_errors import delivery_notice, is_cancellation, strip_delivery_notices, merge_delivery_notices
        try:
            result = self._merge_summaries_verified(episode_id, episode_title, summaries, progress_callback)
        except Exception as error:
            if is_cancellation(error) or not summaries:
                raise
            logger.warning("Delivering source sections after outline merge failure: %s", type(error).__name__)
            result = Summary(episode_id, episode_title,
                delivery_notice("\n\n".join(strip_delivery_notices(summary.overview) for summary in summaries), "merge", "\n".join(point.summary for summary in summaries for point in summary.key_points)),
                [point for summary in summaries for point in summary.key_points],
                list(dict.fromkeys(topic for summary in summaries for topic in summary.topics)),
                [item for summary in summaries for item in summary.takeaways])
        result = replace(result, overview=merge_delivery_notices(result.overview, [result.overview, *[summary.overview for summary in summaries]]))
        return result

    def _merge_summaries_verified(
        self,
        episode_id: str,
        episode_title: str,
        summaries: List[Summary],
        progress_callback=None,
    ) -> Summary:
        """Synthesize an outline; retain every detailed point and its evidence.

        The model only writes the introduction/implications.
        It cannot accidentally remove examples by rewriting all detailed notes.
        """
        if not summaries:
            raise SummaryOutputError('invalid')
        if len(summaries) == 1:
            return replace(summaries[0], episode_id=episode_id, title=episode_title)

        outlines = []
        topics = []
        for summary in summaries:
            chapter_names = list(dict.fromkeys(summary.topics + [p.topic for p in summary.key_points]))
            topics.extend(topic for topic in chapter_names if topic not in topics)
            outlines.append({'overview': summary.overview, 'chapters': chapter_names,
                             'takeaways': summary.takeaways})
        payload = json.dumps(outlines, ensure_ascii=False)
        if len(payload) > self.outline_chars:
            if len(summaries) == 2:
                # Never submit an over-context request or silently save half an
                # episode when a provider ignores the concise overview contract.
                raise SummaryOutputError('length')
            midpoint = len(summaries) // 2
            halves = [self._merge_summaries(episode_id, episode_title, part, progress_callback)
                      for part in (summaries[:midpoint], summaries[midpoint:])]
            return self._merge_summaries(episode_id, episode_title, halves, progress_callback)

        response = self._call_llm_with_retry(MERGE_PROMPT.format(
            episode_title=episode_title, outlines=payload), progress_callback,
            system_prompt=MERGE_SYSTEM_PROMPT)
        try:
            data = extract_json_from_response(response.choices[0].message.content)
        except (json.JSONDecodeError, TypeError):
            raise SummaryOutputError('invalid') from None
        if not isinstance(data, dict):
            raise SummaryOutputError('invalid')
        # No generated ID map controls whether detailed source notes survive.
        # Keep original titles and chronological point order within each chapter.
        points = [point for topic in topics for summary in summaries
                  for point in summary.key_points if point.topic == topic]
        return self._parse_summary({
            'overview': data.get('overview'), 'topics': topics,
            'key_points': [asdict(p) for p in points],
            'takeaways': data.get('takeaways'),
        }, episode_id, episode_title)

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
    
    merged_key_points = list(accurate_summary.key_points)
    identity = lambda p: (re.sub(r"\s+", "", p.summary).casefold(), p.original_quote.strip())
    seen_points = {identity(p) for p in merged_key_points}
    for point in fast_summary.key_points:
        point_id = identity(point)
        if point_id not in seen_points:
            merged_key_points.append(point)
            seen_points.add(point_id)
    for point in merged_key_points:
        if point.topic not in merged_topics:
            merged_topics.append(point.topic)

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


def get_summarizer(model: Optional[str] = None, *, api_key: str = "", base_url: str = "", custom_endpoint: bool = False) -> Summarizer:
    """
    Get or create a Summarizer instance.
    
    Args:
        model: Optional model name. If provided, creates a new instance
               with this model. If None, uses/creates the global instance.
    
    Returns:
        Summarizer instance
    """
    global _summarizer
    
    if model is not None or api_key or base_url:
        return Summarizer(model=model, api_key=api_key, base_url=base_url, custom_endpoint=custom_endpoint)
    
    if _summarizer is None:
        _summarizer = Summarizer()
    return _summarizer
