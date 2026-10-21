"""Reject incomplete speech recognition before it becomes a saved summary."""
import math


class IncompleteTranscriptError(ValueError):
    pass


def validate_transcript(transcript, expected_duration: float = 0) -> None:
    text = (getattr(transcript, 'text', '') or '').strip()
    duration = float(getattr(transcript, 'duration', 0) or 0)
    expected = float(expected_duration or 0)
    if not text:
        raise IncompleteTranscriptError('Speech recognition returned no text. Please retry transcription.')
    if expected >= 60 and (not math.isfinite(duration) or duration < expected * .85):
        raise IncompleteTranscriptError(
            f'Transcription is incomplete: received {duration:.0f}s for {expected:.0f}s of audio. '
            'The summary was not replaced. Please retry transcription.')
    # A long recording reduced to one short sentence is commonly a Whisper
    # hallucination. Duration alone is insufficient (chunk mergers set duration).
    if max(expected, duration) >= 1800 and len(text) < 100:
        raise IncompleteTranscriptError(
            'Speech recognition returned too little text for this recording. '
            'The summary was not replaced. Please retry transcription.')
