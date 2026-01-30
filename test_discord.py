#!/usr/bin/env python3
"""Quick test script to verify Discord webhook is working."""

import sys
sys.path.insert(0, '.')

from dotenv import load_dotenv
load_dotenv()

from config import DISCORD_WEBHOOK_URL
from logger import notify_discord

print(f"Webhook URL configured: {bool(DISCORD_WEBHOOK_URL)}")
if DISCORD_WEBHOOK_URL:
    print(f"Webhook URL: {DISCORD_WEBHOOK_URL[:50]}...")

print("\nSending test notification...")
notify_discord(
    title="Test Notification",
    message="If you see this, Discord notifications are working!",
    event_type="info",
)

# Give the thread time to send
import time
time.sleep(3)
print("\nDone! Check your Discord channel.")
