"""Small progress messages; reading content has its own authenticated endpoints."""
VIDEO_PROGRESS_FIELDS = frozenset({
    'id', 'url', 'platform', 'title', 'thumbnail', 'status', 'progress',
    'message', 'error', 'channel', 'channel_url', 'channel_avatar',
    'duration', 'published_at', 'created_at', 'updated_at', 'started_at',
})


def video_progress_payload(task):
    return {key: value for key, value in task.items() if key in VIDEO_PROGRESS_FIELDS}
