"""
Transcription service using faster-whisper (CTranslate2).
Optimized for speed with batched inference and int8/fp16 support.
"""

import json
import os
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Callable

from config import (
    WHISPER_MODE,
    WHISPER_LOCAL_MODEL,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_BATCH_SIZE,
    WHISPER_BACKEND,
    WHISPER_API_KEY,
    WHISPER_BASE_URL,
    WHISPER_API_MODEL,
    MAX_AUDIO_SIZE_MB,
    TRANSCRIPTS_DIR,
)
from logger import get_logger

logger = get_logger("transcriber")

# Try to use imageio-ffmpeg if available (for API transcriber)
try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
    ffmpeg_dir = os.path.dirname(FFMPEG_PATH)
    if ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
except ImportError:
    FFMPEG_PATH = "ffmpeg"


@dataclass
class TranscriptSegment:
    """A segment of the transcript with timing."""
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    """Full transcript of an episode."""
    episode_id: str
    language: str
    duration: float
    text: str
    segments: List[TranscriptSegment]


# Model size mapping for faster-whisper
MODEL_MAP = {
    "tiny": "tiny",
    "base": "base",
    "small": "small",
    "medium": "medium",
    "large": "large-v3",
    "large-v2": "large-v2",
    "large-v3": "large-v3",
    "turbo": "turbo",
}

# Model mapping for mlx-whisper (uses different naming)
MLX_MODEL_MAP = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large": "mlx-community/whisper-large-v3-mlx",
    "large-v2": "mlx-community/whisper-large-v2-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "turbo": "mlx-community/whisper-large-v3-turbo",
}


def _detect_best_backend() -> str:
    """Detect the best backend for the current system."""
    import platform
    
    # Check if on Apple Silicon
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        try:
            import mlx
            logger.info("Detected Apple Silicon with MLX - using mlx-whisper")
            return "mlx-whisper"
        except ImportError:
            logger.info("Apple Silicon detected but mlx not installed - using faster-whisper")
            return "faster-whisper"
    
    return "faster-whisper"


class FastLocalTranscriber:
    """
    Fast transcription using faster-whisper with CTranslate2.
    
    Features:
    - Up to 4x faster than openai-whisper
    - Batched inference for even faster processing
    - INT8 quantization for lower memory usage
    - Built-in VAD filter
    - Configurable device and compute type
    """

    def __init__(self, model_name: str = "small"):
        self.model_name = MODEL_MAP.get(model_name, model_name)
        self._model = None
        self._batched_model = None
        self._device = None
        self._compute_type = None
        self._batch_size = None

    def _setup(self):
        """Initialize the faster-whisper model."""
        if self._model is not None:
            return

        from faster_whisper import WhisperModel, BatchedInferencePipeline
        import torch

        # Determine device
        if WHISPER_DEVICE == "auto":
            if torch.cuda.is_available():
                self._device = "cuda"
            else:
                self._device = "cpu"
        else:
            self._device = WHISPER_DEVICE

        # Determine compute type
        if WHISPER_COMPUTE_TYPE == "auto":
            if self._device == "cuda":
                self._compute_type = "float16"
            else:
                self._compute_type = "int8"
        else:
            self._compute_type = WHISPER_COMPUTE_TYPE

        # Determine batch size
        if WHISPER_BATCH_SIZE > 0:
            self._batch_size = WHISPER_BATCH_SIZE
        elif self._device == "cuda":
            self._batch_size = 16
        else:
            self._batch_size = 8

        # Log configuration
        logger.info(f"Device: {self._device}")
        logger.info(f"Compute type: {self._compute_type}")
        logger.info(f"Batch size: {self._batch_size}")
        logger.info(f"Loading model: {self.model_name}...")

        # Load model
        self._model = WhisperModel(
            self.model_name,
            device=self._device,
            compute_type=self._compute_type,
        )

        # Create batched inference pipeline for faster processing
        self._batched_model = BatchedInferencePipeline(model=self._model)

        logger.info("Model loaded and ready.")

    def transcribe(
        self,
        audio_path: Path,
        episode_id: str,
        language: str = "zh",
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> Optional[Transcript]:
        """
        Transcribe an audio file using faster-whisper with batched inference.

        Args:
            audio_path: Path to the audio file
            episode_id: Episode ID for reference
            language: Language code (default: zh for Chinese)
            progress_callback: Optional callback for progress updates

        Returns:
            Transcript object or None on failure
        """
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return None

        try:
            self._setup()

            logger.info(f"Transcribing with batch_size={self._batch_size}...")

            # Run batched transcription with VAD filter
            segments_generator, info = self._batched_model.transcribe(
                str(audio_path),
                language=language,
                batch_size=self._batch_size,
                vad_filter=True,  # Filter out silence
                vad_parameters=dict(min_silence_duration_ms=500),
            )

            logger.info(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")
            logger.info(f"Audio duration: {info.duration:.1f}s ({info.duration/60:.1f} min)")

            # Collect segments with progress tracking
            segments = []
            full_text_parts = []
            
            for segment in segments_generator:
                segments.append(TranscriptSegment(
                    start=segment.start,
                    end=segment.end,
                    text=segment.text.strip(),
                ))
                full_text_parts.append(segment.text.strip())
                
                # Update progress based on segment end time
                if progress_callback and info.duration > 0:
                    progress = min(segment.end / info.duration, 1.0)
                    progress_callback(progress)

            full_text = " ".join(full_text_parts)

            if progress_callback:
                progress_callback(1.0)

            logger.info(f"Transcription complete: {len(segments)} segments")

            return Transcript(
                episode_id=episode_id,
                language=info.language,
                duration=info.duration,
                text=full_text,
                segments=segments,
            )

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None


class MLXTranscriber:
    """
    Fast transcription using mlx-whisper on Apple Silicon.
    
    Features:
    - Uses Apple Silicon GPU via MLX framework
    - Significantly faster than CPU on M1/M2/M3
    - Optimized for Apple Neural Engine
    """

    def __init__(self, model_name: str = "small"):
        self.model_name = model_name
        self.model_id = MLX_MODEL_MAP.get(model_name, f"mlx-community/whisper-{model_name}-mlx")
        self._transcribe_fn = None

    def _setup(self):
        """Initialize mlx-whisper."""
        if self._transcribe_fn is not None:
            return

        try:
            import mlx_whisper
            self._transcribe_fn = mlx_whisper.transcribe
            logger.info(f"MLX-Whisper loaded: {self.model_id}")
        except ImportError:
            raise ImportError(
                "mlx-whisper not installed. Install with: pip install mlx-whisper"
            )

    def transcribe(
        self,
        audio_path: Path,
        episode_id: str,
        language: str = "zh",
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> Optional[Transcript]:
        """
        Transcribe an audio file using mlx-whisper.

        Args:
            audio_path: Path to the audio file
            episode_id: Episode ID for reference
            language: Language code (default: zh for Chinese)
            progress_callback: Optional callback for progress updates

        Returns:
            Transcript object or None on failure
        """
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return None

        try:
            self._setup()

            logger.info(f"Transcribing with MLX-Whisper ({self.model_id})...")

            # Run transcription
            result = self._transcribe_fn(
                str(audio_path),
                path_or_hf_repo=self.model_id,
                language=language,
                verbose=False,
            )

            # Parse results
            segments = []
            full_text = result.get("text", "")

            for seg in result.get("segments", []):
                segments.append(TranscriptSegment(
                    start=seg.get("start", 0),
                    end=seg.get("end", 0),
                    text=seg.get("text", "").strip(),
                ))
                
                # Update progress
                if progress_callback and segments:
                    # Estimate progress from segment timing
                    progress_callback(min(seg.get("end", 0) / max(result.get("duration", 1), 1), 1.0))

            if progress_callback:
                progress_callback(1.0)

            # Get duration from last segment or result
            duration = segments[-1].end if segments else 0

            logger.info(f"Transcription complete: {len(segments)} segments")

            return Transcript(
                episode_id=episode_id,
                language=result.get("language", language),
                duration=duration,
                text=full_text,
                segments=segments,
            )

        except Exception as e:
            logger.error(f"MLX transcription failed: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None


class APITranscriber:
    """Handles audio transcription using Whisper API (OpenAI or Groq)."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        from openai import OpenAI

        self.api_key = api_key or WHISPER_API_KEY
        self.base_url = base_url or WHISPER_BASE_URL

        if not self.api_key:
            raise ValueError("API key is required for API transcription. Set GROQ_API_KEY or OPENAI_API_KEY.")

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.max_size = MAX_AUDIO_SIZE_MB * 1024 * 1024
        
        logger.info(f"Using Whisper API: {self.base_url}")

    def transcribe(
        self,
        audio_path: Path,
        episode_id: str,
        language: str = "zh",
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> Optional[Transcript]:
        """Transcribe an audio file using OpenAI API."""
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return None

        file_size = audio_path.stat().st_size

        if file_size <= self.max_size:
            return self._transcribe_file(audio_path, episode_id, language)

        return self._transcribe_large_file(audio_path, episode_id, language)

    def _transcribe_file(
        self,
        audio_path: Path,
        episode_id: str,
        language: str,
    ) -> Optional[Transcript]:
        """Transcribe a single audio file."""
        try:
            with open(audio_path, "rb") as audio_file:
                response = self.client.audio.transcriptions.create(
                    model=WHISPER_API_MODEL,
                    file=audio_file,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )

            segments = []
            if hasattr(response, 'segments'):
                for seg in response.segments:
                    segments.append(TranscriptSegment(
                        start=seg.get("start", 0),
                        end=seg.get("end", 0),
                        text=seg.get("text", "").strip(),
                    ))

            return Transcript(
                episode_id=episode_id,
                language=response.language if hasattr(response, 'language') else language,
                duration=response.duration if hasattr(response, 'duration') else 0,
                text=response.text,
                segments=segments,
            )

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return None

    def _transcribe_large_file(
        self,
        audio_path: Path,
        episode_id: str,
        language: str,
    ) -> Optional[Transcript]:
        """Transcribe a large audio file by splitting."""
        import tempfile

        file_size = audio_path.stat().st_size
        num_chunks = (file_size // self.max_size) + 1

        duration = self._get_audio_duration(audio_path)
        if duration == 0:
            logger.error("Could not determine audio duration")
            return None

        chunk_duration = duration / num_chunks

        all_segments = []
        all_text = []
        time_offset = 0

        with tempfile.TemporaryDirectory() as temp_dir:
            for i in range(num_chunks):
                start_time = i * chunk_duration
                chunk_path = Path(temp_dir) / f"chunk_{i}.mp3"

                if not self._extract_chunk(audio_path, chunk_path, start_time, chunk_duration):
                    continue

                chunk_transcript = self._transcribe_file(
                    chunk_path, f"{episode_id}_chunk_{i}", language
                )

                if chunk_transcript:
                    for seg in chunk_transcript.segments:
                        adjusted_seg = TranscriptSegment(
                            start=seg.start + time_offset,
                            end=seg.end + time_offset,
                            text=seg.text,
                        )
                        all_segments.append(adjusted_seg)

                    all_text.append(chunk_transcript.text)

                time_offset += chunk_duration

        if not all_text:
            return None

        return Transcript(
            episode_id=episode_id,
            language=language,
            duration=duration,
            text=" ".join(all_text),
            segments=all_segments,
        )

    def _get_audio_duration(self, audio_path: Path) -> float:
        """Get audio duration using ffprobe."""
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
            )
            return float(result.stdout.strip())
        except (subprocess.SubprocessError, ValueError):
            return 0

    def _extract_chunk(
        self,
        input_path: Path,
        output_path: Path,
        start_time: float,
        duration: float,
    ) -> bool:
        """Extract a chunk from audio file using ffmpeg."""
        try:
            subprocess.run(
                [
                    FFMPEG_PATH, "-y", "-v", "quiet",
                    "-i", str(input_path),
                    "-ss", str(start_time),
                    "-t", str(duration),
                    "-acodec", "libmp3lame",
                    "-ab", "64k",
                    str(output_path)
                ],
                check=True,
            )
            return output_path.exists()
        except subprocess.SubprocessError:
            return False


class Transcriber:
    """
    Unified transcriber that supports local (faster-whisper, mlx-whisper) and API modes.
    Automatically selects the best backend for the current system.
    """

    def __init__(self):
        if WHISPER_MODE == "local":
            # Determine which backend to use
            backend = WHISPER_BACKEND
            if backend == "auto":
                backend = _detect_best_backend()
            
            if backend == "mlx-whisper":
                logger.info("Using MLX-Whisper (Apple Silicon GPU)")
                self._transcriber = MLXTranscriber(model_name=WHISPER_LOCAL_MODEL)
            else:
                logger.info("Using faster-whisper (CTranslate2)")
                self._transcriber = FastLocalTranscriber(model_name=WHISPER_LOCAL_MODEL)
        else:
            self._transcriber = APITranscriber()

    def transcribe(
        self,
        audio_path: Path,
        episode_id: str,
        language: str = "zh",
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> Optional[Transcript]:
        """Transcribe an audio file."""
        return self._transcriber.transcribe(
            audio_path, episode_id, language, progress_callback
        )

    def save_transcript(self, transcript: Transcript) -> Path:
        """Save transcript to JSON file."""
        output_path = TRANSCRIPTS_DIR / f"{transcript.episode_id}.json"

        data = {
            "episode_id": transcript.episode_id,
            "language": transcript.language,
            "duration": transcript.duration,
            "text": transcript.text,
            "segments": [asdict(seg) for seg in transcript.segments],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return output_path

    def load_transcript(self, episode_id: str) -> Optional[Transcript]:
        """Load transcript from JSON file."""
        file_path = TRANSCRIPTS_DIR / f"{episode_id}.json"

        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            segments = [
                TranscriptSegment(**seg)
                for seg in data.get("segments", [])
            ]

            return Transcript(
                episode_id=data["episode_id"],
                language=data["language"],
                duration=data["duration"],
                text=data["text"],
                segments=segments,
            )
        except (json.JSONDecodeError, KeyError, IOError):
            return None

    def transcript_exists(self, episode_id: str) -> bool:
        """Check if transcript already exists."""
        file_path = TRANSCRIPTS_DIR / f"{episode_id}.json"
        return file_path.exists()


# Global transcriber instance
_transcriber: Optional[Transcriber] = None


def get_transcriber() -> Transcriber:
    """Get or create the global Transcriber instance."""
    global _transcriber
    if _transcriber is None:
        _transcriber = Transcriber()
    return _transcriber
