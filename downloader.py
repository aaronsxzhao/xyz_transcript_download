"""
Audio file downloader with resume and retry support.
Downloads podcast episodes from Xiaoyuzhou.
"""

import os
import time
from pathlib import Path
from typing import Optional, Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import AUDIO_DIR, DEFAULT_HEADERS
from xyz_client import Episode
from logger import get_logger

logger = get_logger("downloader")


def create_session_with_retries(retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET"],
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session


class AudioDownloader:
    """Downloads audio files with resume and retry support."""

    def __init__(self, base_dir: Optional[Path] = None, max_retries: int = 5):
        self.base_dir = base_dir or AUDIO_DIR
        self.max_retries = max_retries
        self.chunk_size = 1024 * 1024  # 1MB chunks for better reliability

    def get_audio_path(self, episode: Episode) -> Path:
        """
        Get the path where an episode's audio should be stored.
        
        Args:
            episode: Episode object
            
        Returns:
            Path to the audio file
        """
        # Create podcast-specific directory
        podcast_dir = self.base_dir / (episode.pid or "unknown")
        podcast_dir.mkdir(parents=True, exist_ok=True)

        # Determine file extension from URL
        ext = self._get_extension(episode.audio_url)
        filename = f"{episode.eid}{ext}"

        return podcast_dir / filename

    def _get_extension(self, url: str) -> str:
        """Extract file extension from URL."""
        # Remove query parameters
        path = url.split("?")[0]
        
        if path.endswith(".m4a"):
            return ".m4a"
        elif path.endswith(".mp3"):
            return ".mp3"
        elif path.endswith(".wav"):
            return ".wav"
        else:
            # Default to m4a for Xiaoyuzhou
            return ".m4a"

    def is_downloaded(self, episode: Episode) -> bool:
        """Check if episode audio is already downloaded."""
        audio_path = self.get_audio_path(episode)
        return audio_path.exists() and audio_path.stat().st_size > 0

    def download(
        self,
        episode: Episode,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        force: bool = False,
    ) -> Optional[Path]:
        """
        Download episode audio file with resume and retry support.
        
        Args:
            episode: Episode to download
            progress_callback: Optional callback(downloaded_bytes, total_bytes)
            force: Force re-download even if file exists
            
        Returns:
            Path to downloaded file, or None on failure
        """
        if not episode.audio_url:
            logger.error(f"No audio URL for episode: {episode.title}")
            return None

        audio_path = self.get_audio_path(episode)

        # Check if already downloaded
        if not force and self.is_downloaded(episode):
            return audio_path

        # Create session with retry logic
        session = create_session_with_retries()
        session.headers.update(DEFAULT_HEADERS)

        # Get file size
        total_size = 0
        try:
            head_response = session.head(episode.audio_url, timeout=30)
            total_size = int(head_response.headers.get("content-length", 0))
        except requests.RequestException:
            pass  # Will try to get size from GET response

        # Download with retry logic
        for attempt in range(self.max_retries):
            try:
                result = self._download_with_resume(
                    session, episode.audio_url, audio_path, total_size, progress_callback
                )
                if result:
                    return audio_path
                    
            except Exception as e:
                wait_time = (attempt + 1) * 2  # Exponential backoff
                if attempt < self.max_retries - 1:
                    logger.warning(f"Download interrupted, retrying in {wait_time}s... (attempt {attempt + 2}/{self.max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Download failed after {self.max_retries} attempts: {e}")
                    return None

        return None

    def _download_with_resume(
        self,
        session: requests.Session,
        url: str,
        audio_path: Path,
        total_size: int,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """Download file with resume support."""
        
        # Check for existing partial download
        existing_size = 0
        if audio_path.exists():
            existing_size = audio_path.stat().st_size
            
            # If we already have the full file, we're done
            if total_size > 0 and existing_size >= total_size:
                return True

        # Prepare headers for resume
        headers = {}
        mode = "wb"
        
        if existing_size > 0:
            headers["Range"] = f"bytes={existing_size}-"
            mode = "ab"
            logger.info(f"Resuming download from {existing_size / (1024*1024):.1f}MB...")

        # Make request with timeout
        response = session.get(
            url,
            headers=headers,
            stream=True,
            timeout=(30, 60),  # (connect timeout, read timeout)
        )
        response.raise_for_status()

        # Get total size from response if not known
        if total_size == 0:
            content_length = response.headers.get("content-length", 0)
            total_size = int(content_length) + existing_size

        downloaded = existing_size

        with open(audio_path, mode) as f:
            for chunk in response.iter_content(chunk_size=self.chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size)

        # Verify download is complete
        final_size = audio_path.stat().st_size
        if total_size > 0 and final_size < total_size:
            # Incomplete - will be retried
            raise Exception(f"Incomplete download: {final_size}/{total_size} bytes")

        return True

    def delete(self, episode: Episode) -> bool:
        """
        Delete downloaded audio file.
        
        Args:
            episode: Episode whose audio to delete
            
        Returns:
            True if deleted, False otherwise
        """
        audio_path = self.get_audio_path(episode)
        if audio_path.exists():
            audio_path.unlink()
            return True
        return False


# Global downloader instance
_downloader: Optional[AudioDownloader] = None


def get_downloader() -> AudioDownloader:
    """Get or create the global AudioDownloader instance."""
    global _downloader
    if _downloader is None:
        _downloader = AudioDownloader()
    return _downloader
