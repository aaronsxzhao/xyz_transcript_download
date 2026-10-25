"""Persist model preferences without changing another account's defaults."""
import json
import sqlite3
import threading
from contextlib import contextmanager
from weakref import WeakValueDictionary
from typing import Optional

from config import DATABASE_PATH, USE_SUPABASE, WHISPER_MODE, WHISPER_LOCAL_MODEL, get_runtime_settings

SETTING_KEYS = {"whisper_model", "llm_model", "llm_provider", "transcription_provider", "llm_base_url", "whisper_base_url"}
SECRET_KEYS = {"llm_api_key", "whisper_api_key"}
_settings_locks = WeakValueDictionary()
_settings_locks_guard = threading.Lock()


@contextmanager
def account_settings_lock(user_id: str):
    # The current server has one worker with concurrent request threads. Keep
    # each account's validation and read/modify/write sequence together.
    with _settings_locks_guard:
        lock = _settings_locks.setdefault(user_id, threading.RLock())
    with lock:
        yield


def _load_preferences(user_id: Optional[str]) -> dict:
    if USE_SUPABASE:
        if not user_id:
            return {}
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
    return saved if isinstance(saved, dict) else {}


def get_user_settings(user_id: Optional[str]) -> dict:
    defaults = get_runtime_settings()
    from api.llm_settings import GROQ_API_KEY, GROQ_MODELS, LLM_MODEL
    defaults["llm_provider"] = "groq" if GROQ_API_KEY else "server"
    defaults["transcription_provider"] = "server"
    if GROQ_API_KEY:
        defaults["llm_model"] = GROQ_MODELS[0]
    if WHISPER_MODE == "local":
        defaults["whisper_model"] = WHISPER_LOCAL_MODEL
    saved = _load_preferences(user_id)
    settings = {**defaults, **{k: v for k, v in saved.items() if k in SETTING_KEYS}}
    from api.model_credentials import decrypt_key
    for field in SECRET_KEYS:
        try:
            settings[field] = decrypt_key(user_id or "local", field, saved.get(field + "_encrypted", ""))
        except ValueError:
            settings[field] = ""
            settings[field + "_error"] = "Saved model key cannot be opened. Re-enter it in Settings."
    if settings["llm_provider"] == "groq" and settings["llm_model"] not in GROQ_MODELS:
        settings["llm_model"] = GROQ_MODELS[0]
    elif settings["llm_provider"] == "server" and "llm_model" not in saved:
        settings["llm_model"] = LLM_MODEL
    return settings


def save_user_settings(user_id: str, settings: dict) -> dict:
    with account_settings_lock(user_id):
        return _save_user_settings(user_id, settings)


def _save_user_settings(user_id: str, settings: dict) -> dict:
    current = get_user_settings(user_id)
    saved = _load_preferences(user_id)
    preferences = {k: v for k, v in current.items() if k in SETTING_KEYS}
    preferences.update({k: v for k, v in settings.items() if k in SETTING_KEYS})
    from api.model_credentials import encrypt_key
    for field in SECRET_KEYS:
        preferences[field + "_encrypted"] = encrypt_key(user_id, field, settings[field]) if field in settings else saved.get(field + "_encrypted", "")
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
    # A save acknowledgement describes the persisted row, not its pre-save draft.
    return get_user_settings(user_id)
