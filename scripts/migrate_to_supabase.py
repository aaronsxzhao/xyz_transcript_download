#!/usr/bin/env python3
"""
Migration script: Migrate local SQLite data to Supabase for a specific user.

This script migrates:
- Missing podcasts
- Missing episodes
- All transcripts (from JSON files)
- All summaries (from JSON files)

Usage:
    python scripts/migrate_to_supabase.py
"""

import os
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

# Configuration
USER_ID = "800a86dd-a1b8-4322-8212-a3dcf13f8806"  # vincentjyzhao@gmail.com
USER_EMAIL = "vincentjyzhao@gmail.com"

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
SQLITE_DB = DATA_DIR / "xyz.db"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
SUMMARIES_DIR = DATA_DIR / "summaries"


def get_supabase_client():
    """Create Supabase client with service key for admin access."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
    
    return create_client(url, key)


def get_local_podcasts():
    """Get all podcasts from local SQLite."""
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM podcasts")
    podcasts = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return podcasts


def get_local_episodes():
    """Get all episodes from local SQLite."""
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM episodes")
    episodes = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return episodes


def get_supabase_podcasts(client, user_id: str):
    """Get all podcasts from Supabase for user."""
    result = client.table("podcasts").select("*").eq("user_id", user_id).execute()
    return {p["pid"]: p for p in result.data}


def get_supabase_episodes(client, user_id: str):
    """Get all episodes from Supabase for user."""
    result = client.table("episodes").select("*").eq("user_id", user_id).execute()
    return {e["eid"]: e for e in result.data}


def migrate_podcasts(client, user_id: str):
    """Migrate missing podcasts to Supabase."""
    print("\n📚 Migrating Podcasts...")
    
    local_podcasts = get_local_podcasts()
    supabase_podcasts = get_supabase_podcasts(client, user_id)
    
    migrated = 0
    skipped = 0
    
    for podcast in local_podcasts:
        pid = podcast["pid"]
        
        if pid in supabase_podcasts:
            print(f"  ⏭️  Skip (exists): {podcast['title']}")
            skipped += 1
            continue
        
        # Insert new podcast
        result = client.table("podcasts").insert({
            "user_id": user_id,
            "pid": pid,
            "title": podcast["title"],
            "author": podcast.get("author", ""),
            "description": podcast.get("description", ""),
            "cover_url": podcast.get("cover_url", ""),
        }).execute()
        
        if result.data:
            print(f"  ✅ Migrated: {podcast['title']}")
            migrated += 1
        else:
            print(f"  ❌ Failed: {podcast['title']}")
    
    print(f"\n  Podcasts: {migrated} migrated, {skipped} skipped")
    return migrated


def migrate_episodes(client, user_id: str):
    """Migrate missing episodes to Supabase."""
    print("\n🎙️  Migrating Episodes...")
    
    local_episodes = get_local_episodes()
    supabase_episodes = get_supabase_episodes(client, user_id)
    supabase_podcasts = get_supabase_podcasts(client, user_id)
    
    migrated = 0
    skipped = 0
    failed = 0
    
    for episode in local_episodes:
        eid = episode["eid"]
        pid = episode["pid"]
        
        if eid in supabase_episodes:
            print(f"  ⏭️  Skip (exists): {episode['title'][:40]}...")
            skipped += 1
            continue
        
        # Find podcast_id in Supabase
        if pid not in supabase_podcasts:
            print(f"  ❌ Podcast not found for: {episode['title'][:40]}...")
            failed += 1
            continue
        
        podcast_id = supabase_podcasts[pid]["id"]
        
        # Insert new episode
        result = client.table("episodes").insert({
            "user_id": user_id,
            "podcast_id": podcast_id,
            "eid": eid,
            "pid": pid,
            "title": episode["title"],
            "description": episode.get("description", ""),
            "duration": episode.get("duration", 0),
            "pub_date": episode.get("pub_date", ""),
            "audio_url": episode.get("audio_url", ""),
            "status": episode.get("status", "pending"),
        }).execute()
        
        if result.data:
            print(f"  ✅ Migrated: {episode['title'][:40]}...")
            migrated += 1
        else:
            print(f"  ❌ Failed: {episode['title'][:40]}...")
            failed += 1
    
    print(f"\n  Episodes: {migrated} migrated, {skipped} skipped, {failed} failed")
    return migrated


def migrate_transcripts(client, user_id: str):
    """Migrate all transcripts from JSON files to Supabase."""
    print("\n📝 Migrating Transcripts...")
    
    if not TRANSCRIPTS_DIR.exists():
        print("  No transcripts directory found")
        return 0
    
    transcript_files = list(TRANSCRIPTS_DIR.glob("*.json"))
    
    migrated = 0
    skipped = 0
    failed = 0
    
    for tf in transcript_files:
        episode_id = tf.stem
        
        # Check if already exists
        result = client.table("transcripts").select("id").eq("user_id", user_id).eq("episode_id", episode_id).execute()
        if result.data:
            print(f"  ⏭️  Skip (exists): {episode_id}")
            skipped += 1
            continue
        
        # Load transcript data
        try:
            with open(tf, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  ❌ Failed to read: {tf.name} - {e}")
            failed += 1
            continue
        
        # Insert transcript
        try:
            result = client.table("transcripts").insert({
                "user_id": user_id,
                "episode_id": episode_id,
                "language": data.get("language", "zh"),
                "duration": data.get("duration", 0),
                "text": data.get("text", ""),
            }).execute()
            
            if not result.data:
                print(f"  ❌ Failed to insert: {episode_id}")
                failed += 1
                continue
            
            transcript_id = result.data[0]["id"]
            
            # Insert segments
            segments = data.get("segments", [])
            if segments:
                segment_rows = [
                    {
                        "transcript_id": transcript_id,
                        "start_time": seg.get("start", 0),
                        "end_time": seg.get("end", 0),
                        "text": seg.get("text", ""),
                    }
                    for seg in segments
                ]
                # Insert in batches of 500 to avoid timeout
                batch_size = 500
                for i in range(0, len(segment_rows), batch_size):
                    batch = segment_rows[i:i + batch_size]
                    client.table("transcript_segments").insert(batch).execute()
            
            print(f"  ✅ Migrated: {episode_id} ({len(segments)} segments)")
            migrated += 1
            
        except Exception as e:
            print(f"  ❌ Failed: {episode_id} - {e}")
            failed += 1
    
    print(f"\n  Transcripts: {migrated} migrated, {skipped} skipped, {failed} failed")
    return migrated


def migrate_summaries(client, user_id: str):
    """Migrate all summaries from JSON files to Supabase."""
    print("\n📊 Migrating Summaries...")
    
    if not SUMMARIES_DIR.exists():
        print("  No summaries directory found")
        return 0
    
    summary_files = [f for f in SUMMARIES_DIR.glob("*.json") if f.stem != ".DS_Store"]
    
    migrated = 0
    skipped = 0
    failed = 0
    
    for sf in summary_files:
        episode_id = sf.stem
        
        # Skip .DS_Store or other non-episode files
        if episode_id.startswith("."):
            continue
        
        # Check if already exists
        result = client.table("summaries").select("id").eq("user_id", user_id).eq("episode_id", episode_id).execute()
        if result.data:
            print(f"  ⏭️  Skip (exists): {episode_id}")
            skipped += 1
            continue
        
        # Load summary data
        try:
            with open(sf, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  ❌ Failed to read: {sf.name} - {e}")
            failed += 1
            continue
        
        # Insert summary
        try:
            result = client.table("summaries").insert({
                "user_id": user_id,
                "episode_id": episode_id,
                "title": data.get("title", ""),
                "overview": data.get("overview", ""),
                "topics": data.get("topics", []),
                "takeaways": data.get("takeaways", []),
            }).execute()
            
            if not result.data:
                print(f"  ❌ Failed to insert: {episode_id}")
                failed += 1
                continue
            
            summary_id = result.data[0]["id"]
            
            # Insert key points
            key_points = data.get("key_points", [])
            if key_points:
                kp_rows = [
                    {
                        "summary_id": summary_id,
                        "topic": kp.get("topic", ""),
                        "summary": kp.get("summary", ""),
                        "original_quote": kp.get("original_quote", ""),
                        "timestamp": kp.get("timestamp", ""),
                    }
                    for kp in key_points
                ]
                client.table("summary_key_points").insert(kp_rows).execute()
            
            print(f"  ✅ Migrated: {episode_id} ({len(key_points)} key points)")
            migrated += 1
            
        except Exception as e:
            print(f"  ❌ Failed: {episode_id} - {e}")
            failed += 1
    
    print(f"\n  Summaries: {migrated} migrated, {skipped} skipped, {failed} failed")
    return migrated


def main():
    print("=" * 60)
    print("🔄 SQLite to Supabase Migration")
    print(f"   User: {USER_EMAIL}")
    print(f"   User ID: {USER_ID}")
    print("=" * 60)
    
    # Check files exist
    if not SQLITE_DB.exists():
        print(f"\n❌ SQLite database not found: {SQLITE_DB}")
        return 1
    
    # Connect to Supabase
    try:
        client = get_supabase_client()
        print("\n✅ Connected to Supabase")
    except Exception as e:
        print(f"\n❌ Failed to connect to Supabase: {e}")
        return 1
    
    # Run migrations
    podcasts_migrated = migrate_podcasts(client, USER_ID)
    
    # Refresh podcast cache after migration
    if podcasts_migrated > 0:
        # Re-fetch to get new podcast IDs
        pass
    
    episodes_migrated = migrate_episodes(client, USER_ID)
    transcripts_migrated = migrate_transcripts(client, USER_ID)
    summaries_migrated = migrate_summaries(client, USER_ID)
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 Migration Summary")
    print("=" * 60)
    print(f"   Podcasts migrated:   {podcasts_migrated}")
    print(f"   Episodes migrated:   {episodes_migrated}")
    print(f"   Transcripts migrated: {transcripts_migrated}")
    print(f"   Summaries migrated:  {summaries_migrated}")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
