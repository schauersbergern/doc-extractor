"""Benchmark-Modul: Vergleich Vision-LLM vs. DeepSeek OCR 2.

Erzeugt strukturierte Vergleichsdaten für die Projektpräsentation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from .models import BenchmarkResult, SlideData, Timer
from .utils import estimate_tokens

logger = logging.getLogger(__name__)

# Kosten pro Bild (geschätzt)
COST_ESTIMATES = {
    "direct": 0.0,
    "vision-anthropic/claude-sonnet-4-20250514": 0.012,
    "vision-anthropic/claude-haiku-4-5-20251001": 0.003,
    "vision-openai/gpt-4o": 0.015,
    "vision-openai/gpt-4o-mini": 0.003,
    "deepseek-ocr2": 0.0,  # Lokal, nur Stromkosten
}


def _make_benchmark_result(
    method: str,
    slides: list[SlideData],
    total_time: float,
    gpu_required: bool = False,
    notes: str = "",
) -> BenchmarkResult:
    """Erstellt ein BenchmarkResult aus extrahierten Slides."""
    total_chars = sum(len(s.content) for s in slides)
    total_tokens = sum(s.token_count or estimate_tokens(s.content) for s in slides)

    # Kosten schätzen
    cost_key = method.split("/")[0] if "/" in method else method
    per_image_cost = 0.0
    for key, val in COST_ESTIMATES.items():
        if key in method:
            per_image_cost = val
            break
    estimated_cost = per_image_cost * len(slides)

    return BenchmarkResult(
        method=method,
        total_slides=len(slides),
        total_time_seconds=total_time,
        avg_time_per_slide=total_time / len(slides) if slides else 0,
        total_chars=total_chars,
        total_tokens_estimate=total_tokens,
        slides=slides,
        estimated_cost_usd=estimated_cost,
        gpu_required=gpu_required,
        notes=notes,
    )


def benchmark_pptx(
    pptx_path: str | Path,
    methods: list[str] | None = None,
    slide_numbers: list[int] | None = None,
    vision_provider: Literal["anthropic", "openai"] = "anthropic",
    deepseek_quantize: bool = False,
    deepseek_backend: Literal["transformers", "vllm"] = "transformers",
) -> list[BenchmarkResult]:
    """Führt Benchmark über mehrere Extraktionsmethoden aus.

    Args:
        pptx_path: Pfad zur PPTX-Datei
        methods: Liste von Methoden: 'direct', 'vision', 'deepseek'
                 Default: alle verfügbaren
        slide_numbers: Nur diese Slides benchmarken (1-basiert)
        vision_provider: Provider für Vision-LLM
        deepseek_quantize: 4-bit für DeepSeek
        deepseek_backend: Backend für DeepSeek

    Returns:
        Liste von BenchmarkResult pro Methode
    """
    pptx_path = Path(pptx_path)
    if methods is None:
        methods = ["direct", "vision", "deepseek"]

    results = []

    # === Direct ===
    if "direct" in methods:
        logger.info("=== Benchmark: Direkte Extraktion ===")
        from .direct import extract_direct

        with Timer() as timer:
            slides = extract_direct(pptx_path, slide_numbers=slide_numbers)

        results.append(_make_benchmark_result(
            method="direct",
            slides=slides,
            total_time=timer.elapsed,
            gpu_required=False,
            notes="Nur Text aus XML-Shapes, kein Layout-Kontext",
        ))

    # === Vision LLM ===
    if "vision" in methods:
        logger.info(f"=== Benchmark: Vision-LLM ({vision_provider}) ===")
        from .vision import extract_vision

        with Timer() as timer:
            slides = extract_vision(
                pptx_path,
                slide_numbers=slide_numbers,
                provider=vision_provider,
            )

        model = slides[0].extraction_method if slides else f"vision-{vision_provider}"
        results.append(_make_benchmark_result(
            method=model,
            slides=slides,
            total_time=timer.elapsed,
            gpu_required=False,
            notes="Cloud-API, semantische Interpretation, Layout-Verständnis",
        ))

    # === DeepSeek OCR 2 ===
    if "deepseek" in methods:
        logger.info("=== Benchmark: DeepSeek OCR 2 ===")
        from .deepseek import extract_deepseek

        with Timer() as timer:
            slides = extract_deepseek(
                pptx_path,
                slide_numbers=slide_numbers,
                quantize_4bit=deepseek_quantize,
                backend=deepseek_backend,
            )

        method = slides[0].extraction_method if slides else "deepseek-ocr2"
        results.append(_make_benchmark_result(
            method=method,
            slides=slides,
            total_time=timer.elapsed,
            gpu_required=True,
            notes=f"Lokal, {'4-bit' if deepseek_quantize else 'volle Präzision'}, "
                  f"DSGVO-konform",
        ))

    return results


def benchmark_images(
    image_paths: list[str | Path],
    methods: list[str] | None = None,
    vision_provider: Literal["anthropic", "openai"] = "anthropic",
    prompt_mode: Literal["slide", "invoice"] = "invoice",
    deepseek_quantize: bool = False,
) -> list[BenchmarkResult]:
    """Benchmark direkt auf Bilddateien (Rechnungen, Scans).

    Args:
        image_paths: Liste von Bildpfaden
        methods: 'vision', 'deepseek' (kein 'direct' möglich)
        vision_provider: Provider für Vision-LLM
        prompt_mode: 'slide' oder 'invoice'
        deepseek_quantize: 4-bit für DeepSeek

    Returns:
        Liste von BenchmarkResult
    """
    if methods is None:
        methods = ["vision", "deepseek"]

    results = []

    if "vision" in methods:
        logger.info(f"=== Benchmark Bilder: Vision-LLM ({vision_provider}) ===")
        from .vision import extract_vision_images

        with Timer() as timer:
            slides = extract_vision_images(
                image_paths,
                provider=vision_provider,
                prompt_mode=prompt_mode,
            )

        method = slides[0].extraction_method if slides else f"vision-{vision_provider}"
        results.append(_make_benchmark_result(
            method=method,
            slides=slides,
            total_time=timer.elapsed,
            gpu_required=False,
            notes=f"Cloud-API, Modus: {prompt_mode}",
        ))

    if "deepseek" in methods:
        logger.info("=== Benchmark Bilder: DeepSeek OCR 2 ===")
        from .deepseek import extract_deepseek_images

        with Timer() as timer:
            slides = extract_deepseek_images(
                image_paths,
                quantize_4bit=deepseek_quantize,
            )

        method = slides[0].extraction_method if slides else "deepseek-ocr2"
        results.append(_make_benchmark_result(
            method=method,
            slides=slides,
            total_time=timer.elapsed,
            gpu_required=True,
            notes=f"Lokal, {'4-bit' if deepseek_quantize else 'volle Präzision'}",
        ))

    return results


def format_benchmark_report(results: list[BenchmarkResult]) -> str:
    """Erzeugt einen lesbaren Benchmark-Report (Markdown)."""
    lines = ["# Benchmark-Report: Dokumentenextraktion\n"]

    # Zusammenfassungstabelle
    lines.append("## Zusammenfassung\n")
    lines.append("| Methode | Slides | Zeit (s) | ø/Slide (s) | Zeichen | Tokens | Kosten (USD) | GPU |")
    lines.append("|---------|--------|----------|-------------|---------|--------|--------------|-----|")

    for r in results:
        gpu = "✓" if r.gpu_required else "✗"
        cost = f"${r.estimated_cost_usd:.4f}" if r.estimated_cost_usd > 0 else "lokal"
        lines.append(
            f"| {r.method} | {r.total_slides} | "
            f"{r.total_time_seconds:.2f} | {r.avg_time_per_slide:.3f} | "
            f"{r.total_chars} | {r.total_tokens_estimate} | {cost} | {gpu} |"
        )

    # Detail pro Methode
    lines.append("\n## Details pro Methode\n")

    for r in results:
        lines.append(f"### {r.method}\n")
        lines.append(f"- **Notizen**: {r.notes}")
        lines.append(f"- **Gesamtzeit**: {r.total_time_seconds:.2f}s")
        lines.append(f"- **Durchsatz**: {r.avg_time_per_slide:.3f}s/Slide\n")

        # Slide-Details
        for slide in r.slides[:3]:  # Max 3 Slides als Preview
            preview = slide.content[:200].replace("\n", " ")
            lines.append(f"**Slide {slide.slide_number}** ({len(slide.content)} Zeichen):")
            lines.append(f"> {preview}...\n")

        if len(r.slides) > 3:
            lines.append(f"*... und {len(r.slides) - 3} weitere Slides*\n")

    return "\n".join(lines)
