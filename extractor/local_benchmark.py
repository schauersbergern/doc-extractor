"""Lokaler OCR-Benchmark: DeepSeek OCR 2 vs. EasyOCR."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .easyocr_local import extract_easyocr_images
from .invoice_properties import PROPERTY_KEYS, extract_invoice_properties, normalize_value
from .models import Timer
from .utils import pdf_to_images

logger = logging.getLogger(__name__)


def _collect_files(folder: Path, suffixes: tuple[str, ...]) -> list[Path]:
    if not folder.exists():
        raise FileNotFoundError(f"Ordner nicht gefunden: {folder}")
    files = [p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() in suffixes]
    if not files:
        raise FileNotFoundError(f"Keine passenden Dateien in {folder} für {suffixes}")
    return files


def _ocr_handwriting(images: list[Path], model: str, deepseek_quantize: bool, deepseek_backend: str) -> dict:
    if model == "deepseek":
        from .deepseek import extract_deepseek_images

        with Timer() as timer:
            slides = extract_deepseek_images(
                images,
                quantize_4bit=deepseek_quantize,
                backend=deepseek_backend,
                prompt_mode="free",
            )
    elif model == "easyocr":
        with Timer() as timer:
            slides = extract_easyocr_images(images, languages=["de", "en"], gpu=True)
    else:
        raise ValueError(f"Unbekanntes Modell: {model}")

    return {
        "model": model,
        "total_items": len(slides),
        "total_time_seconds": round(timer.elapsed, 3),
        "avg_time_seconds": round(timer.elapsed / len(slides), 3) if slides else 0.0,
        "items": [
            {
                "file": str(images[i]),
                "text": s.content,
                "chars": len(s.content),
                "tokens_estimate": s.token_count,
            }
            for i, s in enumerate(slides)
        ],
    }


def _ocr_pdf_text(pdf_path: Path, model: str, deepseek_quantize: bool, deepseek_backend: str, dpi: int) -> str:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="invoice_pdf_") as tmp:
        page_images = pdf_to_images(pdf_path, Path(tmp) / "pages", dpi=dpi)

        if model == "deepseek":
            from .deepseek import extract_deepseek_images

            slides = extract_deepseek_images(
                page_images,
                quantize_4bit=deepseek_quantize,
                backend=deepseek_backend,
                prompt_mode="structured",
            )
        elif model == "easyocr":
            slides = extract_easyocr_images(page_images, languages=["de", "en"], gpu=True)
        else:
            raise ValueError(f"Unbekanntes Modell: {model}")

    return "\n\n".join(s.content for s in slides if s.content.strip())


def _score_against_ground_truth(pred: dict, truth: dict) -> dict:
    total = 0
    hits = 0
    per_key = {}
    for key in PROPERTY_KEYS:
        if key not in truth:
            continue
        total += 1
        p = normalize_value(pred.get(key, ""))
        t = normalize_value(truth.get(key, ""))
        ok = bool(p) and p.lower() == t.lower()
        hits += 1 if ok else 0
        per_key[key] = {"pred": p, "truth": t, "exact_match": ok}

    return {
        "evaluated_fields": total,
        "exact_matches": hits,
        "exact_match_rate": round(hits / total, 4) if total else None,
        "per_key": per_key,
    }


def run_local_ocr_benchmark(
    handwriting_dir: Path,
    invoices_dir: Path,
    methods: list[str] | None = None,
    deepseek_quantize: bool = True,
    deepseek_backend: str = "transformers",
    dpi: int = 250,
    ground_truth_json: Path | None = None,
) -> dict:
    """Benchmarkt zwei lokale OCR-Modelle auf Handschrift + Rechnungs-PDFs."""
    if methods is None:
        methods = ["deepseek", "easyocr"]

    images = _collect_files(handwriting_dir, (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"))
    pdfs = _collect_files(invoices_dir, (".pdf",))

    truth_data = {}
    if ground_truth_json:
        truth_data = json.loads(Path(ground_truth_json).read_text(encoding="utf-8"))

    result = {
        "inputs": {
            "handwriting_dir": str(handwriting_dir),
            "invoices_dir": str(invoices_dir),
            "handwriting_files": [str(p) for p in images],
            "invoice_files": [str(p) for p in pdfs],
        },
        "methods": methods,
        "handwriting": {},
        "invoices": {},
    }

    for model in methods:
        logger.info(f"=== Handschrift Benchmark: {model} ===")
        result["handwriting"][model] = _ocr_handwriting(
            images=images,
            model=model,
            deepseek_quantize=deepseek_quantize,
            deepseek_backend=deepseek_backend,
        )

        logger.info(f"=== Rechnungs Benchmark: {model} ===")
        rows = []
        with Timer() as timer:
            for pdf in pdfs:
                text = _ocr_pdf_text(
                    pdf_path=pdf,
                    model=model,
                    deepseek_quantize=deepseek_quantize,
                    deepseek_backend=deepseek_backend,
                    dpi=dpi,
                )
                props = extract_invoice_properties(text)
                fill_count = sum(1 for k in PROPERTY_KEYS if normalize_value(props.get(k)))
                row = {
                    "file": str(pdf),
                    "ocr_text": text,
                    "properties": props,
                    "filled_properties": fill_count,
                    "filled_ratio": round(fill_count / len(PROPERTY_KEYS), 4),
                }

                truth = truth_data.get(pdf.name) or truth_data.get(str(pdf))
                if truth:
                    row["ground_truth_eval"] = _score_against_ground_truth(props, truth)

                rows.append(row)

        result["invoices"][model] = {
            "total_items": len(rows),
            "total_time_seconds": round(timer.elapsed, 3),
            "avg_time_seconds": round(timer.elapsed / len(rows), 3) if rows else 0.0,
            "avg_property_fill_ratio": round(
                sum(r["filled_ratio"] for r in rows) / len(rows), 4
            ) if rows else 0.0,
            "items": rows,
        }

    return result


def format_local_benchmark_report(data: dict) -> str:
    """Markdown-Report für den kombinierten lokalen OCR-Benchmark."""
    lines = ["# Lokaler OCR-Benchmark: DeepSeek OCR 2 vs. EasyOCR", ""]

    lines.append("## Inputs")
    lines.append(f"- Handschrift-Ordner: `{data['inputs']['handwriting_dir']}`")
    lines.append(f"- Rechnungs-Ordner: `{data['inputs']['invoices_dir']}`")
    lines.append(f"- Handschrift-Dateien: {len(data['inputs']['handwriting_files'])}")
    lines.append(f"- Rechnungs-PDFs: {len(data['inputs']['invoice_files'])}")
    lines.append("")

    lines.append("## Handschrift (OCR)")
    lines.append("| Modell | Dateien | Zeit gesamt (s) | Ø pro Datei (s) |")
    lines.append("|---|---:|---:|---:|")
    for model, res in data["handwriting"].items():
        lines.append(
            f"| {model} | {res['total_items']} | {res['total_time_seconds']:.3f} | {res['avg_time_seconds']:.3f} |"
        )
    lines.append("")

    lines.append("## Rechnungen (Property-Extraktion)")
    lines.append("| Modell | PDFs | Zeit gesamt (s) | Ø pro PDF (s) | Ø Füllgrad Properties |")
    lines.append("|---|---:|---:|---:|---:|")
    for model, res in data["invoices"].items():
        lines.append(
            f"| {model} | {res['total_items']} | {res['total_time_seconds']:.3f} | "
            f"{res['avg_time_seconds']:.3f} | {res['avg_property_fill_ratio']:.2%} |"
        )
    lines.append("")

    lines.append("## Hinweise")
    lines.append("- Der Füllgrad misst nur, wie viele Felder befüllt wurden, nicht deren Korrektheit.")
    lines.append("- Für Qualitätsvergleich `ground_truth_json` mit Sollwerten pro PDF verwenden.")
    lines.append("")

    return "\n".join(lines)
