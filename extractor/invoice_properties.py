"""Extraktion strukturierter Rechnungs-Properties aus OCR-Text via LLM."""

from __future__ import annotations

import json
import re
from typing import Literal

from .llm_text import call_text_llm

PROPERTY_KEYS = [
    "Belegnummer",
    "Belegdatum",
    "Lieferant",
    "Lieferdatum",
    "Verknüpfung",
    "Fälligkeit",
    "Kostenstelle",
    "Tags",
    "Kategorie",
    "Betrag (Brutto)",
    "Währung",
    "Umsatzsteuer",
    "Beschreibung",
    "Positionen",
    "Gesamt Netto",
    "Gesamt Umsatzsteuer",
    "Gesamt Betrag",
]

_LIST_KEYS = {"Tags", "Positionen"}

SYSTEM_PROMPT = """\
Du extrahierst strukturierte Rechnungsdaten aus OCR-Text.
Gib IMMER ein gueltiges JSON-Objekt mit exakt den vorgegebenen Keys zurueck.
Keine Erklaerungen, keine Markdown-Formatierung.
Wenn ein Feld unbekannt ist: leerer String.
Fuer "Tags" und "Positionen": leere Liste [] falls nichts vorhanden.
"""


def _schema_json() -> str:
    return json.dumps(
        {key: ([] if key in _LIST_KEYS else "") for key in PROPERTY_KEYS},
        ensure_ascii=False,
        indent=2,
    )


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _extract_json_block(raw: str) -> dict:
    """Parst JSON robust auch wenn das Modell Code-Fences mitschickt."""
    s = (raw or "").strip()
    if not s:
        return {}

    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```$", "", s)

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            return json.loads(s[start:end + 1])
        raise


def _coerce_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out = []
        for item in value:
            if item is None:
                continue
            text = _norm(str(item))
            if text:
                out.append(text)
        return out
    text = _norm(str(value))
    return [text] if text else []


def _coerce_properties(payload: dict) -> dict:
    props = {}
    for key in PROPERTY_KEYS:
        value = payload.get(key, [] if key in _LIST_KEYS else "")
        if key in _LIST_KEYS:
            props[key] = _coerce_list(value)
        else:
            props[key] = _norm("" if value is None else str(value))
    return props


def extract_invoice_properties(
    ocr_text: str,
    provider: Literal["openai", "anthropic"] = "openai",
    model: str | None = None,
) -> dict:
    """LLM-basierte Property-Extraktion für Rechnungsdaten."""
    text = (ocr_text or "").strip()
    if not text:
        return _coerce_properties({})

    prompt = (
        "Extrahiere die Rechnungsdaten aus folgendem OCR-Text.\n"
        "Rueckgabeformat: Nur JSON mit exakt dieser Struktur:\n"
        f"{_schema_json()}\n\n"
        "OCR-Text:\n"
        f"{text}"
    )
    raw = call_text_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=prompt,
        provider=provider,
        model=model,
        max_tokens=4096,
    )
    payload = _extract_json_block(raw)
    if not isinstance(payload, dict):
        raise ValueError("LLM-Antwort fuer Rechnungs-Properties ist kein JSON-Objekt.")
    return _coerce_properties(payload)


def normalize_value(value) -> str:
    if isinstance(value, list):
        return " | ".join(_norm(str(v)) for v in value if _norm(str(v)))
    return _norm("" if value is None else str(value))
