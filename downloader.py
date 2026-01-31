"""
Audio file downloader with resume and retry support.
Downloads podcast episodes from Xiaoyuzhou.
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Optional, Callable, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import AUDIO_DIR, DEFAULT_HEADERS
from xyz_client import Episode
from logger import get_logger

logger = get_logger("downloader")

# Try to use imageio-ffmpeg if available
try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_PATH = "ffmpeg"


def _get_audio_duration_ffprobe(audio_path: Path) -> float:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path)
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        return float(result.stdout.strip())
    except (subprocess.SubprocessError, ValueError):
        return 0


def compress_audio(input_path: Path, output_path: Optional[Path] = None) -> Optional[Path]:
    """
    Compress audio for fast processing.
    
    Creates a smaller version of the audio file optimized for speech recognition:
    - Mono channel (speech doesn't need stereo)
    - 16kHz sample rate (sufficient for Whisper)
    - 64kbps bitrate (enough for speech clarity)
    
    This typically results in 5-10x smaller file size and 3-5x faster transcription.
    
    Args:
        input_path: Path to the original audio file
        output_path: Path for compressed output (default: input_fast.mp3)
        
    Returns:
        Path to compressed file, or None on failure
    """
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return None
    
    # Generate output path if not provided
    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_fast.mp3"
    
    # Skip if compressed version already exists and is newer
    if output_path.exists():
        if output_path.stat().st_mtime >= input_path.stat().st_mtime:
            # Verify the cached compressed file has the same duration as the original
            # This prevents using truncated files from previous timed-out compressions
            input_duration = _get_audio_duration_ffprobe(input_path)
            output_duration = _get_audio_duration_ffprobe(output_path)
            
            # Allow 1 second tolerance for duration comparison
            if input_duration > 0 and output_duration > 0 and abs(input_duration - output_duration) <= 1:
                logger.info(f"Using existing compressed audio: {output_path} ({output_duration/60:.1f} min)")
                return output_path
            elif input_duration > 0 and output_duration > 0:
                # Compressed file is truncated, delete and re-compress
                logger.warning(f"Cached compressed audio is truncated ({output_duration/60:.1f}min vs {input_duration/60:.1f}min), re-compressing...")
                try:
                    output_path.unlink()
                except OSError:
                    pass
            # If we can't determine duration, proceed with compression to be safe
    
    try:
        # Get input file size to estimate timeout
        # For compression, ffmpeg typically processes at ~10x real-time on slow machines
        # So a 100 minute audio should complete in ~10 minutes
        # We use input file size as a proxy: ~1MB per minute of audio at 128kbps
        input_size_mb = input_path.stat().st_size / (1024 * 1024)
        # Estimate: 1 minute per 10MB of input, minimum 5 minutes, maximum 60 minutes
        estimated_timeout = max(300, min(3600, int(input_size_mb * 6)))
        
        logger.info(f"Compressing audio: {input_path.name} -> {output_path.name} (timeout: {estimated_timeout}s)")
        
        # ffmpeg command for speech-optimized compression
        cmd = [
            FFMPEG_PATH,
            "-y",  # Overwrite output
            "-i", str(input_path),
            "-ac", "1",  # Mono
            "-ar", "16000",  # 16kHz sample rate
            "-b:a", "64k",  # 64kbps bitrate
            "-f", "mp3",  # MP3 format
            str(output_path)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=estimated_timeout
        )
        
        if result.returncode != 0:
            logger.error(f"ffmpeg compression failed: {result.stderr}")
            # Clean up partial output
            if output_path.exists():
                try:
                    output_path.unlink()
                except OSError:
                    pass
            return None
        
        # Verify output duration matches input duration
        input_duration = _get_audio_duration_ffprobe(input_path)
        output_duration = _get_audio_duration_ffprobe(output_path)
        
        if input_duration > 0 and output_duration > 0:
            if abs(input_duration - output_duration) > 1:
                logger.error(f"Compressed audio duration mismatch: {output_duration/60:.1f}min vs expected {input_duration/60:.1f}min")
                # Clean up incomplete file
                try:
                    output_path.unlink()
                except OSError:
                    pass
                return None
        
        # Log compression ratio
        original_size = input_path.stat().st_size
        compressed_size = output_path.stat().st_size
        ratio = original_size / compressed_size if compressed_size > 0 else 0
        
        logger.info(f"Compression complete: {original_size/1024/1024:.1f}MB -> {compressed_size/1024/1024:.1f}MB ({ratio:.1f}x smaller)")
        
        return output_path
        
    except subprocess.TimeoutExpired:
        logger.error(f"Audio compression timed out after {estimated_timeout}s")
        # Clean up partial output file to prevent reuse
        if output_path.exists():
            try:
                output_path.unlink()
                logger.info("Deleted partial compressed file")
            except OSError:
                pass
        return None
    except Exception as e:
        logger.error(f"Audio compression failed: {e}")
        # Clean up partial output
        if output_path.exists():
            try:
                output_path.unlink()
            except OSError:
                pass
        return None


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

    def get_compressed_path(self, episode: Episode) -> Path:
        """Get the path for the compressed (fast) version of an episode's audio."""
        original_path = self.get_audio_path(episode)
        return original_path.parent / f"{original_path.stem}_fast.mp3"
    
    def compress(self, episode: Episode) -> Optional[Path]:
        """
        Create a compressed version of the episode audio for fast processing.
        
        Args:
            episode: Episode to compress
            
        Returns:
            Path to compressed audio, or None on failure
        """
        original_path = self.get_audio_path(episode)
        if not original_path.exists():
            logger.error(f"Original audio not found: {original_path}")
            return None
        
        compressed_path = self.get_compressed_path(episode)
        return compress_audio(original_path, compressed_path)
    
    def delete(self, episode: Episode) -> bool:
        """
        Delete downloaded audio file (both original and compressed).
        
        Args:
            episode: Episode whose audio to delete
            
        Returns:
            True if deleted, False otherwise
        """
        deleted = False
        
        # Delete original
        audio_path = self.get_audio_path(episode)
        if audio_path.exists():
            audio_path.unlink()
            deleted = True
        
        # Delete compressed version too
        compressed_path = self.get_compressed_path(episode)
        if compressed_path.exists():
            compressed_path.unlink()
            deleted = True
            
        return deleted


# Global downloader instance
_downloader: Optional[AudioDownloader] = None


def get_downloader() -> AudioDownloader:
    """Get or create the global AudioDownloader instance."""
    global _downloader
    if _downloader is None:
        _downloader = AudioDownloader()
    return _downloader
