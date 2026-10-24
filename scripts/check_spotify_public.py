"""Read-only public Spotify/RSS integration probe; never starts transcription."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    url = "https://open.spotify.com/episode/08tccyLPpPurxtPPrezQGZ"
    try:
        from spotify_podcasts_client import resolve_spotify_episode
    except ImportError:
        import requests
        from bs4 import BeautifulSoup
        response = requests.get(url.replace('/episode/', '/embed/episode/'), timeout=20)
        print(json.dumps({"spotify_status": response.status_code}))
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        def inspect(value, path='root'):
            if isinstance(value, dict):
                if any(key in value for key in ('duration', 'durationMs', 'duration_ms', 'subtitle', 'relatedEntityUri')):
                    safe = {key: value[key] for key in ('name', 'title', 'subtitle', 'duration', 'durationMs', 'duration_ms', 'type', 'uri', 'relatedEntityUri', 'releaseDate') if key in value}
                    print(json.dumps({"path": path, "fields": list(value), "metadata": safe}, ensure_ascii=False))
                for key, item in value.items():
                    if key not in ('accessToken', 'audioPreview', 'audio', 'images', 'coverArt'):
                        inspect(item, path + '.' + key)
            elif isinstance(value, list):
                for index, item in enumerate(value[:3]): inspect(item, path + f'[{index}]')
        data = soup.find('script', id='__NEXT_DATA__')
        if data: inspect(json.loads(data.string or data.get_text()))
        return
    result = resolve_spotify_episode(url)
    print(json.dumps({"spotify_public_source": "matched", "podcast": result.podcast.title,
                      "episode": result.episode.title, "duration": result.episode.duration,
                      "has_public_audio": bool(result.episode.audio_url)}, ensure_ascii=False))


if __name__ == '__main__': main()
