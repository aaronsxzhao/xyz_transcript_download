#!/usr/bin/env python3
"""
Troubleshooting script for Render deploys and Supabase database.

Setup:
1. Get Render API key: https://dashboard.render.com/u/settings#api-keys
2. Add to .env file:
   RENDER_API_KEY=rnd_xxx...
   RENDER_SERVICE_ID=srv-xxx...

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
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load .env file automatically
def load_env_file():
    """Load environment variables from .env file."""
    env_path = project_root / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    # Don't override existing env vars
                    if key and key not in os.environ:
                        os.environ[key] = value

load_env_file()

try:
    import requests
except ImportError:
    print("Please install requests: pip install requests")
    sys.exit(1)


def check_render_cli_available():
    """Check if Render CLI is available."""
    import subprocess
    try:
        result = subprocess.run(["render", "--version"], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def check_render_status():
    """Check Render service status and recent deploys."""
    import subprocess
    
    service_id = os.getenv("RENDER_SERVICE_ID")
    
    # Try Render CLI first (doesn't need API key if logged in)
    if check_render_cli_available():
        print("\n📡 Checking Render status via CLI...")
        
        try:
            # Get deploys using CLI
            result = subprocess.run(
                ["render", "deploys", "list", service_id, "--output", "json", "--confirm"],
                capture_output=True, text=True, timeout=60
            )
            
            if result.returncode == 0:
                deploys = json.loads(result.stdout)
                
                if deploys:
                    first = deploys[0].get("deploy", deploys[0])
                    print(f"   ✅ Service ID: {service_id}")
                    print(f"   Latest status: {first.get('status', 'unknown')}")
                
                print("\n📦 Recent deploys:")
                for deploy in deploys[:5]:
                    d = deploy.get("deploy", deploy)
                    status = d.get("status", "unknown")
                    created = d.get("createdAt", "")[:19].replace("T", " ")
                    commit = d.get("commit", {})
                    commit_msg = commit.get("message", "")[:40] if commit else "N/A"
                    
                    status_icon = "✅" if status == "live" else "🔄" if status in ("build_in_progress", "update_in_progress") else "❌" if status == "build_failed" else "⚪"
                    print(f"   {status_icon} {status:20} | {created} | {commit_msg}")
                
                return True
            else:
                print(f"   ⚠️ CLI error: {result.stderr[:100]}")
        except subprocess.TimeoutExpired:
            print("   ⚠️ CLI timeout")
        except Exception as e:
            print(f"   ⚠️ CLI error: {e}")
    
    # Fall back to API
    api_key = os.getenv("RENDER_API_KEY")
    
    if not api_key:
        if not check_render_cli_available():
            print("\n📡 Render status:")
            print("   ❌ Neither RENDER_API_KEY nor Render CLI available")
            print("   Install CLI: brew install render && render login")
            print("   Or set API key: https://dashboard.render.com/u/settings#api-keys")
        return False
    
    if not service_id:
        print("❌ RENDER_SERVICE_ID not set")
        print("   Find it in your Render dashboard URL: /web/srv-XXXXX")
        return False
    
    headers = {"Authorization": f"Bearer {api_key}"}
    base_url = "https://api.render.com/v1"
    
    print("\n📡 Checking Render service status via API...")
    
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
    import subprocess
    
    service_id = os.getenv("RENDER_SERVICE_ID")
    
    if not service_id:
        print("❌ RENDER_SERVICE_ID not set")
        return
    
    # Try Render CLI first
    if check_render_cli_available():
        print(f"\n📋 Fetching deploy logs for {service_id}...")
        print("=" * 60)
        
        try:
            # Get latest deploy ID
            result = subprocess.run(
                ["render", "deploys", "list", service_id, "--output", "json", "--confirm"],
                capture_output=True, text=True, timeout=60
            )
            
            if result.returncode == 0:
                deploys = json.loads(result.stdout)
                if deploys:
                    deploy = deploys[0].get("deploy", deploys[0])
                    deploy_id = deploy.get("id")
                    status = deploy.get("status")
                    commit = deploy.get("commit", {})
                    
                    print(f"Deploy: {deploy_id}")
                    print(f"Status: {status}")
                    print(f"Commit: {commit.get('message', 'N/A')[:60]}")
                    print("=" * 60)
                    
                    # Get logs - use interactive mode workaround
                    # Note: render CLI doesn't have direct log fetch in non-interactive
                    print("\n💡 To view full logs, run:")
                    print(f"   render deploys list {service_id}")
                    print("   Then select the deploy to view logs")
                    print("\n   Or visit:")
                    print(f"   https://dashboard.render.com/web/{service_id}/deploys/{deploy_id}")
                    return
                    
        except Exception as e:
            print(f"⚠️ CLI error: {e}")
    
    # Fall back to API
    api_key = os.getenv("RENDER_API_KEY")
    
    if not api_key:
        print("❌ RENDER_API_KEY not set (needed for log content)")
        print("   Get one at: https://dashboard.render.com/u/settings#api-keys")
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
        USE_SUPABASE, SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY
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
        
        # Use service key to bypass RLS for admin access
        key = SUPABASE_SERVICE_KEY if SUPABASE_SERVICE_KEY else SUPABASE_KEY
        client = create_client(SUPABASE_URL, key)
        
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
