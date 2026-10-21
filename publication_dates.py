"""Source publication dates, never extraction or import timestamps."""
from datetime import date, datetime, timezone


def publication_date(info: dict) -> str:
    for key in ('release_date', 'upload_date'):
        value = info.get(key)
        if not isinstance(value, str):
            continue
        try:
            if len(value) == 8 and value.isdigit():
                return datetime.strptime(value, '%Y%m%d').date().isoformat()
            return date.fromisoformat(value[:10]).isoformat()
        except ValueError:
            continue
    for key in ('release_timestamp', 'timestamp'):
        value = info.get(key)
        if isinstance(value, bool) or not value:
            continue
        try:
            stamp = float(value)
            if stamp > 0:
                return datetime.fromtimestamp(stamp, tz=timezone.utc).date().isoformat()
        except (ValueError, TypeError, OverflowError, OSError):
            continue
    # yt-dlp's `epoch` is when extraction ran, not when the video was published.
    return ''
