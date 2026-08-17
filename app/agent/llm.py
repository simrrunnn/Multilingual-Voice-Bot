"""OpenRouter LLM abstraction.

OpenRouter exposes an OpenAI-compatible Chat Completions API, so this reuses
the `livekit-plugins-openai` client pointed at OpenRouter's base URL instead
of a bespoke HTTP client. The only place the model/provider is chosen --
swapping `OPENROUTER_MODEL` in `.env` changes it with no code changes.
"""

from __future__ import annotations

from livekit.plugins import openai as lk_openai

from app.config import get_settings


def build_openrouter_llm() -> lk_openai.LLM:
    """Construct the LiveKit-compatible LLM client, configured for OpenRouter."""

    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Configure it in .env before starting the voice agent."
        )
    return lk_openai.LLM(
        model=settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
