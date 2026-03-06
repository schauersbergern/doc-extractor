"""Gemeinsame Text-LLM-Aufrufe fuer OpenAI/Anthropic."""

from __future__ import annotations

import logging
import os
from typing import Literal

Provider = Literal["openai", "anthropic"]
logger = logging.getLogger(__name__)


def resolve_default_model(provider: Provider) -> str:
    if provider == "anthropic":
        return "claude-opus-4-5-20251101"
    return "gpt-5.2"


def resolve_openai_timeout_seconds(default: float = 180.0) -> float:
    raw_value = os.environ.get("OPENAI_TIMEOUT_SECONDS", str(default)).strip()
    try:
        timeout = float(raw_value)
    except ValueError:
        logger.warning(
            "Ungueltiger OPENAI_TIMEOUT_SECONDS Wert %r, nutze %.1fs",
            raw_value,
            default,
        )
        return default
    return max(1.0, timeout)


def resolve_openai_max_retries(default: int = 2) -> int:
    raw_value = os.environ.get("OPENAI_MAX_RETRIES", str(default)).strip()
    try:
        retries = int(raw_value)
    except ValueError:
        logger.warning(
            "Ungueltiger OPENAI_MAX_RETRIES Wert %r, nutze %s",
            raw_value,
            default,
        )
        return default
    return max(0, retries)


def call_text_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    provider: Provider = "openai",
    model: str | None = None,
    max_tokens: int = 4096,
) -> str:
    """Führt einen Text-Only LLM-Call gegen OpenAI oder Anthropic aus."""
    resolved_model = model or resolve_default_model(provider)

    if provider == "anthropic":
        try:
            import anthropic
        except ImportError:
            raise ImportError("anthropic SDK fehlt: pip install anthropic")

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY nicht gesetzt.")

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=resolved_model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return (response.content[0].text or "").strip()

    try:
        import openai
    except ImportError:
        raise ImportError("openai SDK fehlt: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY nicht gesetzt.")

    timeout_seconds = resolve_openai_timeout_seconds()
    client = openai.OpenAI(
        api_key=api_key,
        timeout=timeout_seconds,
        max_retries=resolve_openai_max_retries(),
    )
    logger.info(
        "Text-LLM Request (openai/%s, timeout=%.0fs)",
        resolved_model,
        timeout_seconds,
    )
    try:
        response = client.chat.completions.create(
            model=resolved_model,
            temperature=0.0,
            max_completion_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except openai.APITimeoutError as exc:
        raise TimeoutError(
            f"OpenAI Text-Request hat nach {timeout_seconds:.0f}s kein Ergebnis geliefert. "
            "Erhoehe OPENAI_TIMEOUT_SECONDS oder starte den Lauf erneut."
        ) from exc
    return (response.choices[0].message.content or "").strip()
