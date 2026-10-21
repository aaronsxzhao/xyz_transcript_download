"""Resolve summary providers on the server; credentials never enter browser settings."""
from config import GROQ_API_KEY, GROQ_WHISPER_URL, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

GROQ_MODELS = ("openai/gpt-oss-120b", "openai/gpt-oss-20b")


def resolve_llm_settings(preferences: dict, model: str = "") -> dict:
    provider = preferences.get("llm_provider", "server")
    if provider == "groq":
        if not GROQ_API_KEY:
            raise ValueError("Groq API key is missing on the server. Configure GROQ_API_KEY first.")
        selected = model or preferences.get("llm_model", "")
        # Older browsers/tasks may still send model names from the previous gateway.
        selected = selected if selected in GROQ_MODELS else GROQ_MODELS[0]
        return {"api_key": GROQ_API_KEY, "base_url": GROQ_WHISPER_URL, "model": selected}
    if not LLM_API_KEY:
        raise ValueError("Summary provider is not configured. Open Settings and choose Groq summaries.")
    return {"api_key": LLM_API_KEY, "base_url": LLM_BASE_URL,
            "model": model or preferences.get("llm_model") or LLM_MODEL}


def provider_status(preferences: dict) -> dict:
    """Configuration presence is separate from an actual successful connection test."""
    provider = preferences.get("llm_provider", "server")
    return {"llm_provider": provider, "groq_available": bool(GROQ_API_KEY),
            "llm_configured": bool(GROQ_API_KEY if provider == "groq" else LLM_API_KEY)}


def test_summary_connection(preferences: dict) -> dict:
    """A small real completion verifies the key, endpoint, model, and JSON support."""
    import json
    from openai import OpenAI
    settings = resolve_llm_settings(preferences)
    with OpenAI(api_key=settings["api_key"], base_url=settings["base_url"],
                timeout=25.0, max_retries=0) as client:
        result = client.chat.completions.create(
            model=settings["model"], messages=[{"role": "user", "content": 'Reply with JSON: {"ok":true}'}],
            response_format={"type": "json_object"}, max_completion_tokens=1024,
            **({"reasoning_effort": "low"} if preferences.get("llm_provider") == "groq" else {}),
        )
        content = result.choices[0].message.content
        if not content or not isinstance(json.loads(content), dict):
            raise ValueError("The model returned no JSON response. Try another summary model.")
    return {"message": "Summary connection verified", "model": settings["model"]}


def safe_provider_error(error: Exception) -> str:
    """Do not return provider response bodies, URLs, or headers containing credentials."""
    from summary_errors import SummaryOutputError
    if isinstance(error, SummaryOutputError):
        return str(error)
    if type(error).__name__ in {'APITimeoutError','ReadTimeout','ConnectTimeout'}:
        return "The summary provider timed out. Please retry summary generation."
    if type(error).__name__ in {'APIConnectionError','ConnectError','RemoteProtocolError'}:
        return "The connection to the summary provider was interrupted. Please retry summary generation."
    status = getattr(error, "status_code", None)
    if isinstance(status, int) and status >= 500:
        return "The summary provider is temporarily unavailable. Please retry later."
    if status in (401, 403):
        return "The summary provider rejected the API key or model access. Check provider permissions."
    if status == 429:
        return "The summary provider's rate limit or quota was reached. Wait and retry, or check your Groq limits."
    if status in (400, 404):
        return "The summary model or API endpoint is unavailable. Choose a supported model in Settings."
    return "The summary request failed. Please retry or test the provider connection in Settings."
