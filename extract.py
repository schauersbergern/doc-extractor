#!/usr/bin/env python3
"""doc-extractor: Dokumentenextraktion fuer Vektorisierung und OCR-Benchmark.

Modi:
    direct      - Direkte Textextraktion aus PPTX (schnell, kein GPU)
    vision      - Vision-LLM (Claude/GPT) fuer semantische Interpretation
    deepseek    - DeepSeek OCR 2 fuer lokale OCR (GPU)
    glm         - GLM-OCR ueber lokalen OpenAI-kompatiblen Endpoint

Benchmark:
    deepseek OCR 2 vs. glm-OCR
"""

from __future__ import annotations

import argparse
import json
import logging
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
        content = json.dumps([s.to_dict() for s in slides], ensure_ascii=False, indent=2)
    else:
        parts = [s.to_text(include_notes=include_notes) for s in slides]
        content = "\n\n---\n\n".join(parts) + "\n"

    output_path.write_text(content, encoding="utf-8")
    logging.getLogger(__name__).info(f"Geschrieben: {output_path}")


def _extract_source_file(slide) -> str:
    notes = (slide.notes or "").strip()
    marker = "source_file="
    for line in notes.splitlines():
        line = line.strip()
        if line.startswith(marker):
            return line[len(marker):].strip()
    return ""


def _write_vector_ready_markdown(slides, output_path: Path) -> Path:
    """Schreibt alle Vector-Ready-Texte aus vision-ppts in eine Markdown-Datei."""
    if output_path.suffix:
        md_path = output_path.with_name(f"{output_path.stem}_vector_ready.md")
    else:
        md_path = output_path.with_name(f"{output_path.name}_vector_ready.md")

    grouped: dict[str, list] = {}
    for slide in slides:
        source = _extract_source_file(slide) or "unbekanntes_dokument"
        grouped.setdefault(source, []).append(slide)

    lines = ["# Vector-Ready Gesamttext", ""]
    for source, source_slides in grouped.items():
        source_name = Path(source).name if source else "unbekanntes_dokument"
        lines.append(f"## Dokument: {source_name}")
        lines.append("")
        for slide in source_slides:
            lines.append(f"### {slide.title or f'Slide {slide.slide_number}'}")
            lines.append("")
            text = (slide.vector_ready_text or slide.content or "").strip()
            lines.append(text if text else "_(kein Text)_")
            lines.append("")

    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    logging.getLogger(__name__).info(f"Geschrieben: {md_path}")
    return md_path


def _post_process_if_enabled(args, slides, source_type: str):
    """Finalen Vektor-Post-Processing-Schritt anwenden (optional abschaltbar)."""
    if getattr(args, "no_post_process", False):
        return slides

    from extractor.post_processing import post_process_slides_for_vector_db

    return post_process_slides_for_vector_db(
        slides,
        source_type=source_type,
        provider=args.llm_provider,
        model=args.llm_model,
    )


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
    print(f"✓ {len(slides)} Slides -> {output}")


def cmd_vision(args):
    """Modus 2: Vision-LLM auf PPTX."""
    from extractor.vision import extract_vision

    slides = extract_vision(
        args.input,
        slide_numbers=parse_slide_range(args.slides) if args.slides else None,
        provider=args.provider,
        model=args.model,
        prompt_mode=args.prompt_mode,
        dpi=args.dpi,
    )
    slides = _post_process_if_enabled(args, slides, source_type="powerpoint")

    ext = ".json" if args.format == "json" else ".txt"
    output = args.output or args.input.with_name(f"{args.input.stem}_vision{ext}")
    _write_output(slides, output, args.format)
    print(f"✓ {len(slides)} Slides -> {output}")


def cmd_vision_img(args):
    """Vision-LLM auf Einzelbilder."""
    from extractor.vision import extract_vision_images

    slides = extract_vision_images(
        args.images,
        provider=args.provider,
        model=args.model,
        prompt_mode=args.prompt_mode,
    )
    if args.post_process_type:
        slides = _post_process_if_enabled(args, slides, source_type=args.post_process_type)

    output = args.output or Path("vision_output.json")
    _write_output(slides, output, "json")
    print(f"✓ {len(slides)} Bilder -> {output}")


def cmd_vision_ppts(args):
    """Vision-LLM auf allen gaengigen Dateiformaten im ppts-Ordner."""
    from extractor.vision import extract_vision_documents

    slides = extract_vision_documents(
        args.input_dir,
        provider=args.provider,
        model=args.model,
        prompt_mode=args.prompt_mode,
        dpi=args.dpi,
        recursive=args.recursive,
    )
    slides = _post_process_if_enabled(args, slides, source_type="powerpoint")

    output = args.output or Path("ppts_vision.json")
    _write_output(slides, output, args.format)
    vector_md = _write_vector_ready_markdown(slides, output)
    print(f"✓ {len(slides)} Seiten/Slides aus {args.input_dir} -> {output}")
    print(f"✓ Vector-Ready Markdown -> {vector_md}")


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
    slides = _post_process_if_enabled(args, slides, source_type="powerpoint")

    ext = ".json" if args.format == "json" else ".txt"
    output = args.output or args.input.with_name(f"{args.input.stem}_deepseek{ext}")
    _write_output(slides, output, args.format)
    print(f"✓ {len(slides)} Slides -> {output}")


def cmd_deepseek_img(args):
    """DeepSeek OCR 2 auf Einzelbilder."""
    from extractor.deepseek import extract_deepseek_images

    slides = extract_deepseek_images(
        args.images,
        quantize_4bit=args.quantize_4bit,
        prompt_mode=args.prompt_mode,
        backend=args.backend,
    )
    if args.post_process_type:
        slides = _post_process_if_enabled(args, slides, source_type=args.post_process_type)

    output = args.output or Path("deepseek_output.json")
    _write_output(slides, output, "json")
    print(f"✓ {len(slides)} Bilder -> {output}")


def cmd_glm(args):
    """Modus 4: GLM-OCR auf PPTX."""
    from extractor.glm_ocr import extract_glm

    slides = extract_glm(
        args.input,
        slide_numbers=parse_slide_range(args.slides) if args.slides else None,
        prompt_mode=args.prompt_mode,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        dpi=args.dpi,
    )
    slides = _post_process_if_enabled(args, slides, source_type="powerpoint")

    ext = ".json" if args.format == "json" else ".txt"
    output = args.output or args.input.with_name(f"{args.input.stem}_glm{ext}")
    _write_output(slides, output, args.format)
    print(f"✓ {len(slides)} Slides -> {output}")


def cmd_glm_img(args):
    """GLM-OCR auf Einzelbilder."""
    from extractor.glm_ocr import extract_glm_images

    slides = extract_glm_images(
        args.images,
        prompt_mode=args.prompt_mode,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
    )
    if args.post_process_type:
        slides = _post_process_if_enabled(args, slides, source_type=args.post_process_type)

    output = args.output or Path("glm_output.json")
    _write_output(slides, output, "json")
    print(f"✓ {len(slides)} Bilder -> {output}")


def cmd_benchmark(args):
    """Benchmark: DeepSeek OCR 2 vs. GLM-OCR auf PPTX."""
    from extractor.benchmark import benchmark_pptx, format_benchmark_report

    methods = args.methods.split(",") if args.methods else None
    results = benchmark_pptx(
        args.input,
        methods=methods,
        slide_numbers=parse_slide_range(args.slides) if args.slides else None,
        deepseek_quantize=args.quantize_4bit,
        deepseek_backend=args.backend,
    )

    report = format_benchmark_report(results)
    report_path = args.output or args.input.with_name(f"{args.input.stem}_benchmark.md")
    report_path.write_text(report, encoding="utf-8")

    json_path = report_path.with_suffix(".json")
    json_data = {
        "file": str(args.input),
        "results": [r.to_dict() for r in results],
        "slides": {r.method: [s.to_dict() for s in r.slides] for r in results},
    }
    json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(report)
    print(f"{'=' * 60}")
    print(f"\nReport:  {report_path}")
    print(f"Daten:   {json_path}")


def cmd_benchmark_img(args):
    """Benchmark: DeepSeek OCR 2 vs. GLM-OCR auf Einzelbildern."""
    from extractor.benchmark import benchmark_images, format_benchmark_report

    methods = args.methods.split(",") if args.methods else None
    results = benchmark_images(
        args.images,
        methods=methods,
        prompt_mode=args.prompt_mode,
        deepseek_quantize=args.quantize_4bit,
    )

    report = format_benchmark_report(results)
    report_path = args.output or Path("benchmark_images.md")
    report_path.write_text(report, encoding="utf-8")

    json_path = report_path.with_suffix(".json")
    json_data = {"images": [str(p) for p in args.images], "results": [r.to_dict() for r in results]}
    json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(report)
    print(f"{'=' * 60}")
    print(f"\nReport:  {report_path}")
    print(f"Daten:   {json_path}")


def cmd_benchmark_local_ocr(args):
    """Benchmark: DeepSeek OCR 2 vs. GLM-OCR auf Handschrift + Rechnungs-PDF."""
    from extractor.local_benchmark import format_local_benchmark_report, run_local_ocr_benchmark

    methods = args.methods.split(",") if args.methods else None
    result = run_local_ocr_benchmark(
        handwriting_dir=args.handwriting_dir,
        invoices_dir=args.invoices_dir,
        methods=methods,
        deepseek_quantize=args.quantize_4bit,
        deepseek_backend=args.backend,
        dpi=args.dpi,
        ground_truth_json=args.ground_truth,
        llm_provider=args.llm_provider,
        llm_model=args.llm_model,
    )

    report = format_local_benchmark_report(result)
    report_path = args.output or Path("benchmark_local_ocr.md")
    report_path.write_text(report, encoding="utf-8")

    json_path = report_path.with_suffix(".json")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

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

    llm_common = argparse.ArgumentParser(add_help=False)
    llm_common.add_argument("--llm-provider", choices=["openai", "anthropic"], default="openai")
    llm_common.add_argument("--llm-model", type=str, default=None)

    post_process_common = argparse.ArgumentParser(add_help=False)
    post_process_common.add_argument(
        "--no-post-process",
        action="store_true",
        help="Finalen LLM-Transformationsschritt fuer Vektorisierung deaktivieren",
    )

    img_post_process_common = argparse.ArgumentParser(add_help=False)
    img_post_process_common.add_argument(
        "--post-process-type",
        choices=["powerpoint", "handwriting"],
        default=None,
        help="Optionaler finaler LLM-Transformationsschritt fuer Bildkommandos",
    )

    vision_common = argparse.ArgumentParser(add_help=False)
    vision_common.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    vision_common.add_argument("--model", type=str, default=None)
    vision_common.add_argument("--prompt-mode", choices=["slide", "invoice"], default="slide")

    deepseek_common = argparse.ArgumentParser(add_help=False)
    deepseek_common.add_argument("--quantize-4bit", action="store_true")
    deepseek_common.add_argument("--backend", choices=["transformers", "vllm"], default="transformers")
    deepseek_prompt_common = argparse.ArgumentParser(add_help=False)
    deepseek_prompt_common.add_argument(
        "--prompt-mode",
        choices=["structured", "free", "figure", "describe"],
        default="structured",
    )

    glm_common = argparse.ArgumentParser(add_help=False)
    glm_common.add_argument(
        "--prompt-mode",
        choices=["structured", "free", "figure", "describe", "invoice"],
        default="structured",
    )
    glm_common.add_argument("--model", type=str, default=None, help="Default: GLM_OCR_MODEL oder glm-ocr")
    glm_common.add_argument("--base-url", type=str, default=None, help="Default: GLM_OCR_BASE_URL")
    glm_common.add_argument("--api-key", type=str, default=None, help="Default: GLM_OCR_API_KEY oder EMPTY")

    benchmark_img_mode = argparse.ArgumentParser(add_help=False)
    benchmark_img_mode.add_argument("--prompt-mode", choices=["slide", "invoice"], default="invoice")

    # --- Subcommands ---
    p = sub.add_parser("direct", parents=[pptx_common], help="Direkte Textextraktion")
    p.add_argument("--include-notes", action="store_true")
    p.set_defaults(func=cmd_direct)

    p = sub.add_parser(
        "vision",
        parents=[pptx_common, vision_common, llm_common, post_process_common],
        help="Vision-LLM (Claude/GPT) auf PPTX",
    )
    p.set_defaults(func=cmd_vision)

    p = sub.add_parser(
        "vision-img",
        parents=[img_common, vision_common, llm_common, post_process_common, img_post_process_common],
        help="Vision-LLM auf Bilder",
    )
    p.set_defaults(func=cmd_vision_img)

    p = sub.add_parser(
        "vision-ppts",
        parents=[vision_common, llm_common, post_process_common],
        help="Vision-LLM auf alle gaengigen Dateiformate im ppts-Ordner",
    )
    p.add_argument("input_dir", type=Path, nargs="?", default=Path("ppts"), help="Input-Ordner (Default: ppts)")
    p.add_argument("--recursive", action="store_true", help="Dateien rekursiv verarbeiten")
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--format", choices=["text", "json"], default="json")
    p.add_argument("-o", "--output", type=Path, default=None)
    p.set_defaults(func=cmd_vision_ppts)

    p = sub.add_parser(
        "deepseek",
        parents=[pptx_common, deepseek_common, deepseek_prompt_common, llm_common, post_process_common],
        help="DeepSeek OCR 2 auf PPTX",
    )
    p.set_defaults(func=cmd_deepseek)

    p = sub.add_parser(
        "deepseek-img",
        parents=[
            img_common,
            deepseek_common,
            deepseek_prompt_common,
            llm_common,
            post_process_common,
            img_post_process_common,
        ],
        help="DeepSeek OCR 2 auf Bilder",
    )
    p.set_defaults(func=cmd_deepseek_img)

    p = sub.add_parser(
        "glm",
        parents=[pptx_common, glm_common, llm_common, post_process_common],
        help="GLM-OCR auf PPTX",
    )
    p.set_defaults(func=cmd_glm)

    p = sub.add_parser(
        "glm-img",
        parents=[img_common, glm_common, llm_common, post_process_common, img_post_process_common],
        help="GLM-OCR auf Bilder",
    )
    p.set_defaults(func=cmd_glm_img)

    p = sub.add_parser(
        "benchmark",
        parents=[pptx_common, deepseek_common],
        help="Benchmark: DeepSeek OCR 2 vs. GLM-OCR auf PPTX",
        conflict_handler="resolve",
    )
    p.add_argument("--methods", type=str, default=None, help="z.B. deepseek,glm")
    p.set_defaults(func=cmd_benchmark)

    p = sub.add_parser(
        "benchmark-img",
        parents=[img_common, deepseek_common, benchmark_img_mode],
        help="Benchmark: DeepSeek OCR 2 vs. GLM-OCR auf Bilder",
        conflict_handler="resolve",
    )
    p.add_argument("--methods", type=str, default=None, help="z.B. deepseek,glm")
    p.set_defaults(func=cmd_benchmark_img)

    p = sub.add_parser(
        "benchmark-local-ocr",
        parents=[llm_common],
        help="Lokaler OCR-Benchmark: DeepSeek OCR 2 vs. GLM-OCR",
    )
    p.add_argument("--quantize-4bit", action="store_true")
    p.add_argument("--backend", choices=["transformers", "vllm"], default="transformers")
    p.add_argument("--handwriting-dir", type=Path, required=True, help="Ordner mit Handschrift-Bildern")
    p.add_argument("--invoices-dir", type=Path, required=True, help="Ordner mit Rechnungs-PDFs")
    p.add_argument("--methods", type=str, default="deepseek,glm", help="z.B. deepseek,glm")
    p.add_argument("--ground-truth", type=Path, default=None, help="JSON mit Soll-Properties pro PDF")
    p.add_argument("--dpi", type=int, default=250)
    p.add_argument("-o", "--output", type=Path, default=None)
    p.set_defaults(func=cmd_benchmark_local_ocr)

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    args.func(args)


if __name__ == "__main__":
    main()
