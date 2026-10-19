"""Persist model preferences without changing another account's defaults."""
import json
import sqlite3
from typing import Optional

from config import DATABASE_PATH, USE_SUPABASE, WHISPER_MODE, WHISPER_LOCAL_MODEL, get_runtime_settings

SETTING_KEYS = {"whisper_model", "llm_model", "llm_provider"}


def get_user_settings(user_id: Optional[str]) -> dict:
    defaults = get_runtime_settings()
    from api.llm_settings import GROQ_API_KEY, GROQ_MODELS, LLM_MODEL
    defaults["llm_provider"] = "groq" if GROQ_API_KEY else "server"
    if GROQ_API_KEY:
        defaults["llm_model"] = GROQ_MODELS[0]
    if WHISPER_MODE == "local":
        defaults["whisper_model"] = WHISPER_LOCAL_MODEL
    if USE_SUPABASE:
        if not user_id:
            return defaults
        from api.supabase_client import get_supabase_admin_client
        client = get_supabase_admin_client()
        if client is None:
            raise RuntimeError("Supabase is unavailable")
        result = client.table("user_settings").select("preferences").eq("user_id", user_id).execute()
        saved = result.data[0].get("preferences", {}) if result.data else {}
    else:
        with sqlite3.connect(str(DATABASE_PATH)) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS user_settings (user_id TEXT PRIMARY KEY, preferences TEXT NOT NULL)")
            row = conn.execute("SELECT preferences FROM user_settings WHERE user_id = ?", (user_id or "local",)).fetchone()
            saved = json.loads(row[0]) if row else {}
    settings = {**defaults, **{k: v for k, v in saved.items() if k in SETTING_KEYS}}
    if settings["llm_provider"] == "groq" and settings["llm_model"] not in GROQ_MODELS:
        settings["llm_model"] = GROQ_MODELS[0]
    elif settings["llm_provider"] == "server" and "llm_model" not in saved:
        settings["llm_model"] = LLM_MODEL
    return settings


def save_user_settings(user_id: str, settings: dict) -> None:
    preferences = {k: v for k, v in get_user_settings(user_id).items() if k in SETTING_KEYS}
    preferences.update({k: v for k, v in settings.items() if k in SETTING_KEYS})
    if USE_SUPABASE:
        from api.supabase_client import get_supabase_admin_client
        client = get_supabase_admin_client()
        if client is None:
            raise RuntimeError("Supabase is unavailable")
        client.table("user_settings").upsert({"user_id": user_id, "preferences": preferences}, on_conflict="user_id").execute()
    else:
        with sqlite3.connect(str(DATABASE_PATH)) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS user_settings (user_id TEXT PRIMARY KEY, preferences TEXT NOT NULL)")
            conn.execute("INSERT INTO user_settings VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET preferences = excluded.preferences",
                         (user_id, json.dumps(preferences)))
