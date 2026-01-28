"""
Command-line interface for the Xiaoyuzhou Podcast Tool.
Includes rich progress bars for downloads and transcription.
"""

import argparse
import sys
import os
import signal
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich import box
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
    TimeElapsedColumn,
    DownloadColumn,
    TransferSpeedColumn,
)

from logger import setup_logging, get_logger

console = Console()
logger = get_logger("cli")




def cmd_add(args):
    """Subscribe to a podcast."""
    from xyz_client import get_client
    from database import get_database
    
    client = get_client()
    db = get_database()
    
    podcast_input = args.podcast
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching podcast info...", total=None)
        
        # Try to find podcast
        pid = client.extract_podcast_id(podcast_input)
        
        if not pid:
            progress.stop()
            console.print(f"[red]✗ Could not parse podcast URL: {podcast_input}[/red]")
            console.print("Please provide a URL like: https://www.xiaoyuzhoufm.com/podcast/xxx")
            return False
        
        progress.update(task, description="Getting podcast details...")
        podcast = client.get_podcast(pid)
        
        if not podcast:
            progress.stop()
            console.print("[red]✗ Could not get podcast details[/red]")
            return False
    
    # Check if already subscribed
    if db.get_podcast(podcast.pid):
        console.print(f"[yellow]Already subscribed to: {podcast.title}[/yellow]")
        return True
    
    # Add to database
    db.add_podcast(
        pid=podcast.pid,
        title=podcast.title,
        author=podcast.author,
        description=podcast.description,
        cover_url=podcast.cover_url,
    )
    
    console.print(f"\n[green]✓ Subscribed to: {podcast.title}[/green]")
    if podcast.author:
        console.print(f"  Author: {podcast.author}")
    
    return True


def cmd_remove(args):
    """Unsubscribe from a podcast."""
    from xyz_client import get_client
    from database import get_database
    
    client = get_client()
    db = get_database()
    
    podcast_input = args.podcast
    
    # Find podcast
    pid = client.extract_podcast_id(podcast_input)
    if not pid:
        # Try to find by name in database
        podcasts = db.get_all_podcasts()
        for p in podcasts:
            if podcast_input.lower() in p.title.lower():
                pid = p.pid
                break
    
    if not pid:
        console.print(f"[red]✗ Could not find podcast: {podcast_input}[/red]")
        return False
    
    podcast = db.get_podcast(pid)
    if not podcast:
        console.print(f"[yellow]Not subscribed to this podcast[/yellow]")
        return True
    
    # Confirm deletion
    if not args.yes:
        console.print(f"\nRemove podcast: [bold]{podcast.title}[/bold]?")
        confirm = input("This will also remove all episode data. Continue? (y/N): ")
        if confirm.lower() != "y":
            console.print("Cancelled.")
            return False
    
    db.delete_podcast(pid)
    console.print(f"[green]✓ Removed: {podcast.title}[/green]")
    return True


def cmd_list(args):
    """List all subscribed podcasts."""
    from database import get_database
    
    db = get_database()
    podcasts = db.get_all_podcasts()
    
    if not podcasts:
        console.print("[yellow]No podcasts subscribed yet.[/yellow]")
        console.print("Use 'add <podcast_name>' to subscribe.")
        return
    
    table = Table(title="Subscribed Podcasts")
    table.add_column("Title", style="cyan")
    table.add_column("Author", style="green")
    table.add_column("Last Checked", style="yellow")
    table.add_column("PID", style="dim")
    
    for podcast in podcasts:
        last_checked = podcast.last_checked[:10] if podcast.last_checked else "Never"
        table.add_row(
            podcast.title,
            podcast.author,
            last_checked,
            podcast.pid[:12] + "...",
        )
    
    console.print(table)


def cmd_episodes(args):
    """List episodes for a podcast."""
    from xyz_client import get_client
    from database import get_database, ProcessingStatus
    
    client = get_client()
    db = get_database()
    
    podcast_input = args.podcast
    
    # Find podcast
    pid = client.extract_podcast_id(podcast_input)
    if not pid:
        podcasts = db.get_all_podcasts()
        for p in podcasts:
            if podcast_input.lower() in p.title.lower():
                pid = p.pid
                break
    
    if not pid:
        console.print(f"[red]✗ Could not find podcast: {podcast_input}[/red]")
        return False
    
    podcast = db.get_podcast(pid)
    if not podcast:
        console.print(f"[yellow]Not subscribed to this podcast. Use 'add' first.[/yellow]")
        return False
    
    episodes = db.get_episodes_by_podcast(pid)
    
    if not episodes:
        console.print(f"[yellow]No episodes recorded for: {podcast.title}[/yellow]")
        console.print("Episodes are added when the daemon checks for updates.")
        return
    
    table = Table(title=f"Episodes: {podcast.title}")
    table.add_column("Title", style="cyan", max_width=50)
    table.add_column("Date", style="yellow")
    table.add_column("Status", style="green")
    table.add_column("EID", style="dim")
    
    status_colors = {
        ProcessingStatus.PENDING: "yellow",
        ProcessingStatus.DOWNLOADING: "blue",
        ProcessingStatus.DOWNLOADED: "blue",
        ProcessingStatus.TRANSCRIBING: "blue",
        ProcessingStatus.TRANSCRIBED: "blue",
        ProcessingStatus.SUMMARIZING: "blue",
        ProcessingStatus.COMPLETED: "green",
        ProcessingStatus.FAILED: "red",
    }
    
    for ep in episodes[:args.limit]:
        pub_date = ep.pub_date[:10] if ep.pub_date else ""
        status_color = status_colors.get(ep.status, "white")
        table.add_row(
            ep.title[:50],
            pub_date,
            f"[{status_color}]{ep.status.value}[/{status_color}]",
            ep.eid[:12] + "...",
        )
    
    console.print(table)


def cmd_process(args):
    """Process a specific episode."""
    from xyz_client import get_client
    from database import get_database
    from downloader import get_downloader
    from transcriber import get_transcriber
    from summarizer import get_summarizer
    
    client = get_client()
    db = get_database()
    downloader = get_downloader()
    
    # Support single episode URL
    episode_input = args.episode
    
    console.print(f"\n[bold]Processing episode...[/bold]")
    
    # Get episode from URL
    if "xiaoyuzhoufm.com/episode" in episode_input:
        episode = client.get_episode_by_share_url(episode_input)
    else:
        eid = client.extract_episode_id(episode_input)
        if eid:
            episode = client.get_episode(eid)
        else:
            console.print(f"[red]✗ Could not parse episode: {episode_input}[/red]")
            return False
    
    if not episode:
        console.print("[red]✗ Could not fetch episode details[/red]")
        return False
    
    console.print(f"Episode: [cyan]{episode.title}[/cyan]")
    
    # Auto-subscribe to podcast if episode has a podcast ID
    if episode.pid:
        podcast = db.get_podcast(episode.pid)
        if not podcast:
            # Fetch podcast info and auto-subscribe
            podcast_info = client.get_podcast(episode.pid)
            if podcast_info:
                db.add_podcast(podcast_info.pid, podcast_info.title, podcast_info.author, podcast_info.description)
                console.print(f"[green]+ Auto-subscribed to podcast: {podcast_info.title}[/green]")
                podcast = db.get_podcast(episode.pid)  # Get the newly created record
        
        # Save episode to database
        if podcast:
            db.add_episode(
                eid=episode.eid,
                pid=episode.pid,
                podcast_id=podcast.id,
                title=episode.title,
                description=episode.description,
                duration=episode.duration,
                pub_date=episode.pub_date,
                audio_url=episode.audio_url,
            )
    else:
        console.print("[dim]Note: Could not determine podcast for this episode[/dim]")
    
    # Step 1: Download with progress bar
    console.print("\n[bold]Step 1/3: Downloading audio[/bold]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        download_task = progress.add_task("Downloading...", total=None)
        
        def download_progress(downloaded: int, total: int):
            if total > 0:
                progress.update(download_task, total=total, completed=downloaded)
        
        audio_path = downloader.download(episode, progress_callback=download_progress)
        
    if not audio_path:
        console.print("[red]✗ Download failed[/red]")
        return False
    console.print(f"[green]✓ Downloaded to {audio_path}[/green]")
    
    # Step 2: Check for existing transcript
    console.print("\n[bold]Step 2/3: Transcription[/bold]")
    
    transcriber = get_transcriber()
    
    # First check if we already have a local transcript
    if transcriber.transcript_exists(episode.eid):
        console.print("[green]✓ Found existing local transcript![/green]")
        transcript = transcriber.load_transcript(episode.eid)
    else:
        # Check for transcript on Xiaoyuzhou website
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            check_task = progress.add_task("Checking for transcript on Xiaoyuzhou...", total=None)
            existing_transcript = client.get_episode_transcript(episode_input)
            progress.update(check_task, completed=True)
        
        if existing_transcript and len(existing_transcript) > 500:
            console.print("[green]✓ Found existing transcript on Xiaoyuzhou![/green]")
            # Create transcript object from existing content
            from transcriber import Transcript, TranscriptSegment
            transcript = Transcript(
                episode_id=episode.eid,
                language="zh",
                duration=0,
                text=existing_transcript,
                segments=[TranscriptSegment(start=0, end=0, text=existing_transcript)],
            )
            transcriber.save_transcript(transcript)
        else:
            console.print("No existing transcript found. Generating with Whisper...")
            
            # Get audio file size and estimate duration
            audio_size_mb = audio_path.stat().st_size / (1024 * 1024)
            est_duration_min = audio_size_mb / 1.0  # ~1MB per minute for m4a/mp3
            
            console.print(f"[dim]Audio: {audio_size_mb:.1f} MB (~{est_duration_min:.0f} min)[/dim]")
            console.print("[yellow]Loading model and transcribing... (progress bar from Whisper below)[/yellow]")
            console.print()  # Empty line before whisper's progress
            
            # Run transcription directly - let whisper show its own progress
            transcript = transcriber.transcribe(audio_path, episode.eid)
            
            console.print()  # Empty line after whisper's progress
                
            if not transcript:
                console.print("[red]✗ Transcription failed[/red]")
                return False
            transcriber.save_transcript(transcript)
            console.print("[green]✓ Transcription complete[/green]")
    
    # Step 3: Summarize
    console.print("\n[bold]Step 3/3: Generating summary[/bold]")
    
    summarizer = get_summarizer()
    transcript_len = len(transcript.text)
    console.print(f"[dim]Transcript: {transcript_len:,} characters[/dim]")
    
    # Estimate time: ~1 char of output per 50ms for long transcripts
    if transcript_len > 30000:
        console.print(f"[yellow]Long transcript detected - using chunked processing...[/yellow]")
    
    from rich.live import Live
    from rich.text import Text
    import time
    
    start_time = time.time()
    last_chars = [0]  # Use list to allow modification in closure
    current_chunk = [0, 0]  # [current, total]
    
    def progress_callback(*args):
        """Update progress display."""
        if len(args) == 3:  # Chunked mode: (chars, current_chunk, total_chunks)
            last_chars[0] = args[0]
            current_chunk[0] = args[1]
            current_chunk[1] = args[2]
        else:  # Single mode: just chars
            last_chars[0] = args[0]
    
    with Live(console=console, refresh_per_second=4) as live:
        import threading
        result = [None]
        error = [None]
        
        def run_summarize():
            try:
                result[0] = summarizer.summarize(
                    transcript, 
                    episode_title=episode.title,
                    progress_callback=progress_callback
                )
            except Exception as e:
                error[0] = e
        
        thread = threading.Thread(target=run_summarize)
        thread.start()
        
        while thread.is_alive():
            elapsed = time.time() - start_time
            chars = last_chars[0]
            
            if current_chunk[1] > 0:
                # Chunked mode
                status = Text()
                status.append("⠋ ", style="blue")
                status.append(f"Processing chunk {current_chunk[0]}/{current_chunk[1]}", style="bold")
                status.append(f" | Generated: {chars:,} chars | Elapsed: {elapsed:.0f}s", style="dim")
            else:
                # Single mode or not started
                status = Text()
                status.append("⠋ ", style="blue")
                status.append("Analyzing transcript with LLM...", style="bold")
                if chars > 0:
                    status.append(f" | Generated: {chars:,} chars", style="dim")
                status.append(f" | Elapsed: {elapsed:.0f}s", style="dim")
            
            live.update(status)
            time.sleep(0.25)
        
        thread.join()
        
        if error[0]:
            raise error[0]
        summary = result[0]
        
        elapsed = time.time() - start_time
        live.update(Text(f"✓ LLM analysis complete ({elapsed:.1f}s)", style="green"))
        
    if not summary:
        console.print("[red]✗ Summarization failed[/red]")
        return False
    summary_path = summarizer.save_summary(summary)
    console.print(f"[green]✓ Summary saved to {summary_path}[/green]")
    
    console.print("\n[bold green]Processing complete![/bold green]")
    console.print(f"  Transcript: data/transcripts/{episode.eid}.json")
    console.print(f"  Summary: {summary_path}")
    return True


def cmd_show(args):
    """Show summary for an episode."""
    from database import get_database
    from summarizer import get_summarizer
    from transcriber import get_transcriber
    
    db = get_database()
    summarizer = get_summarizer()
    transcriber = get_transcriber()
    
    # Find episode
    episode = db.get_episode(args.episode)
    if not episode:
        # Try to find by title
        podcasts = db.get_all_podcasts()
        for p in podcasts:
            episodes = db.get_episodes_by_podcast(p.pid)
            for ep in episodes:
                if args.episode.lower() in ep.title.lower():
                    episode = ep
                    break
            if episode:
                break
    
    if not episode:
        console.print(f"[red]✗ Could not find episode: {args.episode}[/red]")
        return False
    
    # Load summary
    summary = summarizer.load_summary(episode.eid)
    
    if not summary:
        console.print(f"[yellow]No summary available for: {episode.title}[/yellow]")
        console.print("Run 'process' to generate a summary.")
        return False
    
    # Display summary
    console.print(Panel(
        f"[bold]{summary.title}[/bold]",
        title="Episode Summary",
    ))
    
    console.print("\n[bold]Overview:[/bold]")
    console.print(summary.overview)
    
    console.print("\n[bold]Topics:[/bold]")
    for topic in summary.topics:
        console.print(f"  • {topic}")
    
    console.print("\n[bold]Key Points:[/bold]")
    for i, kp in enumerate(summary.key_points, 1):
        console.print(f"\n[cyan]{i}. {kp.topic}[/cyan]")
        console.print(f"   {kp.summary}")
        if kp.original_quote:
            console.print(f"   [dim]「{kp.original_quote}」[/dim]")
    
    console.print("\n[bold]Takeaways:[/bold]")
    for takeaway in summary.takeaways:
        console.print(f"  ✓ {takeaway}")
    
    return True


def cmd_view(args):
    """View summary with beautiful formatting."""
    from viewer import (
        load_summary, display_summary_rich, display_summary_compact,
        export_markdown, export_html, list_summaries
    )
    from rich.table import Table
    
    # List mode
    if args.list or not args.episode_id:
        summaries = list_summaries()
        
        if not summaries:
            console.print("[yellow]No summaries found.[/yellow]")
            console.print("Run 'process <episode_url>' to generate summaries.")
            return False
        
        table = Table(title="📚 Available Summaries", box=box.ROUNDED)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Title", style="white")
        table.add_column("Topics", justify="center")
        table.add_column("Key Points", justify="center")
        
        for s in summaries:
            # Truncate title if too long
            title = s["title"][:60] + "..." if len(s["title"]) > 60 else s["title"]
            table.add_row(
                s["id"],
                title,
                str(s["topics_count"]),
                str(s["key_points_count"]),
            )
        
        console.print(table)
        console.print("\n[dim]Use 'view <episode_id>' to view a specific summary[/dim]")
        return True
    
    # Load summary
    summary = load_summary(args.episode_id)
    
    if not summary:
        console.print(f"[red]✗ Summary not found: {args.episode_id}[/red]")
        console.print("[dim]Use 'view --list' to see available summaries[/dim]")
        return False
    
    # Terminal output
    if args.format == "terminal":
        if args.compact:
            display_summary_compact(summary, console)
        else:
            display_summary_rich(summary, console)
        return True
    
    # Markdown output
    elif args.format == "markdown":
        md_content = export_markdown(summary)
        
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(md_content, encoding="utf-8")
            console.print(f"[green]✓ Saved to {output_path}[/green]")
        else:
            # Print to terminal
            console.print(Markdown(md_content))
        return True
    
    # HTML output
    elif args.format == "html":
        html_content = export_html(summary)
        
        if args.output:
            output_path = Path(args.output)
        else:
            output_path = Path(f"data/summaries/{args.episode_id}.html")
        
        output_path.write_text(html_content, encoding="utf-8")
        console.print(f"[green]✓ Saved to {output_path}[/green]")
        
        # Try to open in browser
        import webbrowser
        try:
            webbrowser.open(f"file://{output_path.absolute()}")
            console.print("[dim]Opened in browser[/dim]")
        except:
            pass
        
        return True


def cmd_batch(args):
    """Batch process all episodes from a podcast."""
    from xyz_client import get_client
    from database import get_database
    from downloader import get_downloader
    from transcriber import get_transcriber
    from summarizer import get_summarizer
    
    client = get_client()
    
    console.print(f"[bold]Fetching episodes from podcast...[/bold]")
    
    # Get podcast info and episodes from URL
    podcast_url = args.podcast
    
    # Use get_podcast_by_url for full URLs, get_podcast for IDs
    if podcast_url.startswith("http"):
        podcast = client.get_podcast_by_url(podcast_url)
        # Extract pid from URL
        pid = client._extract_id_from_url(podcast_url, "podcast")
    else:
        pid = podcast_url
        podcast = client.get_podcast(pid)
    
    if not podcast:
        console.print(f"[red]✗ Could not fetch podcast from: {podcast_url}[/red]")
        return False
    
    console.print(f"[green]✓ Found podcast: {podcast.title}[/green]")
    console.print(f"[dim]  Episodes available: {podcast.episode_count}[/dim]")
    
    # Fetch all episodes using the extracted pid
    episodes = client.get_episodes_from_page(pid or podcast.pid, limit=args.limit or 100)
    
    if not episodes:
        console.print(f"[red]✗ No episodes found[/red]")
        return False
    
    console.print(f"\n[bold]Found {len(episodes)} episodes to process[/bold]")
    
    # List episodes
    from rich.table import Table
    table = Table(title="Episodes to Process", box=box.SIMPLE)
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", style="cyan", max_width=60)
    table.add_column("Duration", justify="right")
    table.add_column("EID", style="dim")
    
    for i, ep in enumerate(episodes, 1):
        duration_min = ep.duration // 60
        table.add_row(
            str(i),
            ep.title[:58] + ("..." if len(ep.title) > 58 else ""),
            f"{duration_min}min",
            ep.eid[:12] + "...",
        )
    
    console.print(table)
    
    # Ask for confirmation unless --yes flag
    if not args.yes:
        console.print(f"\n[yellow]Warning: This will process {len(episodes)} episodes.[/yellow]")
        console.print("[dim]Each episode may take several minutes (transcription + LLM).[/dim]")
        confirm = input("\nProceed? [y/N]: ").strip().lower()
        if confirm != 'y':
            console.print("[yellow]Cancelled.[/yellow]")
            return False
    
    # Process each episode
    transcriber = get_transcriber()
    summarizer = get_summarizer()
    downloader = get_downloader()
    
    success_count = 0
    skip_count = 0
    fail_count = 0
    
    for i, episode in enumerate(episodes, 1):
        console.print(f"\n[bold]{'='*60}[/bold]")
        console.print(f"[bold cyan]Processing {i}/{len(episodes)}: {episode.title[:50]}...[/bold cyan]")
        console.print(f"[bold]{'='*60}[/bold]")
        
        # Check if already processed
        if args.skip_existing:
            existing_summary = summarizer.load_summary(episode.eid)
            if existing_summary:
                console.print(f"[yellow]⏭ Skipping (already has summary)[/yellow]")
                skip_count += 1
                continue
        
        try:
            # Step 1: Download
            console.print("\n[bold]Step 1/3: Downloading audio[/bold]")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                download_task = progress.add_task("Downloading...", total=None)
                
                def download_progress(downloaded, total):
                    progress.update(download_task, total=total, completed=downloaded)
                
                audio_path = downloader.download(episode, progress_callback=download_progress)
            
            if not audio_path:
                console.print("[red]✗ Download failed[/red]")
                fail_count += 1
                continue
            console.print(f"[green]✓ Downloaded[/green]")
            
            # Step 2: Transcribe
            console.print("\n[bold]Step 2/3: Transcription[/bold]")
            
            if transcriber.transcript_exists(episode.eid):
                console.print("[green]✓ Using existing transcript[/green]")
                transcript = transcriber.load_transcript(episode.eid)
            else:
                console.print("[yellow]Generating transcript with Whisper...[/yellow]")
                transcript = transcriber.transcribe(audio_path, episode.eid)
                if transcript:
                    transcriber.save_transcript(transcript)
                    console.print("[green]✓ Transcription complete[/green]")
            
            if not transcript:
                console.print("[red]✗ Transcription failed[/red]")
                fail_count += 1
                continue
            
            # Step 3: Summarize (skip if --transcribe-only)
            if args.transcribe_only:
                console.print("\n[dim]Skipping summarization (--transcribe-only)[/dim]")
                success_count += 1
                continue
            
            console.print("\n[bold]Step 3/3: Generating summary[/bold]")
            
            existing_summary = summarizer.load_summary(episode.eid)
            if existing_summary and not args.force:
                console.print("[green]✓ Using existing summary[/green]")
            else:
                summary = summarizer.summarize(transcript, episode_title=episode.title)
                if summary:
                    summarizer.save_summary(summary)
                    console.print("[green]✓ Summary generated[/green]")
                else:
                    console.print("[red]✗ Summary failed[/red]")
                    fail_count += 1
                    continue
            
            success_count += 1
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted by user[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]✗ Error: {e}[/red]")
            fail_count += 1
            continue
    
    # Final summary
    console.print(f"\n[bold]{'='*60}[/bold]")
    console.print("[bold]Batch Processing Complete![/bold]")
    console.print(f"  ✓ Success: {success_count}")
    console.print(f"  ⏭ Skipped: {skip_count}")
    console.print(f"  ✗ Failed: {fail_count}")
    console.print(f"\nView summaries with: python main.py view --list")
    
    return True


def cmd_start(args):
    """Start the background daemon."""
    from daemon import PodcastDaemon
    
    if PodcastDaemon.is_running():
        pid = PodcastDaemon.get_pid()
        console.print(f"[yellow]Daemon is already running (PID: {pid})[/yellow]")
        return False
    
    console.print("[bold]Starting daemon...[/bold]")
    
    daemon = PodcastDaemon()
    
    if args.foreground:
        # Run in foreground (blocking)
        daemon.start(daemonize=False)
    else:
        # Start daemon threads
        daemon.start(daemonize=True)
        console.print("[green]✓ Daemon started in background[/green]")
        console.print("Use 'status' to check status, 'stop' to stop.")
        
        # Keep main thread alive
        try:
            while daemon._running:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            daemon.stop()
    
    return True


def cmd_stop(args):
    """Stop the background daemon."""
    from daemon import PodcastDaemon
    from config import PID_FILE
    
    if not PodcastDaemon.is_running():
        console.print("[yellow]Daemon is not running[/yellow]")
        return True
    
    pid = PodcastDaemon.get_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            console.print(f"[green]✓ Sent stop signal to daemon (PID: {pid})[/green]")
        except OSError as e:
            console.print(f"[red]✗ Could not stop daemon: {e}[/red]")
            # Clean up stale PID file
            if PID_FILE.exists():
                PID_FILE.unlink()
            return False
    
    return True


def cmd_status(args):
    """Show daemon status."""
    from daemon import PodcastDaemon
    from database import get_database
    
    db = get_database()
    stats = db.get_stats()
    
    # Daemon status
    if PodcastDaemon.is_running():
        pid = PodcastDaemon.get_pid()
        console.print(f"[green]● Daemon running[/green] (PID: {pid})")
    else:
        console.print("[yellow]○ Daemon not running[/yellow]")
    
    # Database stats
    console.print(f"\n[bold]Statistics:[/bold]")
    console.print(f"  Podcasts: {stats['podcasts']}")
    console.print(f"  Episodes: {stats['episodes']}")
    
    if stats['status_counts']:
        console.print("\n[bold]Episode Status:[/bold]")
        for status, count in stats['status_counts'].items():
            console.print(f"  {status}: {count}")


def cmd_organize(args):
    """Organize orphaned episodes into their correct podcast folders."""
    import shutil
    from xyz_client import get_client
    from database import get_database
    from config import DATA_DIR
    
    client = get_client()
    db = get_database()
    
    unknown_dir = DATA_DIR / "audio" / "unknown"
    
    if not unknown_dir.exists():
        console.print("[green]No orphaned episodes found.[/green]")
        return True
    
    # Find all audio files in unknown folder
    audio_files = list(unknown_dir.glob("*.m4a")) + list(unknown_dir.glob("*.mp3"))
    
    if not audio_files:
        console.print("[green]No orphaned episodes found.[/green]")
        return True
    
    console.print(f"[bold]Found {len(audio_files)} orphaned episode(s)[/bold]")
    console.print()
    
    moved_count = 0
    failed_count = 0
    
    for audio_file in audio_files:
        eid = audio_file.stem  # Get filename without extension
        console.print(f"Processing: [cyan]{eid}[/cyan]")
        
        # Fetch episode info to get podcast ID
        episode = client.get_episode(eid)
        
        if not episode:
            console.print(f"  [red]✗ Could not fetch episode info[/red]")
            failed_count += 1
            continue
        
        if not episode.pid:
            console.print(f"  [yellow]⚠ Could not determine podcast ID[/yellow]")
            failed_count += 1
            continue
        
        # Get or create podcast
        podcast = db.get_podcast(episode.pid)
        if not podcast:
            podcast_info = client.get_podcast(episode.pid)
            if podcast_info:
                db.add_podcast(podcast_info.pid, podcast_info.title, podcast_info.author, podcast_info.description)
                console.print(f"  [green]+ Auto-subscribed to: {podcast_info.title}[/green]")
                podcast = db.get_podcast(episode.pid)  # Get the newly created record
        
        # Save episode to database
        if podcast:
            db.add_episode(
                eid=episode.eid,
                pid=episode.pid,
                podcast_id=podcast.id,
                title=episode.title,
                description=episode.description,
                duration=episode.duration,
                pub_date=episode.pub_date,
                audio_url=episode.audio_url,
            )
        
        # Move file to correct podcast folder
        target_dir = DATA_DIR / "audio" / episode.pid
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / audio_file.name
        
        if target_file.exists():
            console.print(f"  [yellow]⚠ File already exists in target folder, removing duplicate[/yellow]")
            audio_file.unlink()
        else:
            shutil.move(str(audio_file), str(target_file))
            console.print(f"  [green]✓ Moved to {episode.pid}/[/green]")
        
        if podcast:
            console.print(f"  [dim]Podcast: {podcast.title}[/dim]")
        
        moved_count += 1
    
    console.print()
    console.print(f"[bold]Organization complete![/bold]")
    console.print(f"  ✓ Organized: {moved_count}")
    console.print(f"  ✗ Failed: {failed_count}")
    
    # Clean up empty unknown folder
    if unknown_dir.exists() and not any(unknown_dir.iterdir()):
        unknown_dir.rmdir()
        console.print("[dim]Removed empty 'unknown' folder[/dim]")
    
    return True


def cmd_check_data(args):
    """Check data integrity and optionally fix issues."""
    from xyz_client import get_client
    from database import get_database
    from config import DATA_DIR
    
    client = get_client()
    db = get_database()
    
    console.print("[bold]Data Integrity Check[/bold]\n")
    
    issues = []
    
    # 1. Scan audio files
    audio_dir = DATA_DIR / "audio"
    audio_files = {}  # eid -> (pid, path)
    
    if audio_dir.exists():
        for podcast_dir in audio_dir.iterdir():
            if podcast_dir.is_dir():
                pid = podcast_dir.name
                for audio_file in podcast_dir.glob("*.m4a"):
                    eid = audio_file.stem
                    audio_files[eid] = (pid, audio_file)
                for audio_file in podcast_dir.glob("*.mp3"):
                    eid = audio_file.stem
                    audio_files[eid] = (pid, audio_file)
    
    console.print(f"[bold]Audio files:[/bold] {len(audio_files)} found")
    
    # 2. Scan transcripts
    transcript_dir = DATA_DIR / "transcripts"
    transcripts = set()
    if transcript_dir.exists():
        for f in transcript_dir.glob("*.json"):
            transcripts.add(f.stem)
    
    console.print(f"[bold]Transcripts:[/bold] {len(transcripts)} found")
    
    # 3. Scan summaries
    summary_dir = DATA_DIR / "summaries"
    summaries = set()
    if summary_dir.exists():
        for f in summary_dir.glob("*.json"):
            summaries.add(f.stem)
    
    console.print(f"[bold]Summaries:[/bold] {len(summaries)} found")
    
    # 4. Get database records
    all_podcasts = db.get_all_podcasts()
    podcast_map = {p.pid: p for p in all_podcasts}
    
    console.print(f"[bold]Podcasts in DB:[/bold] {len(all_podcasts)}")
    
    # Get all episodes from database
    db_episodes = {}
    for podcast in all_podcasts:
        episodes = db.get_episodes_by_podcast(podcast.pid)
        for ep in episodes:
            db_episodes[ep.eid] = ep
    
    console.print(f"[bold]Episodes in DB:[/bold] {len(db_episodes)}")
    console.print()
    
    # 5. Check for issues
    console.print("[bold]Checking for issues...[/bold]\n")
    
    # 5a. Audio files without DB records
    audio_without_db = []
    for eid, (pid, path) in audio_files.items():
        if eid not in db_episodes:
            audio_without_db.append((eid, pid, path))
            issues.append(("missing_db_record", eid, pid))
    
    if audio_without_db:
        console.print(f"[yellow]⚠ {len(audio_without_db)} audio file(s) not in database:[/yellow]")
        for eid, pid, path in audio_without_db:
            console.print(f"  - {eid} (in {pid}/)")
        console.print()
    
    # 5b. Audio files without transcripts
    audio_without_transcript = []
    for eid in audio_files:
        if eid not in transcripts:
            audio_without_transcript.append(eid)
            issues.append(("missing_transcript", eid, None))
    
    if audio_without_transcript:
        console.print(f"[yellow]⚠ {len(audio_without_transcript)} audio file(s) without transcripts:[/yellow]")
        for eid in audio_without_transcript:
            console.print(f"  - {eid}")
        console.print()
    
    # 5c. Transcripts without summaries
    transcript_without_summary = []
    for eid in transcripts:
        if eid not in summaries:
            transcript_without_summary.append(eid)
            issues.append(("missing_summary", eid, None))
    
    if transcript_without_summary:
        console.print(f"[yellow]⚠ {len(transcript_without_summary)} transcript(s) without summaries:[/yellow]")
        for eid in transcript_without_summary:
            console.print(f"  - {eid}")
        console.print()
    
    # 5d. DB records without audio files
    db_without_audio = []
    for eid, ep in db_episodes.items():
        if eid not in audio_files:
            db_without_audio.append((eid, ep.title))
            issues.append(("orphan_db_record", eid, None))
    
    if db_without_audio:
        console.print(f"[yellow]⚠ {len(db_without_audio)} DB record(s) without audio files:[/yellow]")
        for eid, title in db_without_audio:
            console.print(f"  - {eid}: {title[:50]}...")
        console.print()
    
    # 5e. Check for corrupted episode records (title contains description patterns)
    corrupted_records = []
    for eid, ep in db_episodes.items():
        # Check if title looks like a description (too long or contains certain patterns)
        if len(ep.title) > 200 or "欢迎" in ep.title or "订阅" in ep.title:
            corrupted_records.append((eid, ep.title[:80]))
            issues.append(("corrupted_record", eid, None))
    
    if corrupted_records:
        console.print(f"[red]✗ {len(corrupted_records)} corrupted episode record(s):[/red]")
        for eid, title in corrupted_records:
            console.print(f"  - {eid}: {title}...")
        console.print()
    
    # Summary
    if not issues:
        console.print("[green]✓ No issues found! Data is consistent.[/green]")
        return True
    
    console.print(f"[bold]Total issues: {len(issues)}[/bold]\n")
    
    # Fix issues if requested
    if args.fix:
        console.print("[bold]Fixing issues...[/bold]\n")
        fixed_count = 0
        
        # Fix missing DB records
        for issue_type, eid, pid in issues:
            if issue_type == "missing_db_record":
                console.print(f"Fixing: {eid}")
                episode = client.get_episode(eid)
                if episode:
                    # Get or create podcast
                    podcast = db.get_podcast(episode.pid) if episode.pid else None
                    if not podcast and episode.pid:
                        podcast_info = client.get_podcast(episode.pid)
                        if podcast_info:
                            db.add_podcast(podcast_info.pid, podcast_info.title, 
                                         podcast_info.author, podcast_info.description)
                            console.print(f"  [green]+ Added podcast: {podcast_info.title}[/green]")
                            podcast = db.get_podcast(episode.pid)
                    
                    if podcast:
                        db.add_episode(
                            eid=episode.eid,
                            pid=episode.pid,
                            podcast_id=podcast.id,
                            title=episode.title,
                            description=episode.description,
                            duration=episode.duration,
                            pub_date=episode.pub_date,
                            audio_url=episode.audio_url,
                        )
                        console.print(f"  [green]+ Added episode: {episode.title[:50]}...[/green]")
                        fixed_count += 1
                    else:
                        console.print(f"  [red]✗ Could not add (no podcast)[/red]")
                else:
                    console.print(f"  [red]✗ Could not fetch episode info[/red]")
            
            elif issue_type == "corrupted_record":
                console.print(f"Fixing corrupted record: {eid}")
                episode = client.get_episode(eid)
                if episode:
                    # Delete and re-add with correct data
                    podcast = db.get_podcast(episode.pid) if episode.pid else None
                    if podcast:
                        db.delete_episode(eid)
                        db.add_episode(
                            eid=episode.eid,
                            pid=episode.pid,
                            podcast_id=podcast.id,
                            title=episode.title,
                            description=episode.description,
                            duration=episode.duration,
                            pub_date=episode.pub_date,
                            audio_url=episode.audio_url,
                        )
                        console.print(f"  [green]+ Fixed: {episode.title[:50]}...[/green]")
                        fixed_count += 1
                    else:
                        console.print(f"  [red]✗ Could not fix (podcast not found)[/red]")
                else:
                    console.print(f"  [red]✗ Could not fetch episode info[/red]")
        
        console.print(f"\n[bold]Fixed {fixed_count} issue(s)[/bold]")
    else:
        console.print("[dim]Run with --fix to attempt automatic fixes[/dim]")
    
    return True


def cmd_serve(args):
    """Start the web app (API + optional frontend dev server)."""
    import subprocess
    import threading
    import socket
    
    def find_available_port(start_port=8000):
        """Find an available port starting from start_port."""
        port = start_port
        while port < 65535:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('', port))
                    return port
            except OSError:
                port += 1
        return start_port
    
    port = find_available_port(args.port)
    
    console.print(Panel(
        "[bold]Starting Podcast Transcript Web App[/bold]\n\n"
        f"API Server: http://localhost:{port}\n"
        f"API Docs:   http://localhost:{port}/docs\n"
        + ("" if args.api_only else "Frontend:   http://localhost:5173"),
        title="Web App",
        border_style="green",
    ))
    
    # Start frontend dev server in background (if not api-only)
    frontend_process = None
    if not args.api_only:
        web_dir = Path(__file__).parent / "web"
        if (web_dir / "node_modules").exists():
            console.print("[dim]Starting frontend dev server...[/dim]")
            # Pass API port to vite via environment variable
            env = os.environ.copy()
            env["VITE_API_PORT"] = str(port)
            frontend_process = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=str(web_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
        else:
            console.print("[yellow]Frontend not installed. Run: cd web && npm install[/yellow]")
    
    # Start API server
    try:
        import uvicorn
        console.print(f"[green]✓ API server starting on port {port}...[/green]")
        uvicorn.run(
            "api.main:app",
            host="0.0.0.0",
            port=port,
            reload=True,
            log_level="info",
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
    finally:
        if frontend_process:
            frontend_process.terminate()
            frontend_process.wait()
    
    return True


def cmd_check(args):
    """Manually check for new episodes."""
    from daemon import get_daemon
    
    console.print("[bold]Checking for new episodes...[/bold]")
    
    daemon = get_daemon()
    daemon.check_podcasts()
    
    console.print("[green]✓ Check complete[/green]")
    return True


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="xyz",
        description="Xiaoyuzhou Podcast Transcript & Summary Tool",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # add
    add_parser = subparsers.add_parser("add", help="Subscribe to a podcast")
    add_parser.add_argument("podcast", help="Podcast URL (e.g., https://www.xiaoyuzhoufm.com/podcast/xxx)")
    add_parser.set_defaults(func=cmd_add)
    
    # remove
    remove_parser = subparsers.add_parser("remove", help="Unsubscribe from a podcast")
    remove_parser.add_argument("podcast", help="Podcast name or ID")
    remove_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    remove_parser.set_defaults(func=cmd_remove)
    
    # list
    list_parser = subparsers.add_parser("list", help="List subscribed podcasts")
    list_parser.set_defaults(func=cmd_list)
    
    # episodes
    episodes_parser = subparsers.add_parser("episodes", help="List episodes for a podcast")
    episodes_parser.add_argument("podcast", help="Podcast name or ID")
    episodes_parser.add_argument("-n", "--limit", type=int, default=20, help="Number of episodes to show")
    episodes_parser.set_defaults(func=cmd_episodes)
    
    # process
    process_parser = subparsers.add_parser("process", help="Process a specific episode")
    process_parser.add_argument("episode", help="Episode URL (e.g., https://www.xiaoyuzhoufm.com/episode/xxx)")
    process_parser.set_defaults(func=cmd_process)
    
    # show (legacy)
    show_parser = subparsers.add_parser("show", help="Show summary for an episode")
    show_parser.add_argument("episode", help="Episode title or ID")
    show_parser.set_defaults(func=cmd_show)
    
    # view (enhanced viewer)
    view_parser = subparsers.add_parser("view", help="View summary with beautiful formatting")
    view_parser.add_argument("episode_id", nargs="?", help="Episode ID (optional, lists all if not provided)")
    view_parser.add_argument("-f", "--format", choices=["terminal", "markdown", "html"], default="terminal",
                            help="Output format (default: terminal)")
    view_parser.add_argument("-o", "--output", help="Output file path (for markdown/html)")
    view_parser.add_argument("-c", "--compact", action="store_true", help="Compact view (terminal only)")
    view_parser.add_argument("-l", "--list", action="store_true", help="List all available summaries")
    view_parser.set_defaults(func=cmd_view)
    
    # batch (process all episodes from a podcast)
    batch_parser = subparsers.add_parser("batch", help="Batch process all episodes from a podcast")
    batch_parser.add_argument("podcast", help="Podcast URL")
    batch_parser.add_argument("-n", "--limit", type=int, help="Max episodes to process")
    batch_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    batch_parser.add_argument("--skip-existing", action="store_true", help="Skip episodes with existing summaries")
    batch_parser.add_argument("--transcribe-only", action="store_true", help="Only transcribe, don't summarize")
    batch_parser.add_argument("--force", action="store_true", help="Regenerate even if exists")
    batch_parser.set_defaults(func=cmd_batch)
    
    # start
    start_parser = subparsers.add_parser("start", help="Start background daemon")
    start_parser.add_argument("-f", "--foreground", action="store_true", help="Run in foreground")
    start_parser.set_defaults(func=cmd_start)
    
    # stop
    stop_parser = subparsers.add_parser("stop", help="Stop background daemon")
    stop_parser.set_defaults(func=cmd_stop)
    
    # status
    status_parser = subparsers.add_parser("status", help="Show daemon status")
    status_parser.set_defaults(func=cmd_status)
    
    # check
    check_parser = subparsers.add_parser("check", help="Check for new episodes now")
    check_parser.set_defaults(func=cmd_check)
    
    # serve (web app)
    serve_parser = subparsers.add_parser("serve", help="Start web app (API + frontend)")
    serve_parser.add_argument("--api-only", action="store_true", help="Only start API server")
    serve_parser.add_argument("--port", type=int, default=8000, help="API port (default: 8000)")
    serve_parser.set_defaults(func=cmd_serve)
    
    # organize (move orphaned episodes to correct podcast folders)
    organize_parser = subparsers.add_parser("organize", help="Organize orphaned episodes into podcast folders")
    organize_parser.set_defaults(func=cmd_organize)
    
    # check-data (data integrity check)
    check_data_parser = subparsers.add_parser("check-data", help="Check data integrity and consistency")
    check_data_parser.add_argument("--fix", action="store_true", help="Attempt to fix issues automatically")
    check_data_parser.set_defaults(func=cmd_check_data)
    
    return parser


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        result = args.func(args)
        return 0 if result is not False else 1
    except KeyboardInterrupt:
        console.print("\nInterrupted.")
        return 130
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
