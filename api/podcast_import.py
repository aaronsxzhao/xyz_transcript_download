"""Save resolved public RSS sources through the existing owned database interface."""
from spotify_podcasts_client import SpotifyResolution


def save_public_episode(db, resolution: SpotifyResolution):
    source, episode = resolution.podcast, resolution.episode
    podcast = db.get_podcast(source.pid)
    if not podcast:
        db.add_podcast(source.pid, source.title, source.author, source.description, source.cover_url,
                       platform='apple', feed_url=source.feed_url)
        podcast = db.get_podcast(source.pid)
    if not podcast:
        raise RuntimeError('Could not save the public podcast subscription. Please retry.')
    if not db.get_episode(episode.eid):
        db.add_episode(eid=episode.eid, pid=source.pid, podcast_id=podcast.id, title=episode.title,
                       description=episode.description, duration=episode.duration, pub_date=episode.pub_date, audio_url=episode.audio_url)
    if not db.get_episode(episode.eid):
        raise RuntimeError('Could not save the matched episode. Please retry.')
    return podcast
