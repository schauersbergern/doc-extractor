"""Finaler Post-Processing-Schritt fuer Vektorisierung."""

from __future__ import annotations

from typing import Literal

from .llm_text import call_text_llm
from .models import SlideData

PostProcessType = Literal["powerpoint", "handwriting"]

SYSTEM_PROMPT = """\
Du bist ein Spezialist fuer Wissensaufbereitung fuer Vektor-Datenbanken.
Ausgabe muss praezise, eigenstaendig verstaendlich und fuer semantische Suche optimiert sein.
Nutze klare Struktur und konsistente Begriffe.
"""

POWERPOINT_PROMPT = """\
Du bekommst extrahierten Slide-/Dokumenttext.
Erzeuge einen finalen, vektorisierungsbereiten Endtext in Deutsch.

Anforderungen:
1) Alle relevanten Fakten erhalten, Redundanz reduzieren.
2) Prozessdiagramme als detaillierte Prozessbeschreibung aufloesen:
   - Schritte in logischer Reihenfolge
   - Entscheidungen/Bedingungen
   - Ein-/Ausgaben pro Schritt
   - beteiligte Rollen/Systeme
3) Klare Abschnittsstruktur mit Ueberschriften.
4) Keine Referenz auf Bilder notwendig; Text muss alleine verstaendlich sein.

Gib nur den finalen Endtext zurueck.
"""

HANDWRITING_PROMPT = """\
Du bekommst OCR-Text aus Handschrift.
Erzeuge einen finalen, vektorisierungsbereiten Endtext in Deutsch.

Anforderungen:
1) OCR-Rauschen entfernen und offensichtliche Fehler normalisieren.
2) Inhalt in saubere, vollstaendige Saetze ueberfuehren.
3) Bei unklaren Stellen vorsichtig formulieren ("unklar"/"vermutlich"), nichts erfinden.
4) Klare Abschnittsstruktur.

Gib nur den finalen Endtext zurueck.
"""


def transform_text_for_vector_db(
    text: str,
    source_type: PostProcessType,
    provider: Literal["openai", "anthropic"] = "openai",
    model: str | None = None,
) -> str:
    """Transformiert OCR-/Vision-Text in finalen Endtext fuer Embeddings."""
    input_text = (text or "").strip()
    if not input_text:
        return ""

    user_prompt = (
        (POWERPOINT_PROMPT if source_type == "powerpoint" else HANDWRITING_PROMPT)
        + "\n\nQuelltext:\n"
        + input_text
    )
    return call_text_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        provider=provider,
        model=model,
        max_tokens=4096,
    )


def post_process_slides_for_vector_db(
    slides: list[SlideData],
    source_type: PostProcessType,
    provider: Literal["openai", "anthropic"] = "openai",
    model: str | None = None,
) -> list[SlideData]:
    """Schreibt vector_ready_text fuer jede SlideData."""
    for slide in slides:
        slide.vector_ready_text = transform_text_for_vector_db(
            slide.content,
            source_type=source_type,
            provider=provider,
            model=model,
        )
    return slides
