"""Lokales OCR mit EasyOCR (zweites Modell für Benchmark gegen DeepSeek)."""

from __future__ import annotations

import logging
from pathlib import Path

from .models import SlideData, Timer
from .utils import estimate_tokens

logger = logging.getLogger(__name__)

_reader_cache: dict[tuple[tuple[str, ...], bool], object] = {}


def _get_reader(languages: list[str] | None = None, gpu: bool = False):
    if languages is None:
        languages = ["de", "en"]

    key = (tuple(languages), gpu)
    if key in _reader_cache:
        return _reader_cache[key]

    try:
        import easyocr
    except ImportError:
        raise ImportError(
            "EasyOCR nicht installiert.\n"
            "Installiere mit: pip install easyocr"
        )

    reader = easyocr.Reader(languages, gpu=gpu)
    _reader_cache[key] = reader
    return reader


def extract_easyocr_images(
    image_paths: list[str | Path],
    languages: list[str] | None = None,
    gpu: bool = False,
) -> list[SlideData]:
    """OCR auf Bilddateien via EasyOCR."""
    reader = _get_reader(languages=languages, gpu=gpu)
    results: list[SlideData] = []

    for idx, image_path in enumerate(image_paths, start=1):
        img = Path(image_path)
        if not img.exists():
            raise FileNotFoundError(f"Bild nicht gefunden: {img}")

        logger.info(f"EasyOCR Bild {idx}: {img.name}")
        with Timer() as timer:
            parts = reader.readtext(str(img), detail=0, paragraph=True)
            text = "\n".join(p.strip() for p in parts if str(p).strip())

        results.append(
            SlideData(
                slide_number=idx,
                title=img.stem,
                content=text,
                extraction_method="easyocr-local",
                extraction_time_seconds=timer.elapsed,
                token_count=estimate_tokens(text),
            )
        )

    return results
