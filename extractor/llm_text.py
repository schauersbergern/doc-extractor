"""Gemeinsame Text-LLM-Aufrufe fuer OpenAI/Anthropic."""

from __future__ import annotations

import os
from typing import Literal

Provider = Literal["openai", "anthropic"]


def resolve_default_model(provider: Provider) -> str:
    if provider == "anthropic":
        return "claude-opus-4-5-20251101"
    return "gpt-5.2"


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

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=resolved_model,
        temperature=0.0,
        max_completion_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return (response.choices[0].message.content or "").strip()
