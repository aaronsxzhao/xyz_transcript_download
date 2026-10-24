"""Read-only public Spotify/RSS integration probe; never starts transcription."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spotify_podcasts_client import resolve_spotify_episode


def main():
    url = "https://open.spotify.com/episode/08tccyLPpPurxtPPrezQGZ"
    result = resolve_spotify_episode(url)
    print(json.dumps({"spotify_public_source": "matched", "podcast": result.podcast.title,
                      "episode": result.episode.title, "duration": result.episode.duration,
                      "has_public_audio": bool(result.episode.audio_url)}, ensure_ascii=False))


if __name__ == '__main__': main()
