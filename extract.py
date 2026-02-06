#!/usr/bin/env python3
"""doc-extractor: Dokumentenextraktion für Vektorisierung und OCR-Benchmark.

Drei Modi:
    direct   — Direkte Textextraktion aus PPTX (schnell, kein GPU)
    vision   — Vision-LLM (Claude/GPT-4o) für semantische Interpretation
    deepseek — DeepSeek OCR 2 für lokale OCR (GPU)

Plus: Benchmark-Modus für Vergleich der Methoden.

Beispiele:
    # Dental-Projekt: Vision-LLM auf Thorstens Slides
    python extract.py vision presentation.pptx

    # Rechnungen scannen mit DeepSeek OCR 2
    python extract.py deepseek-img rechnung1.png rechnung2.jpg

    # Benchmark: Vision vs. DeepSeek auf gleichen Slides
    python extract.py benchmark presentation.pptx

    # Benchmark: Rechnungen vergleichen
    python extract.py benchmark-img rechnung1.png rechnung2.jpg
"""

import argparse
import json
import logging
import sys
from pathlib import Path


def parse_slide_range(spec: str) -> list[int]:
    """Parst '1,3,5-10' zu [1,3,5,6,7,8,9,10]."""
    slides = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            slides.update(range(int(start), int(end) + 1))
        else:
            slides.add(int(part))
    return sorted(slides)


def _write_output(slides, output_path: Path, fmt: str, include_notes: bool = False):
    """Schreibt Extraktionsergebnis in Datei."""
    if fmt == "json":
        content = json.dumps(
            [s.to_dict() for s in slides],
            ensure_ascii=False,
            indent=2,
        )
    else:
        parts = [s.to_text(include_notes=include_notes) for s in slides]
        content = "\n\n---\n\n".join(parts) + "\n"

    output_path.write_text(content, encoding="utf-8")
    logging.getLogger(__name__).info(f"Geschrieben: {output_path}")


def cmd_direct(args):
    """Modus 1: Direkte Extraktion."""
    from extractor.direct import extract_direct

    slides = extract_direct(
        args.input,
        slide_numbers=parse_slide_range(args.slides) if args.slides else None,
        include_notes=args.include_notes,
    )

    ext = ".json" if args.format == "json" else ".txt"
    output = args.output or args.input.with_suffix(ext)
    _write_output(slides, output, args.format, args.include_notes)
    print(f"✓ {len(slides)} Slides → {output}")


def cmd_vision(args):
    """Modus 2: Vision-LLM."""
    from extractor.vision import extract_vision

    slides = extract_vision(
        args.input,
        slide_numbers=parse_slide_range(args.slides) if args.slides else None,
        provider=args.provider,
        model=args.model,
        prompt_mode=args.prompt_mode,
        dpi=args.dpi,
    )

    ext = ".json" if args.format == "json" else ".txt"
    output = args.output or args.input.with_name(f"{args.input.stem}_vision{ext}")
    _write_output(slides, output, args.format)
    print(f"✓ {len(slides)} Slides → {output}")


def cmd_vision_img(args):
    """Vision-LLM auf Einzelbilder (Rechnungen)."""
    from extractor.vision import extract_vision_images

    slides = extract_vision_images(
        args.images,
        provider=args.provider,
        model=args.model,
        prompt_mode=args.prompt_mode,
    )

    output = args.output or Path("vision_output.json")
    _write_output(slides, output, "json")
    print(f"✓ {len(slides)} Bilder → {output}")


def cmd_deepseek(args):
    """Modus 3: DeepSeek OCR 2 auf PPTX."""
    from extractor.deepseek import extract_deepseek

    slides = extract_deepseek(
        args.input,
        slide_numbers=parse_slide_range(args.slides) if args.slides else None,
        quantize_4bit=args.quantize_4bit,
        prompt_mode=args.prompt_mode,
        backend=args.backend,
        dpi=args.dpi,
    )

    ext = ".json" if args.format == "json" else ".txt"
    output = args.output or args.input.with_name(f"{args.input.stem}_deepseek{ext}")
    _write_output(slides, output, args.format)
    print(f"✓ {len(slides)} Slides → {output}")


def cmd_deepseek_img(args):
    """DeepSeek OCR 2 auf Einzelbilder."""
    from extractor.deepseek import extract_deepseek_images

    slides = extract_deepseek_images(
        args.images,
        quantize_4bit=args.quantize_4bit,
        prompt_mode=args.prompt_mode,
        backend=args.backend,
    )

    output = args.output or Path("deepseek_output.json")
    _write_output(slides, output, "json")
    print(f"✓ {len(slides)} Bilder → {output}")


def cmd_benchmark(args):
    """Benchmark: Vergleich aller Methoden auf PPTX."""
    from extractor.benchmark import benchmark_pptx, format_benchmark_report

    methods = args.methods.split(",") if args.methods else None

    results = benchmark_pptx(
        args.input,
        methods=methods,
        slide_numbers=parse_slide_range(args.slides) if args.slides else None,
        vision_provider=args.provider,
        deepseek_quantize=args.quantize_4bit,
        deepseek_backend=args.backend,
    )

    # Report
    report = format_benchmark_report(results)
    report_path = args.output or args.input.with_name(f"{args.input.stem}_benchmark.md")
    report_path.write_text(report, encoding="utf-8")

    # JSON-Daten
    json_path = report_path.with_suffix(".json")
    json_data = {
        "file": str(args.input),
        "results": [r.to_dict() for r in results],
        "slides": {
            r.method: [s.to_dict() for s in r.slides]
            for r in results
        },
    }
    json_path.write_text(
        json.dumps(json_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n{'=' * 60}")
    print(report)
    print(f"{'=' * 60}")
    print(f"\nReport:  {report_path}")
    print(f"Daten:   {json_path}")


def cmd_benchmark_img(args):
    """Benchmark: Vergleich auf Einzelbildern (Rechnungen)."""
    from extractor.benchmark import benchmark_images, format_benchmark_report

    methods = args.methods.split(",") if args.methods else None

    results = benchmark_images(
        args.images,
        methods=methods,
        vision_provider=args.provider,
        prompt_mode=args.prompt_mode,
        deepseek_quantize=args.quantize_4bit,
    )

    report = format_benchmark_report(results)
    report_path = args.output or Path("benchmark_images.md")
    report_path.write_text(report, encoding="utf-8")

    json_path = report_path.with_suffix(".json")
    json_data = {
        "images": [str(p) for p in args.images],
        "results": [r.to_dict() for r in results],
    }
    json_path.write_text(
        json.dumps(json_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n{'=' * 60}")
    print(report)
    print(f"{'=' * 60}")
    print(f"\nReport:  {report_path}")
    print(f"Daten:   {json_path}")


def main():
    parser = argparse.ArgumentParser(
        description="doc-extractor: Dokumentenextraktion & OCR-Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    # --- Gemeinsame Argumente ---
    pptx_common = argparse.ArgumentParser(add_help=False)
    pptx_common.add_argument("input", type=Path, help="PPTX-Datei")
    pptx_common.add_argument("-o", "--output", type=Path, default=None)
    pptx_common.add_argument("--slides", type=str, default=None, help="z.B. 1,3,5-10")
    pptx_common.add_argument("--format", choices=["text", "json"], default="json")
    pptx_common.add_argument("--dpi", type=int, default=200)

    img_common = argparse.ArgumentParser(add_help=False)
    img_common.add_argument("images", type=Path, nargs="+", help="Bilddateien")
    img_common.add_argument("-o", "--output", type=Path, default=None)

    vision_common = argparse.ArgumentParser(add_help=False)
    vision_common.add_argument(
        "--provider", choices=["anthropic", "openai"], default="anthropic"
    )
    vision_common.add_argument("--model", type=str, default=None)
    vision_common.add_argument(
        "--prompt-mode", choices=["slide", "invoice"], default="slide"
    )

    deepseek_common = argparse.ArgumentParser(add_help=False)
    deepseek_common.add_argument("--quantize-4bit", action="store_true")
    deepseek_common.add_argument(
        "--backend", choices=["transformers", "vllm"], default="transformers"
    )
    deepseek_common.add_argument(
        "--prompt-mode",
        choices=["structured", "free", "figure", "describe"],
        default="structured",
    )

    # --- Subcommands ---
    p = sub.add_parser("direct", parents=[pptx_common], help="Direkte Textextraktion")
    p.add_argument("--include-notes", action="store_true")
    p.set_defaults(func=cmd_direct)

    p = sub.add_parser(
        "vision", parents=[pptx_common, vision_common],
        help="Vision-LLM (Claude/GPT-4o)",
    )
    p.set_defaults(func=cmd_vision)

    p = sub.add_parser(
        "vision-img", parents=[img_common, vision_common],
        help="Vision-LLM auf Bilder (Rechnungen)",
    )
    p.set_defaults(func=cmd_vision_img)

    p = sub.add_parser(
        "deepseek", parents=[pptx_common, deepseek_common],
        help="DeepSeek OCR 2 auf PPTX",
    )
    p.set_defaults(func=cmd_deepseek)

    p = sub.add_parser(
        "deepseek-img", parents=[img_common, deepseek_common],
        help="DeepSeek OCR 2 auf Bilder",
    )
    p.set_defaults(func=cmd_deepseek_img)

    p = sub.add_parser(
        "benchmark",
        parents=[pptx_common, vision_common, deepseek_common],
        help="Benchmark: alle Methoden auf PPTX",
        conflict_handler="resolve",
    )
    p.add_argument("--methods", type=str, default=None, help="z.B. direct,vision")
    p.set_defaults(func=cmd_benchmark)

    p = sub.add_parser(
        "benchmark-img",
        parents=[img_common, vision_common, deepseek_common],
        help="Benchmark: Methoden auf Bilder",
        conflict_handler="resolve",
    )
    p.add_argument("--methods", type=str, default=None, help="z.B. vision,deepseek")
    p.set_defaults(func=cmd_benchmark_img)

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    args.func(args)


if __name__ == "__main__":
    main()
