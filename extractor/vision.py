"""Modus 2: Vision-LLM Extraktion (Anthropic Claude / OpenAI GPT).

Rendert Slides als Bilder und lässt ein Vision-LLM den Inhalt
semantisch interpretieren — ideal für Flowcharts, Diagramme,
komplexe Layouts.

Dies ist der Produktionsmodus für das Dental-Projekt.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Literal

from .models import SlideData, Timer
from .utils import estimate_tokens, image_to_base64, pptx_to_images

logger = logging.getLogger(__name__)

# === Prompts ===

SYSTEM_PROMPT = """\
Du bist ein Experte für Dokumentenanalyse. Deine Aufgabe ist es, den Inhalt \
eines Präsentations-Slides vollständig und strukturiert zu erfassen — so, dass \
der extrahierte Text später für semantische Suche (Retrieval-Augmented Generation) \
verwendet werden kann.

Regeln:
1. Erfasse ALLEN sichtbaren Text, auch in Diagrammen, Flowcharts, Tabellen und Bildern.
2. Beschreibe die STRUKTUR: Welche Elemente gehören zusammen? Was sind Phasen, \
   Übergänge, Bedingungen, Hierarchien?
3. Beschreibe VISUELLE BEZIEHUNGEN: Pfeile, Farbkodierungen, Gruppierungen, \
   räumliche Anordnung — in Textform.
4. Verwende Markdown für Struktur (Überschriften, Listen, Tabellen).
5. Der Output muss eigenständig verständlich sein, ohne das Originalbild zu sehen.
6. Sprache: Deutsch, es sei denn der Slide ist auf Englisch.
"""

SLIDE_PROMPT = """\
Analysiere diesen Präsentations-Slide vollständig.

Gib zurück:
1. **Titel** des Slides
2. **Inhaltstyp** (Text, Flowchart, Tabelle, Diagramm, Mixed)
3. **Vollständige Inhaltsbeschreibung** — alle Texte, Beziehungen, Prozessschritte
4. **Zusammenfassung** in 1-2 Sätzen (für die Vektorisierung)

Format: Markdown
"""

INVOICE_PROMPT = """\
Analysiere diese Rechnung/dieses Dokument vollständig.

Extrahiere:
1. **Dokumenttyp** (Rechnung, Angebot, Lieferschein, etc.)
2. **Absender** (Name, Adresse, Steuernummer/USt-ID)
3. **Empfänger** (Name, Adresse)
4. **Rechnungsdaten** (Nummer, Datum, Fälligkeitsdatum)
5. **Positionen** als Markdown-Tabelle (Beschreibung, Menge, Einzelpreis, Gesamtpreis)
6. **Summen** (Netto, USt, Brutto)
7. **Zahlungsinformationen** (IBAN, BIC, Verwendungszweck)
8. **Sonstige relevante Informationen**

Format: Strukturiertes Markdown
"""


def _call_anthropic(
    image_b64: str,
    media_type: str,
    prompt: str,
    model: str = "claude-opus-4-5-20251101",
) -> str:
    """Ruft die Anthropic Messages API mit einem Bild auf."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic SDK fehlt: pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY nicht gesetzt.\n"
            "Export: export ANTHROPIC_API_KEY='sk-ant-...'"
        )

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    )

    return message.content[0].text


def _call_openai(
    image_b64: str,
    media_type: str,
    prompt: str,
    model: str = "gpt-5.2",
) -> str:
    """Ruft die OpenAI Chat Completions API mit einem Bild auf."""
    try:
        import openai
    except ImportError:
        raise ImportError("openai SDK fehlt: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY nicht gesetzt.\n"
            "Export: export OPENAI_API_KEY='sk-...'"
        )

    client = openai.OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=4096,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_b64}",
                            "detail": "high",
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            },
        ],
    )

    return response.choices[0].message.content


# Kosten pro Bild (ungefähre Werte, Stand 2025/2026)
_COST_PER_IMAGE = {
    "claude-opus-4-5-20251101": 0.012,  # grober Richtwert
    "claude-haiku-4-5-20251001": 0.003,
    "gpt-5.2": 0.015,
    "gpt-4o-mini": 0.003,
}


def extract_vision(
    pptx_path: str | Path,
    slide_numbers: list[int] | None = None,
    provider: Literal["anthropic", "openai"] = "anthropic",
    model: str | None = None,
    prompt_mode: Literal["slide", "invoice"] = "slide",
    dpi: int = 200,
) -> list[SlideData]:
    """Extrahiert Slide-Inhalte via Vision-LLM.

    Args:
        pptx_path: Pfad zur PPTX-Datei
        slide_numbers: Nur diese Slides (1-basiert)
        provider: 'anthropic' oder 'openai'
        model: Modellname (Default: claude-opus-4-5 / gpt-5.2)
        prompt_mode: 'slide' für Präsentationen, 'invoice' für Rechnungen
        dpi: Render-Auflösung

    Returns:
        Liste von SlideData
    """
    pptx_path = Path(pptx_path)
    if not pptx_path.exists():
        raise FileNotFoundError(f"Nicht gefunden: {pptx_path}")

    # Defaults
    if model is None:
        model = (
            "claude-opus-4-5-20251101" if provider == "anthropic" else "gpt-5.2"
        )

    prompt = INVOICE_PROMPT if prompt_mode == "invoice" else SLIDE_PROMPT

    call_fn = _call_anthropic if provider == "anthropic" else _call_openai

    # Slides rendern
    import tempfile
    with tempfile.TemporaryDirectory(prefix="vision_") as tmp:
        tmp_path = Path(tmp)
        image_paths = pptx_to_images(pptx_path, tmp_path / "slides", dpi=dpi)

        # Filter
        if slide_numbers:
            items = [
                (int(p.stem.split("_")[1]), p)
                for p in image_paths
                if int(p.stem.split("_")[1]) in slide_numbers
            ]
        else:
            items = [(i + 1, p) for i, p in enumerate(image_paths)]

        results = []
        for slide_num, img_path in items:
            logger.info(f"Vision-LLM Slide {slide_num} ({provider}/{model})")

            with Timer() as timer:
                b64, media_type = image_to_base64(img_path)
                text = call_fn(b64, media_type, prompt, model=model)

            slide_data = SlideData(
                slide_number=slide_num,
                content=text,
                extraction_method=f"vision-{provider}/{model}",
                extraction_time_seconds=timer.elapsed,
                token_count=estimate_tokens(text),
            )

            # Titel aus Markdown extrahieren
            for line in text.strip().split("\n"):
                s = line.strip()
                if s.startswith("# "):
                    slide_data.title = s[2:].strip()
                    break
                elif s.startswith("**Titel"):
                    # **Titel**: Xyz → Xyz
                    if ":" in s:
                        slide_data.title = s.split(":", 1)[1].strip().strip("*")
                    break

            results.append(slide_data)
            logger.info(
                f"  → {len(text)} Zeichen, {timer.elapsed:.2f}s"
            )

    return results


def extract_vision_images(
    image_paths: list[str | Path],
    provider: Literal["anthropic", "openai"] = "anthropic",
    model: str | None = None,
    prompt_mode: Literal["slide", "invoice"] = "invoice",
) -> list[SlideData]:
    """Extrahiert Text direkt aus Bilddateien (z.B. gescannte Rechnungen).

    Args:
        image_paths: Liste von Bildpfaden
        provider: 'anthropic' oder 'openai'
        model: Modellname
        prompt_mode: 'slide' oder 'invoice'

    Returns:
        Liste von SlideData (slide_number = Index)
    """
    if model is None:
        model = (
            "claude-opus-4-5-20251101" if provider == "anthropic" else "gpt-5.2"
        )

    prompt = INVOICE_PROMPT if prompt_mode == "invoice" else SLIDE_PROMPT
    call_fn = _call_anthropic if provider == "anthropic" else _call_openai

    results = []
    for idx, img_path in enumerate(image_paths, start=1):
        img_path = Path(img_path)
        logger.info(f"Vision-LLM Bild {idx}: {img_path.name}")

        with Timer() as timer:
            b64, media_type = image_to_base64(img_path)
            text = call_fn(b64, media_type, prompt, model=model)

        results.append(SlideData(
            slide_number=idx,
            title=img_path.stem,
            content=text,
            extraction_method=f"vision-{provider}/{model}",
            extraction_time_seconds=timer.elapsed,
            token_count=estimate_tokens(text),
        ))

    return results
