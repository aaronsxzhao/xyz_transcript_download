"""Read-only channel groups; missing source attribution is never written back."""
UNKNOWN_CHANNEL_SENTINEL = "__unknown__"


def aggregate_channels(rows):
    groups = {}
    for row in rows:
        channel = row.get('channel') or UNKNOWN_CHANNEL_SENTINEL
        key = (channel, row.get('platform') or '')
        unknown = channel == UNKNOWN_CHANNEL_SENTINEL
        entry = groups.setdefault(key, dict(channel=channel, platform=key[1],
            channel_url='', channel_avatar='', thumbnail='', total=0, done=0, last_updated=''))
        entry['total'] += 1
        entry['done'] += row.get('status') == 'success'
        entry['last_updated'] = max(entry['last_updated'], row.get('updated_at') or '')
        for field in ('thumbnail', 'channel_url', 'channel_avatar'):
            if not entry[field] and (field == 'thumbnail' or not unknown):
                entry[field] = row.get(field) or ''
    return sorted(groups.values(), key=lambda row: row['last_updated'], reverse=True)
