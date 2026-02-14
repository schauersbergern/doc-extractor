"""Benchmark-Modul: Vergleich DeepSeek OCR 2 vs. GLM-OCR.

Erzeugt strukturierte Vergleichsdaten für die Projektpräsentation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from .models import BenchmarkResult, SlideData, Timer
from .utils import estimate_tokens

logger = logging.getLogger(__name__)

# Kosten pro Bild (geschätzt)
COST_ESTIMATES = {
    "deepseek-ocr2": 0.0,  # Lokal, nur Stromkosten
    "glm-ocr": 0.0,  # Lokal gehostet
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
    deepseek_quantize: bool = False,
    deepseek_backend: Literal["transformers", "vllm"] = "transformers",
) -> list[BenchmarkResult]:
    """Führt Benchmark über DeepSeek OCR 2 und GLM-OCR aus.

    Args:
        pptx_path: Pfad zur PPTX-Datei
        methods: Liste aus {'deepseek', 'glm'}
                 Default: beide Methoden
        slide_numbers: Nur diese Slides benchmarken (1-basiert)
        deepseek_quantize: 4-bit für DeepSeek
        deepseek_backend: Backend für DeepSeek

    Returns:
        Liste von BenchmarkResult pro Methode
    """
    pptx_path = Path(pptx_path)
    if methods is None:
        methods = ["deepseek", "glm"]
    invalid = sorted(set(methods) - {"deepseek", "glm"})
    if invalid:
        raise ValueError(
            f"Ungültige Benchmark-Methoden: {', '.join(invalid)}. "
            "Erlaubt sind nur: deepseek, glm"
        )

    results = []

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

    # === GLM-OCR ===
    if "glm" in methods:
        logger.info("=== Benchmark: GLM-OCR ===")
        from .glm_ocr import extract_glm

        with Timer() as timer:
            slides = extract_glm(
                pptx_path,
                slide_numbers=slide_numbers,
                prompt_mode="structured",
            )

        method = slides[0].extraction_method if slides else "glm-ocr"
        results.append(_make_benchmark_result(
            method=method,
            slides=slides,
            total_time=timer.elapsed,
            gpu_required=True,
            notes="Lokal gehostetes Vision-OCR (OpenAI-kompatibler Endpoint)",
        ))

    return results


def benchmark_images(
    image_paths: list[str | Path],
    methods: list[str] | None = None,
    prompt_mode: Literal["slide", "invoice"] = "invoice",
    deepseek_quantize: bool = False,
) -> list[BenchmarkResult]:
    """Benchmark direkt auf Bilddateien (Rechnungen, Scans).

    Args:
        image_paths: Liste von Bildpfaden
        methods: 'deepseek', 'glm'
        prompt_mode: 'slide' oder 'invoice'
        deepseek_quantize: 4-bit für DeepSeek

    Returns:
        Liste von BenchmarkResult
    """
    if methods is None:
        methods = ["deepseek", "glm"]
    invalid = sorted(set(methods) - {"deepseek", "glm"})
    if invalid:
        raise ValueError(
            f"Ungültige Benchmark-Methoden: {', '.join(invalid)}. "
            "Erlaubt sind nur: deepseek, glm"
        )

    results = []

    if "deepseek" in methods:
        logger.info("=== Benchmark Bilder: DeepSeek OCR 2 ===")
        from .deepseek import extract_deepseek_images

        with Timer() as timer:
            deepseek_prompt_mode = "structured" if prompt_mode in {"slide", "invoice"} else prompt_mode
            slides = extract_deepseek_images(
                image_paths,
                quantize_4bit=deepseek_quantize,
                prompt_mode=deepseek_prompt_mode,
            )

        method = slides[0].extraction_method if slides else "deepseek-ocr2"
        results.append(_make_benchmark_result(
            method=method,
            slides=slides,
            total_time=timer.elapsed,
            gpu_required=True,
            notes=(
                f"Lokal, {'4-bit' if deepseek_quantize else 'volle Präzision'}, "
                f"Modus: {deepseek_prompt_mode}"
            ),
        ))

    if "glm" in methods:
        logger.info("=== Benchmark Bilder: GLM-OCR ===")
        from .glm_ocr import extract_glm_images

        with Timer() as timer:
            glm_prompt_mode = "invoice" if prompt_mode == "invoice" else "structured"
            slides = extract_glm_images(
                image_paths,
                prompt_mode=glm_prompt_mode,
            )

        method = slides[0].extraction_method if slides else "glm-ocr"
        results.append(_make_benchmark_result(
            method=method,
            slides=slides,
            total_time=timer.elapsed,
            gpu_required=True,
            notes=f"Lokal gehostet, Modus: {glm_prompt_mode}",
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
