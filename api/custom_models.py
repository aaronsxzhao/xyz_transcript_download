"""Validation and bounded, redacted probes for OpenAI-compatible providers."""
import io
import ipaddress
import logging
import socket
import wave
from urllib.parse import urlsplit

import httpx
from openai import OpenAI

from config import USE_SUPABASE


class ModelConfigurationError(ValueError):
    pass


def normalize_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ModelConfigurationError("Enter an OpenAI-compatible Base URL, such as https://api.example.com/v1.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ModelConfigurationError("Base URL must not contain credentials, a query, or a fragment. Enter the API key separately.")
    if USE_SUPABASE and parsed.scheme != "https":
        raise ModelConfigurationError("Use an HTTPS Base URL for your API key.")
    if parsed.path.endswith(("/models", "/chat/completions", "/audio/transcriptions")):
        raise ModelConfigurationError("Enter the API root (usually ending in /v1), not /models, /chat/completions or /audio/transcriptions.")
    # Bare hosts use the conventional OpenAI root. Preserve custom prefixes
    # (for example /openai/v1 or /gateway), and never append /v1 twice.
    return value + '/v1' if not parsed.path else value


def _check_destination(request: httpx.Request) -> None:
    # User endpoints must not turn the cloud server into a private-network proxy.
    if not USE_SUPABASE:
        return
    try:
        addresses = socket.getaddrinfo(request.url.host, request.url.port or 443, type=socket.SOCK_STREAM)
    except OSError:
        raise ModelConfigurationError("Cannot resolve the provider hostname. Check the Base URL.") from None
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ModelConfigurationError("The cloud website needs a publicly reachable model endpoint; localhost and private network addresses cannot be used.")


def custom_http_client() -> httpx.Client:
    return httpx.Client(follow_redirects=False, event_hooks={"request": [_check_destination]})


def resolve_custom(preferences: dict, kind: str) -> dict:
    prefix = "llm" if kind == "summary" else "whisper"
    base = normalize_base_url(preferences.get(prefix + "_base_url", ""))
    key = preferences.get(prefix + "_api_key", "")
    model = preferences.get(prefix + "_model", "").strip()
    if not key:
        raise ModelConfigurationError(f"Enter and save the API key for {kind} in Settings.")
    if not model:
        raise ModelConfigurationError(f"Choose or enter a {kind} model ID in Settings.")
    return {"api_key": key, "base_url": base, "model": model, "custom_endpoint": True}


def public_model_error(error: Exception, kind: str) -> str:
    from summary_errors import SummaryOutputError
    if isinstance(error, SummaryOutputError):
        return str(error)
    if isinstance(error, ModelConfigurationError):
        return str(error)
    status = getattr(error, "status_code", None)
    if status in (401, 403):
        return "API key rejected or model access denied. Check the key and provider permissions."
    if status == 402:
        return "The provider requires payment. Check the account balance and billing."
    if status == 429:
        return "Provider rate limit or quota reached. Check usage and balance, or wait before retrying."
    body = getattr(error, 'body', None)
    detail = body.get('error', body) if isinstance(body, dict) else {}
    param = detail.get('param') if isinstance(detail, dict) else None
    if status in (400,422) and param in ('reasoning_effort','service_tier'):
        return f"The provider rejected {param}. Choose Provider default or a value documented for this model, then test again."
    if status in (400, 404, 405, 422):
        return f"The endpoint or model does not support the required {kind} API. Check the API root and model ID."
    if isinstance(status, int) and 300 <= status < 400:
        return "The endpoint redirects requests. Enter the final API root directly."
    if isinstance(status, int) and status >= 500:
        return f"The model provider returned HTTP {status} and is temporarily unavailable. Retry later."
    if "timeout" in type(error).__name__.lower():
        return "The model provider timed out. Check the Base URL or retry later."
    if type(error).__name__ in {"APIConnectionError", "ConnectError"}:
        return "Cannot connect to the provider. Check the Base URL, TLS certificate, and network access."
    return f"Could not verify {kind}. Check provider compatibility and try again."


def probe_provider(preferences: dict, kind: str, *, models_only=False) -> dict:
    operation = "models" if models_only else "summary" if kind == "summary" else "transcription"
    try:
        return _probe_provider(preferences, kind, models_only=models_only)
    except Exception as error:
        status = getattr(error, "status_code", 0)
        status = status if isinstance(status, int) and 100 <= status <= 599 else 0
        # Provider bodies and exception messages may contain keys or private URLs.
        logging.getLogger(__name__).warning(
            "Custom model probe failed: operation=%s error_type=%s upstream_status=%s",
            operation, type(error).__name__, status,
        )
        raise


def _probe_provider(preferences: dict, kind: str, *, models_only=False) -> dict:
    config = resolve_custom({**preferences, ("llm_model" if kind == "summary" else "whisper_model"): preferences.get("llm_model" if kind == "summary" else "whisper_model") or "list-models"}, kind)
    with OpenAI(api_key=config["api_key"], base_url=config["base_url"], timeout=20, max_retries=0,
                http_client=custom_http_client()) as client:
        if models_only:
            models = client.models.list()
            ids = sorted({row.id for row in models.data if isinstance(row.id, str) and 0 < len(row.id) <= 200})[:1000]
            return {"models": ids, "message": "Model listing does not prove audio/JSON capability. Test the selected model before processing."}
        if kind == "summary":
            import json
            response = client.chat.completions.create(model=config["model"], messages=[{"role": "user", "content": 'Reply with JSON: {"ok":true}'}], response_format={"type": "json_object"}, max_completion_tokens=2048, **__import__("model_execution").request_options(preferences, config["base_url"], config["model"]))
            try:
                parsed = json.loads(response.choices[0].message.content or "")
            except (ValueError, IndexError, AttributeError):
                raise ModelConfigurationError("Model did not return valid JSON. Choose a summary model supporting JSON output.") from None
            if not isinstance(parsed, dict):
                raise ModelConfigurationError("Model did not return JSON. Choose a summary model supporting JSON output.")
        else:
            audio = io.BytesIO()
            with wave.open(audio, "wb") as output:
                output.setnchannels(1); output.setsampwidth(2); output.setframerate(16000)
                output.writeframes(b"\0\0" * 16000)
            # A short synthetic probe verifies the same endpoint/response format used by processing.
            response = client.audio.transcriptions.create(model=config["model"], file=("connection-test.wav", audio.getvalue(), "audio/wav"), response_format="verbose_json", timestamp_granularities=["segment"])
            if not hasattr(response, "text"):
                raise ModelConfigurationError("Transcription endpoint did not return text. This must be an audio transcription model.")
        message = "Connection verified. Save Settings to apply it to new tasks."
        if kind == 'summary' and (preferences.get('llm_reasoning_effort') or preferences.get('llm_service_tier')):
            message += " Selected parameters were accepted by the endpoint; gateways may not confirm whether they were applied."
        return {"model": config["model"], "message": message}
