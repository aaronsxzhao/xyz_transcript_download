#!/usr/bin/env python3
"""Check transcript vs episode durations for a user."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL and SUPABASE_KEY must be set")
    sys.exit(1)

client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Find user by email
email = sys.argv[1] if len(sys.argv) > 1 else "aaronsxzhao@gmail.com"
print(f"Looking up user: {email}\n")

# Get user_id from auth (if using Supabase auth) or from any table
# Try to find user_id from episodes table
episodes_result = client.table("episodes").select("user_id").limit(1).execute()
if not episodes_result.data:
    print("No episodes found in database")
    sys.exit(1)

# Get unique user_ids
all_episodes = client.table("episodes").select("user_id, eid, title, duration").execute()
user_ids = set(ep["user_id"] for ep in all_episodes.data)
print(f"Found {len(user_ids)} user(s) in database\n")

for user_id in user_ids:
    print(f"=== User ID: {user_id} ===\n")
    
    # Get transcripts
    transcripts = client.table("transcripts").select("id, episode_id, duration").eq("user_id", user_id).execute()
    
    if not transcripts.data:
        print("  No transcripts found\n")
        continue
    
    # Get max segment end_time for each transcript
    segment_times = {}
    for t in transcripts.data:
        segs = client.table("transcript_segments").select("end_time").eq("transcript_id", t["id"]).order("end_time", desc=True).limit(1).execute()
        if segs.data:
            segment_times[t["episode_id"]] = segs.data[0]["end_time"]
    
    # Get episodes
    episodes = client.table("episodes").select("eid, title, duration").eq("user_id", user_id).execute()
    ep_map = {ep["eid"]: ep for ep in episodes.data}
    
    print(f"{'Episode Title':<50} {'Ep Dur':>8} {'Tx Dur':>8} {'%':>6} {'Status':>10}")
    print("-" * 90)
    
    for t in transcripts.data:
        ep = ep_map.get(t["episode_id"], {})
        ep_dur = ep.get("duration", 0)
        tx_dur = segment_times.get(t["episode_id"]) or t["duration"] or 0
        
        if ep_dur > 0:
            pct = (tx_dur / ep_dur) * 100
            status = "OK" if pct >= 95 else "TRUNCATED"
        else:
            pct = 0
            status = "NO EP DUR"
        
        title = ep.get("title", t["episode_id"])[:48]
        print(f"{title:<50} {ep_dur:>7}s {tx_dur:>7.0f}s {pct:>5.1f}% {status:>10}")
    
    print()
