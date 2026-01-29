#!/usr/bin/env python3
"""
Troubleshooting script for Render deploys and Supabase database.

Setup:
1. Get Render API key: https://dashboard.render.com/u/settings#api-keys
2. Set environment variables:
   export RENDER_API_KEY="rnd_xxx..."
   export RENDER_SERVICE_ID="srv-xxx..."  # From your service URL

Usage:
    python scripts/troubleshoot.py              # Run all checks
    python scripts/troubleshoot.py --render     # Render deploy logs only
    python scripts/troubleshoot.py --supabase   # Supabase status only
    python scripts/troubleshoot.py --deploy-log # Latest deploy log
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
except ImportError:
    print("Please install requests: pip install requests")
    sys.exit(1)


def check_render_status():
    """Check Render service status and recent deploys."""
    api_key = os.getenv("RENDER_API_KEY")
    service_id = os.getenv("RENDER_SERVICE_ID")
    
    if not api_key:
        print("❌ RENDER_API_KEY not set")
        print("   Get one at: https://dashboard.render.com/u/settings#api-keys")
        return False
    
    if not service_id:
        print("❌ RENDER_SERVICE_ID not set")
        print("   Find it in your Render dashboard URL: /web/srv-XXXXX")
        return False
    
    headers = {"Authorization": f"Bearer {api_key}"}
    base_url = "https://api.render.com/v1"
    
    print("\n📡 Checking Render service status...")
    
    # Get service info
    try:
        resp = requests.get(f"{base_url}/services/{service_id}", headers=headers, timeout=30)
        if resp.status_code == 200:
            service = resp.json()
            print(f"   ✅ Service: {service.get('name', 'Unknown')}")
            print(f"   Status: {service.get('suspended', 'Unknown')}")
            print(f"   URL: {service.get('serviceDetails', {}).get('url', 'N/A')}")
        else:
            print(f"   ❌ Failed to get service: {resp.status_code}")
            print(f"   {resp.text}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Get recent deploys
    print("\n📦 Recent deploys:")
    try:
        resp = requests.get(
            f"{base_url}/services/{service_id}/deploys",
            headers=headers,
            params={"limit": 5},
            timeout=30
        )
        if resp.status_code == 200:
            deploys = resp.json()
            for deploy in deploys:
                d = deploy.get("deploy", deploy)
                status = d.get("status", "unknown")
                created = d.get("createdAt", "")[:19]
                commit_msg = d.get("commit", {}).get("message", "")[:50] if d.get("commit") else "N/A"
                
                status_icon = "✅" if status == "live" else "🔄" if status == "building" else "❌"
                print(f"   {status_icon} {status:12} | {created} | {commit_msg}")
        else:
            print(f"   ❌ Failed to get deploys: {resp.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    return True


def get_deploy_logs():
    """Get logs from the latest deploy."""
    api_key = os.getenv("RENDER_API_KEY")
    service_id = os.getenv("RENDER_SERVICE_ID")
    
    if not api_key or not service_id:
        print("❌ RENDER_API_KEY and RENDER_SERVICE_ID required")
        return
    
    headers = {"Authorization": f"Bearer {api_key}"}
    base_url = "https://api.render.com/v1"
    
    # Get latest deploy
    try:
        resp = requests.get(
            f"{base_url}/services/{service_id}/deploys",
            headers=headers,
            params={"limit": 1},
            timeout=30
        )
        if resp.status_code != 200:
            print(f"❌ Failed to get deploys: {resp.text}")
            return
        
        deploys = resp.json()
        if not deploys:
            print("No deploys found")
            return
        
        deploy = deploys[0].get("deploy", deploys[0])
        deploy_id = deploy.get("id")
        status = deploy.get("status")
        
        print(f"\n📋 Deploy {deploy_id} ({status})")
        print("=" * 60)
        
        # Get deploy logs
        resp = requests.get(
            f"{base_url}/services/{service_id}/deploys/{deploy_id}/logs",
            headers=headers,
            timeout=30
        )
        
        if resp.status_code == 200:
            logs = resp.json()
            for log in logs:
                timestamp = log.get("timestamp", "")[:19]
                message = log.get("message", "")
                print(f"[{timestamp}] {message}")
        else:
            print(f"❌ Failed to get logs: {resp.status_code}")
            print(resp.text)
            
    except Exception as e:
        print(f"❌ Error: {e}")


def check_supabase_status():
    """Check Supabase database connectivity and stats."""
    from config import (
        USE_SUPABASE, SUPABASE_URL, SUPABASE_KEY
    )
    
    print("\n🗄️  Checking Supabase status...")
    
    if not USE_SUPABASE:
        print("   ℹ️  Supabase not enabled (USE_SUPABASE=false)")
        return True
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("   ❌ SUPABASE_URL or SUPABASE_KEY not set")
        return False
    
    print(f"   URL: {SUPABASE_URL}")
    
    try:
        from supabase import create_client
        
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Test connection with simple queries
        tables = ["podcasts", "episodes", "transcripts", "summaries", "summary_key_points"]
        
        print("\n   Table counts:")
        for table in tables:
            try:
                result = client.table(table).select("*", count="exact").limit(0).execute()
                count = result.count if hasattr(result, 'count') else len(result.data)
                print(f"   - {table}: {count} rows")
            except Exception as e:
                print(f"   - {table}: ❌ {str(e)[:50]}")
        
        print("\n   ✅ Supabase connection successful")
        return True
        
    except ImportError:
        print("   ❌ supabase package not installed")
        return False
    except Exception as e:
        print(f"   ❌ Supabase error: {e}")
        return False


def check_local_status():
    """Check local database and files."""
    from config import DATA_DIR, USE_SUPABASE
    
    print("\n📁 Local storage status:")
    
    if USE_SUPABASE:
        print("   ℹ️  Using Supabase (local storage may be empty)")
    
    # Check directories
    dirs = {
        "audio": DATA_DIR / "audio",
        "transcripts": DATA_DIR / "transcripts",
        "summaries": DATA_DIR / "summaries",
    }
    
    for name, path in dirs.items():
        if path.exists():
            files = list(path.rglob("*"))
            file_count = len([f for f in files if f.is_file()])
            print(f"   - {name}: {file_count} files")
        else:
            print(f"   - {name}: (not created)")
    
    # Check SQLite database
    db_path = DATA_DIR / "xyz.db"
    if db_path.exists():
        size_mb = db_path.stat().st_size / (1024 * 1024)
        print(f"   - database: {size_mb:.2f} MB")
    else:
        print("   - database: (not created)")


def check_env_vars():
    """Check required environment variables."""
    print("\n🔧 Environment variables:")
    
    env_vars = {
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY"),
        "USE_SUPABASE": os.getenv("USE_SUPABASE"),
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY"),
        "LLM_API_KEY": os.getenv("LLM_API_KEY"),
        "LLM_BASE_URL": os.getenv("LLM_BASE_URL"),
        "LLM_MODEL": os.getenv("LLM_MODEL"),
        "RENDER_API_KEY": os.getenv("RENDER_API_KEY"),
        "RENDER_SERVICE_ID": os.getenv("RENDER_SERVICE_ID"),
    }
    
    for name, value in env_vars.items():
        if value:
            # Mask sensitive values
            if "KEY" in name or "SECRET" in name:
                display = value[:8] + "..." if len(value) > 8 else "***"
            else:
                display = value[:50] + "..." if len(value) > 50 else value
            print(f"   ✅ {name}: {display}")
        else:
            print(f"   ⚪ {name}: (not set)")


def main():
    parser = argparse.ArgumentParser(description="Troubleshoot Render and Supabase")
    parser.add_argument("--render", action="store_true", help="Check Render status only")
    parser.add_argument("--supabase", action="store_true", help="Check Supabase status only")
    parser.add_argument("--deploy-log", action="store_true", help="Show latest deploy log")
    parser.add_argument("--env", action="store_true", help="Check environment variables")
    args = parser.parse_args()
    
    print("=" * 60)
    print("🔍 XYZ Transcript Download - Troubleshooter")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    if args.deploy_log:
        get_deploy_logs()
        return
    
    if args.env:
        check_env_vars()
        return
    
    if args.render:
        check_render_status()
        return
    
    if args.supabase:
        check_supabase_status()
        return
    
    # Run all checks
    check_env_vars()
    check_local_status()
    check_supabase_status()
    check_render_status()
    
    print("\n" + "=" * 60)
    print("💡 Tips:")
    print("   - Set RENDER_API_KEY for deploy logs")
    print("   - Run with --deploy-log to see build output")
    print("   - Check Render dashboard: https://dashboard.render.com")
    print("=" * 60)


if __name__ == "__main__":
    main()
