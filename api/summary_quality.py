"""Shared lightweight readiness rule; never fetch a transcript just to list notes."""
EMPTY_LONG_MESSAGE = 'This long episode has no topics or key points. Its summary needs review before it can be treated as ready to read.'


def needs_review(duration, topics, key_points):
    return (duration or 0) >= 1800 and not topics and not key_points
