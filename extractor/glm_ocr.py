"""GLM-OCR Extraktion ueber einen lokal gehosteten OpenAI-kompatiblen Endpoint.

Empfohlene lokale Installation laut GLM-OCR README (Option 2):
    vllm serve zai-org/GLM-OCR-9B --served-model-name glm-ocr --trust-remote-code
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Literal

from .models import SlideData, Timer
from .utils import estimate_tokens, image_to_base64, pptx_to_images

logger = logging.getLogger(__name__)

DEFAULT_GLM_BASE_URL = os.environ.get("GLM_OCR_BASE_URL", "http://127.0.0.1:8000/v1")
DEFAULT_GLM_MODEL = os.environ.get("GLM_OCR_MODEL", "glm-ocr")
DEFAULT_GLM_API_KEY = os.environ.get("GLM_OCR_API_KEY", "EMPTY")

PROMPTS = {
    "structured": (
        "Extract all visible text from this document image and preserve layout in Markdown. "
        "Include headings, tables, bullets, and labels."
    ),
    "free": "Transcribe all visible text as plain text. Keep line breaks where useful.",
    "figure": (
        "Analyze the diagram/figure and produce a detailed textual process description, "
        "including nodes, transitions, conditions, and dependencies."
    ),
    "describe": (
        "Describe this document image in detail for semantic retrieval. Include structure, "
        "entities, relations, and key facts."
    ),
    "invoice": (
        "Extract this invoice/document as structured Markdown with sender, recipient, "
        "invoice numbers/dates, line items, totals, and payment details."
    ),
}


def _call_glm_ocr(
    image_b64: str,
    media_type: str,
    prompt: str,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> str:
    """Ruft GLM-OCR ueber OpenAI-kompatible API auf."""
    try:
        import openai
    except ImportError:
        raise ImportError("openai SDK fehlt: pip install openai")

    resolved_model = model or DEFAULT_GLM_MODEL
    resolved_base_url = (base_url or DEFAULT_GLM_BASE_URL).rstrip("/")
    resolved_api_key = api_key or DEFAULT_GLM_API_KEY

    client = openai.OpenAI(
        api_key=resolved_api_key,
        base_url=f"{resolved_base_url}/",
    )

    response = client.chat.completions.create(
        model=resolved_model,
        temperature=0.0,
        max_completion_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_b64}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ],
    )

    return (response.choices[0].message.content or "").strip()


def extract_glm(
    pptx_path: str | Path,
    slide_numbers: list[int] | None = None,
    prompt_mode: Literal["structured", "free", "figure", "describe", "invoice"] = "structured",
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    dpi: int = 200,
) -> list[SlideData]:
    """Extrahiert Text aus PPTX via lokalem GLM-OCR Endpoint."""
    pptx_path = Path(pptx_path)
    if not pptx_path.exists():
        raise FileNotFoundError(f"Nicht gefunden: {pptx_path}")

    prompt = PROMPTS.get(prompt_mode, PROMPTS["structured"])

    with tempfile.TemporaryDirectory(prefix="glm_ocr_") as tmp:
        tmp_path = Path(tmp)
        image_paths = pptx_to_images(pptx_path, tmp_path / "slides", dpi=dpi)

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
            logger.info(f"GLM-OCR Slide {slide_num}: {img_path.name}")

            with Timer() as timer:
                b64, media_type = image_to_base64(img_path)
                text = _call_glm_ocr(
                    b64,
                    media_type,
                    prompt=prompt,
                    model=model,
                    base_url=base_url,
                    api_key=api_key,
                )

            results.append(
                SlideData(
                    slide_number=slide_num,
                    content=text,
                    extraction_method=f"glm-ocr/{model or DEFAULT_GLM_MODEL}/{prompt_mode}",
                    extraction_time_seconds=timer.elapsed,
                    token_count=estimate_tokens(text),
                )
            )

    return results


def extract_glm_images(
    image_paths: list[str | Path],
    prompt_mode: Literal["structured", "free", "figure", "describe", "invoice"] = "structured",
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> list[SlideData]:
    """Extrahiert Text direkt aus Bilddateien via GLM-OCR."""
    prompt = PROMPTS.get(prompt_mode, PROMPTS["structured"])
    resolved_model = model or DEFAULT_GLM_MODEL

    results = []
    for idx, image_path in enumerate(image_paths, start=1):
        img_path = Path(image_path)
        if not img_path.exists():
            raise FileNotFoundError(f"Bild nicht gefunden: {img_path}")

        logger.info(f"GLM-OCR Bild {idx}: {img_path.name}")
        with Timer() as timer:
            b64, media_type = image_to_base64(img_path)
            text = _call_glm_ocr(
                b64,
                media_type,
                prompt=prompt,
                model=resolved_model,
                base_url=base_url,
                api_key=api_key,
            )

        results.append(
            SlideData(
                slide_number=idx,
                title=img_path.stem,
                content=text,
                extraction_method=f"glm-ocr/{resolved_model}/{prompt_mode}",
                extraction_time_seconds=timer.elapsed,
                token_count=estimate_tokens(text),
            )
        )

    return results
