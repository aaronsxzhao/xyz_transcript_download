"""
Video downloader supporting multiple platforms: Bilibili, YouTube, Douyin, Kuaishou, and local files.
Uses yt-dlp Python library for Bilibili/YouTube and custom HTTP for Douyin/Kuaishou.
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
from typing import Callable, Optional

import yt_dlp

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


class VideoDownloadError(Exception):
    """Raised when a download fails with a user-facing reason."""

    def __init__(self, message: str, error_code: str = "DOWNLOAD_FAILED"):
        super().__init__(message)
        self.error_code = error_code


def _classify_ytdlp_error(e: Exception, platform: str) -> VideoDownloadError:
    """Classify a yt-dlp exception into an actionable user-facing error."""
    msg = str(e).lower()
    raw = str(e)
    logger.error(f"[yt-dlp error] platform={platform}, error={raw[:500]}")

    if "412" in msg or "precondition" in msg:
        if platform == "bilibili":
            return VideoDownloadError(
                "BiliBili returned 412 (anti-bot). Your cookies may have expired. "
                "Please go to Settings → Platform Accounts → BiliBili and re-login via QR code.",
                "BILIBILI_LOGIN_REQUIRED",
            )
        return VideoDownloadError(
            f"Server rejected the request (412). You may need to set cookies for {platform} in Settings.",
            "COOKIES_REQUIRED",
        )

    # Chinese: 登录 = login, 请先 = please first, 未登录 = not logged in, 需要 = need
    auth_patterns = ["sign in", "login", "need to log in", "confirm your age",
                     "登录", "请先", "未登录", "需要登录", "cookie", "banned",
                     "403", "unauthorized", "authentication"]
    if any(p in msg for p in auth_patterns):
        if platform == "bilibili":
            return VideoDownloadError(
                "BiliBili login expired or invalid. "
                "Please go to Settings → Platform Accounts → BiliBili and re-login via QR code.",
                "BILIBILI_LOGIN_REQUIRED",
            )
        if platform == "youtube":
            return VideoDownloadError(
                "YouTube requires login for this video. "
                "Go to Settings → Platform Accounts → YouTube and follow the 4-step guide to upload your cookies.",
                "LOGIN_REQUIRED",
            )
        return VideoDownloadError(
            f"This video requires login on {platform}. "
            f"Please go to Settings → Platform Accounts → {platform} and import cookies.",
            "LOGIN_REQUIRED",
        )

    if "private" in msg:
        return VideoDownloadError(
            "This video is private and cannot be accessed.",
            "VIDEO_PRIVATE",
        )

    if "removed" in msg or "deleted" in msg or "not available" in msg or "not found" in msg:
        return VideoDownloadError(
            "This video has been removed or is no longer available.",
            "VIDEO_UNAVAILABLE",
        )

    if "age" in msg and ("restrict" in msg or "verif" in msg or "gate" in msg):
        return VideoDownloadError(
            f"This video is age-restricted on {platform}. Please set cookies from a logged-in browser in Settings.",
            "AGE_RESTRICTED",
        )

    if "geo" in msg or "country" in msg or "region" in msg or "not available in your" in msg:
        return VideoDownloadError(
            "This video is not available in your region.",
            "GEO_RESTRICTED",
        )

    if "copyright" in msg or "blocked" in msg:
        return VideoDownloadError(
            "This video is blocked due to copyright restrictions.",
            "COPYRIGHT_BLOCKED",
        )

    if "rate limit" in msg or "too many" in msg or "429" in msg:
        return VideoDownloadError(
            f"Rate limited by {platform}. Please wait a few minutes and try again.",
            "RATE_LIMITED",
        )

    if "ffmpeg" in msg or "ffprobe" in msg:
        return VideoDownloadError(
            "FFmpeg is not installed or not found. It is required for audio extraction.",
            "FFMPEG_MISSING",
        )

    if "unsupported url" in msg or "no suitable" in msg:
        return VideoDownloadError(
            "This URL is not supported. Please check the URL and try again.",
            "UNSUPPORTED_URL",
        )

    return VideoDownloadError(
        f"Download failed: {e}",
        "DOWNLOAD_FAILED",
    )


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


ProgressCallback = Optional["Callable[[float, str], None]"]


class BaseDownloader(ABC):
    """Base class for platform-specific downloaders."""

    @abstractmethod
    def get_metadata(self, url: str) -> Optional[VideoMetadata]:
        pass

    @abstractmethod
    def download_audio(self, url: str, task_id: str, quality: str = "medium",
                       progress_callback: ProgressCallback = None) -> Optional[Path]:
        pass

    @abstractmethod
    def download_video(self, url: str, task_id: str, video_quality: str = "720",
                       progress_callback: ProgressCallback = None) -> Optional[Path]:
        pass

    def get_subtitles(self, url: str, task_id: str) -> Optional[list]:
        """Try to extract platform subtitles. Returns list of segments or None."""
        return None


class YtdlpDownloader(BaseDownloader):
    """Downloader using yt-dlp Python library (for Bilibili, YouTube, etc.)."""

    def __init__(self, platform: str, cookies: str = ""):
        self.platform = platform
        self.cookies = cookies

    def _get_base_opts(self) -> dict:
        """Build base yt-dlp options with cookie support from QR login or manual input."""
        import shutil

        opts = {
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "concurrent_fragment_downloads": 8,
            "retries": 10,
            "fragment_retries": 10,
            "socket_timeout": 30,
            "http_chunk_size": 10485760,
            "throttled_rate": 100_000,
            "buffersize": 1024 * 1024,
            "js_runtimes": {"deno": {}, "node": {}, "bun": {}},
            "remote_components": {"ejs:github"},
        }

        node_path = shutil.which("node")
        if self.platform == "youtube":
            logger.info(f"[yt-dlp] Platform=youtube, node available={node_path is not None}, node_path={node_path}")

        if shutil.which("aria2c"):
            opts["external_downloader"] = "aria2c"
            opts["external_downloader_args"] = {
                "default": ["-x", "16", "-s", "16", "-k", "1M", "--min-split-size=1M"],
            }
        cookie_str = self.cookies
        if not cookie_str:
            try:
                from cookie_manager import get_cookie_manager
                cookie_str = get_cookie_manager().get_cookie(self.platform)
            except Exception:
                pass

        if cookie_str:
            cookie_file = DATA_DIR / f"{self.platform}_cookies.txt"
            cookie_file.write_text(cookie_str, encoding="utf-8")
            opts["cookiefile"] = str(cookie_file)
            lines = [l for l in cookie_str.strip().splitlines() if l.strip() and not l.startswith("#")]
            cookie_names = [l.split("\t")[-2] if "\t" in l else "?" for l in lines[:20]]
            logger.info(f"Using saved cookies for {self.platform}: {len(lines)} entries, keys={cookie_names}")
        elif self.platform == "youtube":
            logger.info("[yt-dlp] No YouTube cookies found, relying on JS challenge solver")
        return opts

    def _best_thumbnail(self, info: dict) -> str:
        thumb = info.get("thumbnail", "")
        if thumb:
            return thumb
        thumbnails = info.get("thumbnails")
        if thumbnails:
            best = max(thumbnails, key=lambda t: t.get("preference", 0))
            return best.get("url", "")
        return ""

    def get_metadata(self, url: str) -> Optional[VideoMetadata]:
        try:
            opts = self._get_base_opts()
            opts["skip_download"] = True
            if self.platform == "youtube":
                opts["quiet"] = False
                opts["no_warnings"] = False
                logger.info(f"[yt-dlp] Extracting YouTube metadata for {url}")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                return None
            if self.platform == "youtube":
                logger.info(f"[yt-dlp] YouTube metadata OK: title={info.get('title', '')[:60]}")
            return VideoMetadata(
                title=info.get("title", ""),
                description=info.get("description", ""),
                thumbnail=self._best_thumbnail(info),
                duration=info.get("duration", 0) or 0,
                platform=self.platform,
                url=url,
                tags=info.get("tags", []) or [],
            )
        except Exception as e:
            logger.error(f"Failed to get metadata for {self.platform}: {type(e).__name__}: {e}")
            return None

    def _make_progress_hook(self, progress_callback: ProgressCallback, label: str = "Downloading"):
        """Create a yt-dlp progress hook that calls our callback."""
        if not progress_callback:
            return []
        last_pct = [-1.0]

        def hook(d):
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                if total > 0:
                    pct = downloaded / total
                    if pct - last_pct[0] >= 0.02:
                        last_pct[0] = pct
                        speed = d.get("speed")
                        eta = d.get("eta")
                        parts = [f"{label}... {pct:.0%}"]
                        if speed and speed > 0:
                            parts.append(f"{speed / 1024 / 1024:.1f} MB/s")
                        if eta and eta > 0:
                            parts.append(f"ETA {eta}s")
                        progress_callback(pct, " | ".join(parts))
            elif d.get("status") == "finished":
                progress_callback(1.0, f"{label} complete, processing...")

        return [hook]

    def download_audio(self, url: str, task_id: str, quality: str = "medium",
                       progress_callback: ProgressCallback = None) -> Optional[Path]:
        output_path = VIDEO_AUDIO_DIR / f"{task_id}.mp3"
        if output_path.exists():
            return output_path

        bitrate = QUALITY_MAP.get(quality, "64")
        try:
            opts = self._get_base_opts()
            # Prefer smaller audio: worst acceptable quality first, fall back to best
            if quality == "fast":
                audio_fmt = "worstaudio[ext=m4a]/worstaudio/bestaudio[ext=m4a]/bestaudio/best"
            elif quality == "medium":
                audio_fmt = "bestaudio[ext=m4a][abr<=128]/bestaudio[abr<=128]/bestaudio[ext=m4a]/bestaudio/best"
            else:
                audio_fmt = "bestaudio[ext=m4a]/bestaudio/best"
            opts.update({
                "format": audio_fmt,
                "outtmpl": str(VIDEO_AUDIO_DIR / f"{task_id}.%(ext)s"),
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": bitrate,
                }],
                "progress_hooks": self._make_progress_hook(progress_callback, "Downloading audio"),
            })
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    self._last_info = info

            if output_path.exists():
                return output_path
            for f in VIDEO_AUDIO_DIR.glob(f"{task_id}.*"):
                if f.suffix in (".mp3", ".m4a", ".wav", ".ogg"):
                    return f
            return None
        except VideoDownloadError:
            raise
        except Exception as e:
            logger.error(f"Audio download failed: {e}")
            raise _classify_ytdlp_error(e, self.platform)

    def get_last_download_info(self) -> Optional[VideoMetadata]:
        """Get metadata from the last download (useful when get_metadata fails)."""
        info = getattr(self, "_last_info", None)
        if not info:
            return None
        return VideoMetadata(
            title=info.get("title", ""),
            description=info.get("description", ""),
            thumbnail=self._best_thumbnail(info),
            duration=info.get("duration", 0) or 0,
            platform=self.platform,
            url=info.get("webpage_url", ""),
            tags=info.get("tags", []) or [],
        )

    def download_video(self, url: str, task_id: str, video_quality: str = "720",
                       progress_callback: ProgressCallback = None) -> Optional[Path]:
        output_path = VIDEO_DIR / f"{task_id}.mp4"
        if output_path.exists():
            return output_path

        try:
            opts = self._get_base_opts()
            if video_quality == "best":
                vfmt = "bv*[ext=mp4]+ba[ext=m4a]/best[ext=mp4]/best"
            else:
                h = int(video_quality) if video_quality.isdigit() else 720
                vfmt = f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/bv*[height<={h}]+ba/best[height<={h}]/best[ext=mp4]/best"
            opts.update({
                "format": vfmt,
                "outtmpl": str(VIDEO_DIR / f"{task_id}.%(ext)s"),
                "merge_output_format": "mp4",
                "progress_hooks": self._make_progress_hook(progress_callback, "Downloading video"),
            })
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

            if output_path.exists():
                return output_path
            for f in VIDEO_DIR.glob(f"{task_id}.*"):
                if f.suffix in (".mp4", ".mkv", ".webm"):
                    return f
            return None
        except VideoDownloadError:
            raise
        except Exception as e:
            logger.error(f"Video download failed: {e}")
            raise _classify_ytdlp_error(e, self.platform)

    def get_subtitles(self, url: str, task_id: str) -> Optional[list]:
        """Try to extract subtitles from the video platform."""
        try:
            sub_dir = DATA_DIR / "subtitles"
            sub_dir.mkdir(exist_ok=True)

            opts = self._get_base_opts()
            opts.update({
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["zh-Hans", "zh", "zh-CN", "ai-zh", "en"],
                "subtitlesformat": "json3/srt/best",
                "skip_download": True,
                "outtmpl": str(sub_dir / f"{task_id}.%(ext)s"),
            })
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)

            subtitles = info.get("requested_subtitles") or {}
            if not subtitles:
                return None

            priority_langs = ["zh-Hans", "zh", "zh-CN", "ai-zh", "en"]
            sub_info = None
            detected_lang = None
            for lang in priority_langs:
                if lang in subtitles:
                    detected_lang = lang
                    sub_info = subtitles[lang]
                    break
            if not sub_info:
                for lang, info_item in subtitles.items():
                    if lang != "danmaku":
                        detected_lang = lang
                        sub_info = info_item
                        break

            if not sub_info:
                return None

            ext = sub_info.get("ext", "json3")
            subtitle_file = sub_dir / f"{task_id}.{detected_lang}.{ext}"

            if not subtitle_file.exists():
                for f in sub_dir.glob(f"{task_id}*.json3"):
                    subtitle_file = f
                    ext = "json3"
                    break
                else:
                    for f in sub_dir.glob(f"{task_id}*.srt"):
                        subtitle_file = f
                        ext = "srt"
                        break

            if not subtitle_file.exists():
                return None

            if ext == "json3":
                return self._parse_json3(subtitle_file)
            else:
                return self._parse_srt(subtitle_file)
        except Exception as e:
            logger.warning(f"Subtitle extraction failed: {e}")
            return None

    def _parse_json3(self, path: Path) -> Optional[list]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        segments = []
        for event in data.get("events", []):
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
        return segments if segments else None

    def _parse_srt(self, path: Path) -> Optional[list]:
        content = path.read_text(encoding="utf-8")
        pattern = r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\n\d+\n|$)"
        matches = re.findall(pattern, content, re.DOTALL)
        segments = []
        for _, start_time, end_time, text in matches:
            text = text.strip()
            if not text:
                continue

            def time_to_seconds(t):
                parts = t.replace(",", ".").split(":")
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])

            segments.append({
                "start": time_to_seconds(start_time),
                "end": time_to_seconds(end_time),
                "text": text,
            })
        return segments if segments else None


class BilibiliDownloader(YtdlpDownloader):
    def __init__(self, cookies: str = ""):
        super().__init__("bilibili", cookies)


class YoutubeDownloader(YtdlpDownloader):
    def __init__(self, cookies: str = ""):
        super().__init__("youtube", cookies)


class DouyinDownloader(BaseDownloader):
    """Downloader for Douyin/TikTok videos using HTTP requests."""

    def __init__(self, cookies: str = ""):
        if not cookies:
            try:
                from cookie_manager import get_cookie_manager
                cookies = get_cookie_manager().get_cookie("douyin")
            except Exception:
                pass
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

    def download_audio(self, url: str, task_id: str, quality: str = "medium",
                       progress_callback: ProgressCallback = None) -> Optional[Path]:
        video_path = self.download_video(url, task_id, progress_callback=progress_callback)
        if not video_path:
            return None
        return self._extract_audio(video_path, task_id, quality)

    def download_video(self, url: str, task_id: str, video_quality: str = "720",
                       progress_callback: ProgressCallback = None) -> Optional[Path]:
        output_path = VIDEO_DIR / f"{task_id}.mp4"
        if output_path.exists():
            return output_path
        try:
            if video_quality == "best":
                vfmt = "best"
            else:
                h = int(video_quality) if video_quality.isdigit() else 720
                vfmt = f"best[height<={h}]/best"
            opts = {
                "format": vfmt,
                "outtmpl": str(VIDEO_DIR / f"{task_id}.%(ext)s"),
                "noplaylist": True,
                "quiet": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            if output_path.exists():
                return output_path
            for f in VIDEO_DIR.glob(f"{task_id}.*"):
                if f.suffix in (".mp4", ".mkv", ".webm"):
                    return f
        except VideoDownloadError:
            raise
        except Exception as e:
            logger.error(f"Douyin video download failed: {e}")
            raise _classify_ytdlp_error(e, "douyin")
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
        if not cookies:
            try:
                from cookie_manager import get_cookie_manager
                cookies = get_cookie_manager().get_cookie("kuaishou")
            except Exception:
                pass
        self.cookies = cookies
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.kuaishou.com/",
        }
        if cookies:
            self.headers["Cookie"] = cookies

    def get_metadata(self, url: str) -> Optional[VideoMetadata]:
        return VideoMetadata(title="Kuaishou Video", platform="kuaishou", url=url)

    def download_audio(self, url: str, task_id: str, quality: str = "medium",
                       progress_callback: ProgressCallback = None) -> Optional[Path]:
        video_path = self.download_video(url, task_id, progress_callback=progress_callback)
        if not video_path:
            return None
        return self._extract_audio(video_path, task_id, quality)

    def download_video(self, url: str, task_id: str, video_quality: str = "720",
                       progress_callback: ProgressCallback = None) -> Optional[Path]:
        output_path = VIDEO_DIR / f"{task_id}.mp4"
        if output_path.exists():
            return output_path
        try:
            if video_quality == "best":
                vfmt = "best"
            else:
                h = int(video_quality) if video_quality.isdigit() else 720
                vfmt = f"best[height<={h}]/best"
            opts = {
                "format": vfmt,
                "outtmpl": str(VIDEO_DIR / f"{task_id}.%(ext)s"),
                "noplaylist": True,
                "quiet": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            if output_path.exists():
                return output_path
            for f in VIDEO_DIR.glob(f"{task_id}.*"):
                if f.suffix in (".mp4", ".mkv", ".webm"):
                    return f
        except VideoDownloadError:
            raise
        except Exception as e:
            logger.error(f"Kuaishou video download failed: {e}")
            raise _classify_ytdlp_error(e, "kuaishou")
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

    def download_audio(self, url: str, task_id: str, quality: str = "medium",
                       progress_callback: ProgressCallback = None) -> Optional[Path]:
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

    def download_video(self, url: str, task_id: str, video_quality: str = "720",
                       progress_callback: ProgressCallback = None) -> Optional[Path]:
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
        return {"available": True, "version": yt_dlp.version.__version__}
    except Exception as e:
        return {"available": False, "error": str(e)}
