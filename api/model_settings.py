"""Authenticated probes and validation for per-account model settings."""
from fastapi import APIRouter, Depends, HTTPException
from api.auth import User, get_current_user
from api.custom_models import ModelConfigurationError, normalize_base_url, probe_provider, public_model_error, resolve_custom
from api.user_settings import SETTING_KEYS, SECRET_KEYS, get_user_settings, save_user_settings, account_settings_lock

router = APIRouter()


def update_user_settings(owner: str, patch: dict) -> dict:
    with account_settings_lock(owner):
        preferences, filtered = prepared_settings(owner, patch)
        if preferences.get("llm_provider") == "custom":
            resolve_custom(preferences, "summary")
        if preferences.get("transcription_provider") == "custom":
            resolve_custom(preferences, "transcription")
        from api.llm_settings import resolve_llm_settings
        # Validate explicit options without making unrelated saves depend on a paid probe.
        if preferences.get('llm_reasoning_effort') or preferences.get('llm_service_tier'):
            resolve_llm_settings(preferences)
        return save_user_settings(owner, filtered)


def prepared_settings(owner: str, patch: dict) -> tuple[dict, dict]:
    current = get_user_settings(owner)
    filtered = {key: value for key, value in patch.items() if key in SETTING_KEYS | SECRET_KEYS}
    for key, value in filtered.items():
        limit = 4096 if key in SECRET_KEYS else 2048 if key.endswith("base_url") else 200
        if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
            raise ModelConfigurationError(f"Invalid {key.replace('_', ' ')}. Enter a single-line value of at most {limit} characters.")
        filtered[key] = value.strip()
    if filtered.get("llm_provider", current.get("llm_provider")) not in {"server", "groq", "custom"}:
        raise ModelConfigurationError("Choose a supported summary provider.")
    if filtered.get("transcription_provider", current.get("transcription_provider", "server")) not in {"server", "custom"}:
        raise ModelConfigurationError("Choose a supported transcription provider.")
    for prefix in ("llm", "whisper"):
        url_key, key_field = prefix + "_base_url", prefix + "_api_key"
        if filtered.get(url_key):
            filtered[url_key] = normalize_base_url(filtered[url_key])
            if filtered[url_key] != current.get(url_key) and (current.get(key_field) or current.get(key_field + "_error")) and not filtered.get(key_field):
                raise ModelConfigurationError("Base URL changed. Re-enter the API key for this endpoint; the old key will not be sent to a different service.")
    merged = {**current, **filtered}
    for field in SECRET_KEYS & filtered.keys():
        merged.pop(field + "_error", None)
    return merged, filtered


@router.post("/models")
def list_models(payload: dict, user: User = Depends(get_current_user)):
    kind = payload.get("kind")
    if kind not in {"summary", "transcription"}:
        raise HTTPException(422, detail="Choose summary or transcription models.")
    try:
        preferences, _ = prepared_settings(user.id, payload)
        return probe_provider(preferences, kind, models_only=True)
    except ModelConfigurationError as error:
        raise HTTPException(422, detail=str(error))
    except Exception as error:
        raise HTTPException(502, detail=public_model_error(error, "model listing") + " If this provider has no /models API, enter its documented model ID manually.")


@router.post("/test-transcription")
def test_transcription(payload: dict, user: User = Depends(get_current_user)):
    try:
        preferences, _ = prepared_settings(user.id, payload)
        if preferences.get("transcription_provider") != "custom":
            raise ModelConfigurationError("Select your custom transcription service first.")
        resolve_custom(preferences, "transcription")
        return probe_provider(preferences, "transcription")
    except ModelConfigurationError as error:
        raise HTTPException(422, detail=str(error))
    except Exception as error:
        raise HTTPException(502, detail=public_model_error(error, "audio transcription"))


@router.post('/model-options')
def model_options(payload: dict, user: User = Depends(get_current_user)):
    from model_execution import capabilities
    from api.llm_settings import GROQ_WHISPER_URL, LLM_BASE_URL
    try:
        current = get_user_settings(user.id)
        provider = payload.get('llm_provider',current.get('llm_provider'))
        model = payload.get('llm_model',current.get('llm_model',''))
        if provider not in ('server','groq','custom') or not isinstance(model,str) or len(model)>200:
            raise ModelConfigurationError('Choose a supported provider and model.')
        # This is a local capability lookup, not an outbound probe. A changed
        # endpoint must not require sending a draft API key merely to show options.
        base = payload.get('llm_base_url',current.get('llm_base_url','')) if provider=='custom' else GROQ_WHISPER_URL if provider=='groq' else LLM_BASE_URL
        if not isinstance(base,str): raise ModelConfigurationError('Enter a valid Base URL.')
        return capabilities(base,model)
    except ModelConfigurationError as error:
        raise HTTPException(422, detail=str(error))
