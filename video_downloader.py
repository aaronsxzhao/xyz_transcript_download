"""
Video downloader supporting multiple platforms: Bilibili, YouTube, Douyin, Kuaishou, and local files.
Uses yt-dlp for Bilibili/YouTube and custom HTTP for Douyin/Kuaishou.
"""

import json
import os
import re
import shutil
import subprocess
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from config import DATA_DIR
from logger import get_logger

logger = get_logger("video_downloader")

VIDEO_DIR = DATA_DIR / "videos"
UPLOAD_DIR = DATA_DIR / "uploads"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
VIDEO_AUDIO_DIR = DATA_DIR / "video_audio"
COVER_DIR = DATA_DIR / "cover"

for d in [VIDEO_DIR, UPLOAD_DIR, SCREENSHOTS_DIR, VIDEO_AUDIO_DIR, COVER_DIR]:
    d.mkdir(parents=True, exist_ok=True)

QUALITY_MAP = {
    "fast": "32",
    "medium": "64",
    "slow": "128",
}

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_PATH = shutil.which("ffmpeg") or "ffmpeg"


@dataclass
class VideoMetadata:
    """Metadata extracted from a video."""
    title: str = ""
    description: str = ""
    thumbnail: str = ""
    duration: float = 0
    platform: str = ""
    url: str = ""
    tags: list = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    def to_dict(self) -> dict:
        return asdict(self)


def detect_platform(url: str) -> str:
    """Auto-detect the video platform from a URL."""
    url_lower = url.lower()
    if "bilibili.com" in url_lower or "b23.tv" in url_lower:
        return "bilibili"
    elif "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    elif "douyin.com" in url_lower or "tiktok.com" in url_lower:
        return "douyin"
    elif "kuaishou.com" in url_lower or "kwai.com" in url_lower:
        return "kuaishou"
    return ""


class BaseDownloader(ABC):
    """Base class for platform-specific downloaders."""

    @abstractmethod
    def get_metadata(self, url: str) -> Optional[VideoMetadata]:
        pass

    @abstractmethod
    def download_audio(self, url: str, task_id: str, quality: str = "medium") -> Optional[Path]:
        pass

    @abstractmethod
    def download_video(self, url: str, task_id: str) -> Optional[Path]:
        pass

    def get_subtitles(self, url: str, task_id: str) -> Optional[list]:
        """Try to extract platform subtitles. Returns list of segments or None."""
        return None


class YtdlpDownloader(BaseDownloader):
    """Base downloader using yt-dlp (for Bilibili and YouTube)."""

    def __init__(self, platform: str, cookies: str = ""):
        self.platform = platform
        self.cookies = cookies

    def _get_cookie_args(self) -> list:
        if not self.cookies:
            return []
        cookie_file = DATA_DIR / f"{self.platform}_cookies.txt"
        cookie_file.write_text(self.cookies, encoding="utf-8")
        return ["--cookies", str(cookie_file)]

    def get_metadata(self, url: str) -> Optional[VideoMetadata]:
        try:
            cmd = ["yt-dlp", "--dump-json", "--no-download"] + self._get_cookie_args() + [url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                logger.error(f"yt-dlp metadata failed: {result.stderr[:500]}")
                return None
            data = json.loads(result.stdout)
            return VideoMetadata(
                title=data.get("title", ""),
                description=data.get("description", ""),
                thumbnail=data.get("thumbnail", ""),
                duration=data.get("duration", 0) or 0,
                platform=self.platform,
                url=url,
                tags=data.get("tags", []) or [],
            )
        except Exception as e:
            logger.error(f"Failed to get metadata: {e}")
            return None

    def download_audio(self, url: str, task_id: str, quality: str = "medium") -> Optional[Path]:
        output_path = VIDEO_AUDIO_DIR / f"{task_id}.mp3"
        if output_path.exists():
            return output_path

        bitrate = QUALITY_MAP.get(quality, "64")
        try:
            cmd = [
                "yt-dlp",
                "-x", "--audio-format", "mp3",
                "--audio-quality", f"{bitrate}K",
                "-o", str(output_path),
                "--no-playlist",
            ] + self._get_cookie_args() + [url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                logger.error(f"yt-dlp audio download failed: {result.stderr[:500]}")
                return None
            if output_path.exists():
                return output_path
            # yt-dlp may add extension
            for f in VIDEO_AUDIO_DIR.glob(f"{task_id}.*"):
                if f.suffix in (".mp3", ".m4a", ".wav", ".ogg"):
                    return f
            return None
        except Exception as e:
            logger.error(f"Audio download failed: {e}")
            return None

    def download_video(self, url: str, task_id: str) -> Optional[Path]:
        output_path = VIDEO_DIR / f"{task_id}.mp4"
        if output_path.exists():
            return output_path

        try:
            cmd = [
                "yt-dlp",
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--merge-output-format", "mp4",
                "-o", str(output_path),
                "--no-playlist",
            ] + self._get_cookie_args() + [url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
            if result.returncode != 0:
                logger.error(f"yt-dlp video download failed: {result.stderr[:500]}")
                return None
            if output_path.exists():
                return output_path
            for f in VIDEO_DIR.glob(f"{task_id}.*"):
                if f.suffix in (".mp4", ".mkv", ".webm"):
                    return f
            return None
        except Exception as e:
            logger.error(f"Video download failed: {e}")
            return None

    def get_subtitles(self, url: str, task_id: str) -> Optional[list]:
        """Try to extract subtitles from the video platform."""
        try:
            sub_dir = DATA_DIR / "subtitles"
            sub_dir.mkdir(exist_ok=True)
            cmd = [
                "yt-dlp",
                "--write-subs", "--write-auto-subs",
                "--sub-langs", "zh-Hans,zh,en",
                "--sub-format", "json3",
                "--skip-download",
                "-o", str(sub_dir / task_id),
            ] + self._get_cookie_args() + [url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return None

            for sub_file in sub_dir.glob(f"{task_id}*.json3"):
                with open(sub_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                events = data.get("events", [])
                segments = []
                for event in events:
                    segs = event.get("segs", [])
                    text = "".join(s.get("utf8", "") for s in segs).strip()
                    if text and text != "\n":
                        start_ms = event.get("tStartMs", 0)
                        dur_ms = event.get("dDurationMs", 0)
                        segments.append({
                            "start": start_ms / 1000.0,
                            "end": (start_ms + dur_ms) / 1000.0,
                            "text": text,
                        })
                if segments:
                    return segments
            return None
        except Exception:
            return None


class BilibiliDownloader(YtdlpDownloader):
    def __init__(self, cookies: str = ""):
        super().__init__("bilibili", cookies)


class YoutubeDownloader(YtdlpDownloader):
    def __init__(self, cookies: str = ""):
        super().__init__("youtube", cookies)


class DouyinDownloader(BaseDownloader):
    """Downloader for Douyin/TikTok videos using HTTP requests."""

    def __init__(self, cookies: str = ""):
        self.cookies = cookies
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                          "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            "Referer": "https://www.douyin.com/",
        }
        if cookies:
            self.headers["Cookie"] = cookies

    def _extract_video_id(self, url: str) -> Optional[str]:
        match = re.search(r'/video/(\d+)', url)
        if match:
            return match.group(1)
        # Handle short URLs by following redirect
        try:
            import requests
            resp = requests.head(url, allow_redirects=True, timeout=10, headers=self.headers)
            match = re.search(r'/video/(\d+)', resp.url)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    def get_metadata(self, url: str) -> Optional[VideoMetadata]:
        try:
            import requests
            video_id = self._extract_video_id(url)
            if not video_id:
                return VideoMetadata(title="Douyin Video", platform="douyin", url=url)

            api_url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}"
            resp = requests.get(api_url, headers=self.headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                detail = data.get("aweme_detail", {})
                return VideoMetadata(
                    title=detail.get("desc", "Douyin Video"),
                    thumbnail=detail.get("video", {}).get("cover", {}).get("url_list", [""])[0],
                    duration=detail.get("video", {}).get("duration", 0) / 1000.0,
                    platform="douyin",
                    url=url,
                )
            return VideoMetadata(title="Douyin Video", platform="douyin", url=url)
        except Exception as e:
            logger.error(f"Douyin metadata error: {e}")
            return VideoMetadata(title="Douyin Video", platform="douyin", url=url)

    def download_audio(self, url: str, task_id: str, quality: str = "medium") -> Optional[Path]:
        video_path = self.download_video(url, task_id)
        if not video_path:
            return None
        return self._extract_audio(video_path, task_id, quality)

    def download_video(self, url: str, task_id: str) -> Optional[Path]:
        output_path = VIDEO_DIR / f"{task_id}.mp4"
        if output_path.exists():
            return output_path
        # Fall back to yt-dlp for Douyin
        try:
            cmd = [
                "yt-dlp",
                "-f", "best",
                "-o", str(output_path),
                "--no-playlist",
                url,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0 and output_path.exists():
                return output_path
        except Exception:
            pass
        return None

    def _extract_audio(self, video_path: Path, task_id: str, quality: str) -> Optional[Path]:
        output_path = VIDEO_AUDIO_DIR / f"{task_id}.mp3"
        if output_path.exists():
            return output_path
        bitrate = QUALITY_MAP.get(quality, "64")
        try:
            cmd = [
                FFMPEG_PATH, "-i", str(video_path),
                "-vn", "-acodec", "libmp3lame", "-ab", f"{bitrate}k",
                "-y", str(output_path),
            ]
            subprocess.run(cmd, capture_output=True, timeout=300, check=True)
            return output_path if output_path.exists() else None
        except Exception as e:
            logger.error(f"Audio extraction failed: {e}")
            return None


class KuaishouDownloader(BaseDownloader):
    """Downloader for Kuaishou videos."""

    def __init__(self, cookies: str = ""):
        self.cookies = cookies
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.kuaishou.com/",
        }
        if cookies:
            self.headers["Cookie"] = cookies

    def get_metadata(self, url: str) -> Optional[VideoMetadata]:
        return VideoMetadata(title="Kuaishou Video", platform="kuaishou", url=url)

    def download_audio(self, url: str, task_id: str, quality: str = "medium") -> Optional[Path]:
        video_path = self.download_video(url, task_id)
        if not video_path:
            return None
        return self._extract_audio(video_path, task_id, quality)

    def download_video(self, url: str, task_id: str) -> Optional[Path]:
        output_path = VIDEO_DIR / f"{task_id}.mp4"
        if output_path.exists():
            return output_path
        try:
            cmd = [
                "yt-dlp", "-f", "best",
                "-o", str(output_path),
                "--no-playlist", url,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0 and output_path.exists():
                return output_path
        except Exception:
            pass
        return None

    def _extract_audio(self, video_path: Path, task_id: str, quality: str) -> Optional[Path]:
        output_path = VIDEO_AUDIO_DIR / f"{task_id}.mp3"
        if output_path.exists():
            return output_path
        bitrate = QUALITY_MAP.get(quality, "64")
        try:
            cmd = [
                FFMPEG_PATH, "-i", str(video_path),
                "-vn", "-acodec", "libmp3lame", "-ab", f"{bitrate}k",
                "-y", str(output_path),
            ]
            subprocess.run(cmd, capture_output=True, timeout=300, check=True)
            return output_path if output_path.exists() else None
        except Exception as e:
            logger.error(f"Audio extraction failed: {e}")
            return None


class LocalVideoHandler(BaseDownloader):
    """Handler for locally uploaded video files."""

    def get_metadata(self, url: str) -> Optional[VideoMetadata]:
        file_path = Path(url)
        if not file_path.exists():
            return None
        title = file_path.stem
        duration = 0
        try:
            cmd = [
                FFMPEG_PATH, "-i", str(file_path),
                "-f", "null", "-",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            duration_match = re.search(r"Duration: (\d+):(\d+):(\d+)\.(\d+)", result.stderr)
            if duration_match:
                h, m, s, _ = duration_match.groups()
                duration = int(h) * 3600 + int(m) * 60 + int(s)
        except Exception:
            pass
        return VideoMetadata(
            title=title,
            duration=duration,
            platform="local",
            url=str(file_path),
        )

    def download_audio(self, url: str, task_id: str, quality: str = "medium") -> Optional[Path]:
        file_path = Path(url)
        if not file_path.exists():
            return None
        output_path = VIDEO_AUDIO_DIR / f"{task_id}.mp3"
        if output_path.exists():
            return output_path
        bitrate = QUALITY_MAP.get(quality, "64")
        try:
            cmd = [
                FFMPEG_PATH, "-i", str(file_path),
                "-vn", "-acodec", "libmp3lame", "-ab", f"{bitrate}k",
                "-y", str(output_path),
            ]
            subprocess.run(cmd, capture_output=True, timeout=600, check=True)
            return output_path if output_path.exists() else None
        except Exception as e:
            logger.error(f"Audio extraction failed: {e}")
            return None

    def download_video(self, url: str, task_id: str) -> Optional[Path]:
        file_path = Path(url)
        if not file_path.exists():
            return None
        output_path = VIDEO_DIR / f"{task_id}.mp4"
        if output_path.exists():
            return output_path
        # Copy or symlink local file
        shutil.copy2(str(file_path), str(output_path))
        return output_path if output_path.exists() else None


def get_downloader(platform: str, cookies: str = "") -> BaseDownloader:
    """Factory to get the appropriate downloader for a platform."""
    downloaders = {
        "bilibili": lambda: BilibiliDownloader(cookies),
        "youtube": lambda: YoutubeDownloader(cookies),
        "douyin": lambda: DouyinDownloader(cookies),
        "kuaishou": lambda: KuaishouDownloader(cookies),
        "local": lambda: LocalVideoHandler(),
    }
    factory = downloaders.get(platform)
    if not factory:
        raise ValueError(f"Unsupported platform: {platform}")
    return factory()


def check_ffmpeg() -> dict:
    """Check if FFmpeg is available and return version info."""
    try:
        result = subprocess.run(
            [FFMPEG_PATH, "-version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            version_line = result.stdout.split("\n")[0] if result.stdout else "unknown"
            return {"available": True, "version": version_line, "path": FFMPEG_PATH}
        return {"available": False, "error": result.stderr[:200]}
    except FileNotFoundError:
        return {"available": False, "error": "FFmpeg not found in PATH"}
    except Exception as e:
        return {"available": False, "error": str(e)}


def check_ytdlp() -> dict:
    """Check if yt-dlp is available."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return {"available": True, "version": result.stdout.strip()}
        return {"available": False, "error": result.stderr[:200]}
    except FileNotFoundError:
        return {"available": False, "error": "yt-dlp not found in PATH"}
    except Exception as e:
        return {"available": False, "error": str(e)}
