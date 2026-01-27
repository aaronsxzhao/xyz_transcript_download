"""
Background daemon for monitoring podcasts and processing new episodes.
Includes health checks, graceful shutdown, and disk space monitoring.
"""

import os
import shutil
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

import schedule

from config import CHECK_INTERVAL, PID_FILE, HEALTH_FILE, DATA_DIR, MIN_DISK_SPACE_MB
from xyz_client import get_client, Episode
from downloader import get_downloader
from transcriber import get_transcriber
from summarizer import get_summarizer
from database import (
    get_database,
    ProcessingStatus,
    PodcastRecord,
    EpisodeRecord,
)
from logger import get_logger

logger = get_logger("daemon")


class PodcastDaemon:
    """Background daemon with health checks and graceful shutdown."""

    def __init__(
        self,
        check_interval: int = CHECK_INTERVAL,
        on_new_episode: Optional[Callable[[Episode], None]] = None,
        on_processing_complete: Optional[Callable[[str], None]] = None,
    ):
        self.check_interval = check_interval
        self.on_new_episode = on_new_episode
        self.on_processing_complete = on_processing_complete
        
        self._running = False
        self._stop_event = threading.Event()
        self._scheduler_thread: Optional[threading.Thread] = None
        self._processor_thread: Optional[threading.Thread] = None
        self._health_thread: Optional[threading.Thread] = None
        self._shutdown_timeout = 30  # seconds

        # Get services
        self.client = get_client()
        self.downloader = get_downloader()
        self.transcriber = get_transcriber()
        self.summarizer = get_summarizer()
        self.db = get_database()

    def start(self, daemonize: bool = True):
        """
        Start the daemon with health monitoring.
        
        Args:
            daemonize: If True, run in background thread. If False, run in main thread.
        """
        if self._running:
            logger.warning("Daemon is already running")
            return

        # Check disk space before starting
        if not self._check_disk_space():
            logger.error("Insufficient disk space. Daemon not started.")
            return

        self._running = True
        self._stop_event.clear()

        # Write PID file
        self._write_pid()

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # Start health check thread
        self._health_thread = threading.Thread(
            target=self._health_loop,
            daemon=True,
            name="HealthCheck"
        )
        self._health_thread.start()

        logger.info(f"Daemon started (check interval: {self.check_interval}s)")

        if daemonize:
            # Run scheduler in background thread
            self._scheduler_thread = threading.Thread(
                target=self._run_scheduler,
                daemon=True,
                name="PodcastScheduler"
            )
            self._scheduler_thread.start()

            # Run processor in background thread
            self._processor_thread = threading.Thread(
                target=self._run_processor,
                daemon=True,
                name="EpisodeProcessor"
            )
            self._processor_thread.start()
        else:
            # Run in main thread (blocking)
            self._run_main_loop()

    def stop(self):
        """Stop the daemon with graceful shutdown."""
        if not self._running:
            return

        logger.info("Stopping daemon...")
        self._running = False
        self._stop_event.set()

        # Remove PID and health files
        self._remove_pid()
        self._remove_health_file()

        # Wait for threads with timeout
        threads = [
            ("scheduler", self._scheduler_thread),
            ("processor", self._processor_thread),
            ("health", self._health_thread),
        ]
        
        for name, thread in threads:
            if thread and thread.is_alive():
                logger.debug(f"Waiting for {name} thread to stop...")
                thread.join(timeout=self._shutdown_timeout // 3)
                if thread.is_alive():
                    logger.warning(f"{name} thread did not stop gracefully")

        logger.info("Daemon stopped")

    def _check_disk_space(self) -> bool:
        """Check if there's enough disk space."""
        try:
            usage = shutil.disk_usage(DATA_DIR)
            free_mb = usage.free / (1024 * 1024)
            if free_mb < MIN_DISK_SPACE_MB:
                logger.warning(f"Low disk space: {free_mb:.0f}MB free (minimum: {MIN_DISK_SPACE_MB}MB)")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to check disk space: {e}")
            return True  # Allow to continue if check fails

    def _health_loop(self):
        """Background loop that writes health status periodically."""
        while not self._stop_event.is_set():
            try:
                self._write_health()
            except Exception as e:
                logger.error(f"Health check failed: {e}")
            self._stop_event.wait(60)  # Update every minute

    def _write_health(self):
        """Write health status to file."""
        health_data = {
            "timestamp": datetime.now().isoformat(),
            "running": self._running,
            "scheduler_alive": self._scheduler_thread.is_alive() if self._scheduler_thread else False,
            "processor_alive": self._processor_thread.is_alive() if self._processor_thread else False,
        }
        with open(HEALTH_FILE, "w") as f:
            import json
            json.dump(health_data, f)

    def _remove_health_file(self):
        """Remove health file."""
        if HEALTH_FILE.exists():
            HEALTH_FILE.unlink()

    def check_podcasts(self):
        """Check all subscribed podcasts for new episodes."""
        if not self._check_disk_space():
            logger.warning("Skipping podcast check due to low disk space")
            return
            
        podcasts = self.db.get_all_podcasts()
        
        if not podcasts:
            logger.debug("No podcasts to check")
            return

        logger.info(f"Checking {len(podcasts)} podcast(s) for updates...")
        for podcast in podcasts:
            self._check_podcast(podcast)

    def _check_podcast(self, podcast: PodcastRecord):
        """Check a single podcast for new episodes."""
        try:
            # Fetch latest episodes from API
            episodes = self.client.get_episodes(podcast.pid, limit=10)

            new_count = 0
            for ep in episodes:
                if not self.db.episode_exists(ep.eid):
                    # Add new episode to database
                    self.db.add_episode(
                        eid=ep.eid,
                        pid=ep.pid,
                        podcast_id=podcast.id,
                        title=ep.title,
                        description=ep.description,
                        duration=ep.duration,
                        pub_date=ep.pub_date,
                        audio_url=ep.audio_url,
                    )
                    new_count += 1

                    if self.on_new_episode:
                        self.on_new_episode(ep)

            if new_count > 0:
                logger.info(f"Found {new_count} new episode(s) for '{podcast.title}'")

            # Update last checked timestamp
            self.db.update_podcast_checked(podcast.pid)

        except Exception as e:
            logger.error(f"Error checking podcast '{podcast.title}': {e}")

    def process_pending_episodes(self):
        """Process all pending episodes."""
        pending = self.db.get_pending_episodes()
        
        for episode_record in pending:
            if self._stop_event.is_set():
                break
            self._process_episode(episode_record)

    def _process_episode(self, episode_record: EpisodeRecord):
        """Process a single episode through the pipeline."""
        eid = episode_record.eid
        
        # Get podcast info
        podcast = self.db.get_podcast_by_id(episode_record.podcast_id)
        podcast_title = podcast.title if podcast else ""

        try:
            # Step 1: Download audio
            if episode_record.status == ProcessingStatus.PENDING:
                logger.info(f"Downloading: {episode_record.title}")
                self.db.update_episode_status(eid, ProcessingStatus.DOWNLOADING)

                # Create Episode object for downloader
                episode = Episode(
                    eid=episode_record.eid,
                    pid=episode_record.pid,
                    title=episode_record.title,
                    description=episode_record.description,
                    duration=episode_record.duration,
                    pub_date=episode_record.pub_date,
                    audio_url=episode_record.audio_url,
                    cover_url="",
                    shownotes="",
                )

                audio_path = self.downloader.download(episode)
                if not audio_path:
                    raise Exception("Download failed")

                self.db.update_episode_status(eid, ProcessingStatus.DOWNLOADED)
                episode_record.status = ProcessingStatus.DOWNLOADED

            # Step 2: Transcribe
            if episode_record.status == ProcessingStatus.DOWNLOADED:
                logger.info(f"Transcribing: {episode_record.title}")
                self.db.update_episode_status(eid, ProcessingStatus.TRANSCRIBING)

                # Get audio path
                episode = Episode(
                    eid=episode_record.eid,
                    pid=episode_record.pid,
                    title=episode_record.title,
                    description="",
                    duration=0,
                    pub_date="",
                    audio_url=episode_record.audio_url,
                    cover_url="",
                    shownotes="",
                )
                audio_path = self.downloader.get_audio_path(episode)

                transcript = self.transcriber.transcribe(audio_path, eid)
                if not transcript:
                    raise Exception("Transcription failed")

                self.transcriber.save_transcript(transcript)
                self.db.update_episode_status(eid, ProcessingStatus.TRANSCRIBED)
                episode_record.status = ProcessingStatus.TRANSCRIBED

            # Step 3: Summarize
            if episode_record.status == ProcessingStatus.TRANSCRIBED:
                logger.info(f"Summarizing: {episode_record.title}")
                self.db.update_episode_status(eid, ProcessingStatus.SUMMARIZING)

                transcript = self.transcriber.load_transcript(eid)
                if not transcript:
                    raise Exception("Could not load transcript")

                summary = self.summarizer.summarize(
                    transcript,
                    podcast_title=podcast_title,
                    episode_title=episode_record.title,
                )
                if not summary:
                    raise Exception("Summarization failed")

                self.summarizer.save_summary(summary)
                self.db.update_episode_status(eid, ProcessingStatus.COMPLETED)

                logger.info(f"Completed: {episode_record.title}")

                if self.on_processing_complete:
                    self.on_processing_complete(eid)

        except Exception as e:
            logger.error(f"Error processing '{episode_record.title}': {e}")
            self.db.update_episode_status(eid, ProcessingStatus.FAILED, str(e))

    def _run_scheduler(self):
        """Run the scheduler loop in a background thread."""
        # Schedule periodic checks
        schedule.every(self.check_interval).seconds.do(self.check_podcasts)

        # Initial check
        self.check_podcasts()

        while not self._stop_event.is_set():
            schedule.run_pending()
            time.sleep(1)

    def _run_processor(self):
        """Run the processor loop in a background thread."""
        while not self._stop_event.is_set():
            self.process_pending_episodes()
            # Sleep between processing cycles
            self._stop_event.wait(30)

    def _run_main_loop(self):
        """Run the main loop (blocking)."""
        # Schedule periodic checks
        schedule.every(self.check_interval).seconds.do(self.check_podcasts)

        # Initial check
        self.check_podcasts()

        while self._running:
            schedule.run_pending()
            self.process_pending_episodes()
            time.sleep(1)

    def _handle_signal(self, signum, frame):
        """Handle termination signals."""
        self.stop()
        sys.exit(0)

    def _write_pid(self):
        """Write PID to file."""
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))

    def _remove_pid(self):
        """Remove PID file."""
        if PID_FILE.exists():
            PID_FILE.unlink()

    @staticmethod
    def is_running() -> bool:
        """Check if daemon is running by checking PID file."""
        if not PID_FILE.exists():
            return False

        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            
            # Check if process is running
            os.kill(pid, 0)
            return True
        except (ValueError, OSError):
            return False

    @staticmethod
    def get_pid() -> Optional[int]:
        """Get the daemon PID if running."""
        if not PID_FILE.exists():
            return None

        try:
            with open(PID_FILE, "r") as f:
                return int(f.read().strip())
        except (ValueError, IOError):
            return None


def process_single_episode(
    podcast_name_or_id: str,
    episode_title_or_id: str,
) -> bool:
    """
    Process a single episode manually.
    
    Args:
        podcast_name_or_id: Podcast URL or ID
        episode_title_or_id: Episode title, URL, or ID
        
    Returns:
        True if successful, False otherwise
    """
    from rich.console import Console
    console = Console()

    # Get services
    client = get_client()
    downloader = get_downloader()
    db = get_database()

    # Find podcast
    pid = client.extract_podcast_id(podcast_name_or_id)
    if not pid:
        console.print(f"[red]✗ Could not find podcast: {podcast_name_or_id}[/red]")
        return False

    podcast = client.get_podcast(pid)
    if not podcast:
        console.print(f"[red]✗ Could not get podcast details[/red]")
        return False

    # Ensure podcast is in database
    db_podcast = db.get_podcast(pid)
    if not db_podcast:
        db.add_podcast(
            pid=podcast.pid,
            title=podcast.title,
            author=podcast.author,
            description=podcast.description,
            cover_url=podcast.cover_url,
        )
        db_podcast = db.get_podcast(pid)

    # Find episode
    eid = client.extract_episode_id(episode_title_or_id)
    
    if eid:
        episode = client.get_episode(eid)
    else:
        # Search in episodes
        episodes = client.get_episodes(pid, limit=50)
        episode = None
        for ep in episodes:
            if episode_title_or_id.lower() in ep.title.lower():
                episode = ep
                break

    if not episode:
        console.print(f"[red]✗ Could not find episode: {episode_title_or_id}[/red]")
        return False

    console.print(f"\n[bold]Processing:[/bold] {episode.title}")

    # Add to database if not exists
    if not db.episode_exists(episode.eid):
        db.add_episode(
            eid=episode.eid,
            pid=episode.pid,
            podcast_id=db_podcast.id,
            title=episode.title,
            description=episode.description,
            duration=episode.duration,
            pub_date=episode.pub_date,
            audio_url=episode.audio_url,
        )

    # Create daemon instance to use its processing logic
    daemon = PodcastDaemon()

    episode_record = db.get_episode(episode.eid)
    if episode_record:
        daemon._process_episode(episode_record)
        return True

    return False


# Global daemon instance
_daemon: Optional[PodcastDaemon] = None


def get_daemon() -> PodcastDaemon:
    """Get or create the global PodcastDaemon instance."""
    global _daemon
    if _daemon is None:
        _daemon = PodcastDaemon()
    return _daemon
