"""
Supabase client for database and storage operations.
Provides user-scoped data access with Row Level Security.
"""

from typing import Optional
from functools import lru_cache

from config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY, USE_SUPABASE

# Only import if Supabase is configured
if USE_SUPABASE:
    from supabase import create_client, Client


def _create_server_client(key):
    from supabase import create_client
    from supabase.client import ClientOptions
    from api.supabase_http import SupabaseHTTPClient
    return create_client(SUPABASE_URL, key, options=ClientOptions(
        httpx_client=SupabaseHTTPClient(), auto_refresh_token=False, persist_session=False,
    ))


@lru_cache()
def get_supabase_client() -> Optional["Client"]:
    """
    Get the Supabase client with anon key (for authenticated user requests).
    Uses RLS policies to restrict data access.
    """
    if not USE_SUPABASE:
        return None
    return _create_server_client(SUPABASE_KEY)


@lru_cache()
def get_supabase_admin_client() -> Optional["Client"]:
    """
    Get the Supabase client with service role key (bypasses RLS).
    Use only for server-side operations that need full access.
    """
    if not USE_SUPABASE or not SUPABASE_SERVICE_KEY:
        return None
    return _create_server_client(SUPABASE_SERVICE_KEY)


def get_user_client(access_token: str) -> Optional["Client"]:
    """
    Get a Supabase client authenticated as a specific user.
    This client respects RLS policies for that user.
    """
    if not USE_SUPABASE:
        return None
    
    client = _create_server_client(SUPABASE_KEY)
    client.auth.set_session(access_token, "")
    return client
