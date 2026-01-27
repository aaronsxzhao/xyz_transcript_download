#!/usr/bin/env python3
"""
Xiaoyuzhou Podcast Transcript & Summary Tool

A tool to download podcasts from 小宇宙 (Xiaoyuzhou), generate transcripts
using OpenAI Whisper, and summarize them using GPT-4.

Usage:
    python main.py auth          # Extract tokens from browser
    python main.py add <podcast> # Subscribe to a podcast
    python main.py list          # List subscribed podcasts
    python main.py process <podcast> <episode>  # Process an episode
    python main.py start         # Start background daemon
    python main.py status        # Show daemon status
"""

from cli import main

if __name__ == "__main__":
    exit(main())
