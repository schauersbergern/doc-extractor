#!/usr/bin/env python3
"""GLM Invoice OCR + Property Extraction to JSON.

Workflow:
1) PDF -> images -> OCR via local GLM endpoint
2) OCR text -> property extraction via text LLM
3) Write combined JSON report
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure repo root is importable when executed as "python scripts/...py".
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from extractor.glm_ocr import extract_glm_pdf
from extractor.invoice_properties import PROPERTY_KEYS, extract_invoice_properties, normalize_value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GLM OCR on invoice PDFs + LLM property extraction -> JSON"
    )
    parser.add_argument("--input-dir", type=Path, default=Path("data/rechnungen"))
    parser.add_argument("--output", type=Path, default=Path("results/invoice_properties_glm.json"))
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8000/v1")
    parser.add_argument("--model", type=str, default="glm-ocr")
    parser.add_argument("--api-key", type=str, default="EMPTY")
    parser.add_argument("--dpi", type=int, default=140)
    parser.add_argument(
        "--prompt-mode",
        choices=["structured", "markdown", "free", "figure", "describe", "invoice"],
        default="structured",
    )
    parser.add_argument("--llm-provider", choices=["openai", "anthropic"], default="openai")
    parser.add_argument("--llm-model", type=str, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_dir = args.input_dir
    if not input_dir.exists():
        raise FileNotFoundError(f"Ordner nicht gefunden: {input_dir}")

    pdfs = sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
    if not pdfs:
        raise FileNotFoundError(f"Keine PDFs in {input_dir}")

    items: list[dict] = []
    for idx, pdf in enumerate(pdfs, start=1):
        print(f"[{idx}/{len(pdfs)}] Verarbeite {pdf.name} ...", flush=True)

        slides = extract_glm_pdf(
            pdf_path=pdf,
            prompt_mode=args.prompt_mode,
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            dpi=args.dpi,
        )
        ocr_text = "\n\n".join(s.content for s in slides if (s.content or "").strip())
        properties = extract_invoice_properties(
            ocr_text,
            provider=args.llm_provider,
            model=args.llm_model,
        )
        fill_count = sum(1 for key in PROPERTY_KEYS if normalize_value(properties.get(key)))

        items.append(
            {
                "file": str(pdf),
                "pages": len(slides),
                "ocr_text": ocr_text,
                "properties": properties,
                "filled_properties": fill_count,
                "filled_ratio": round(fill_count / len(PROPERTY_KEYS), 4),
            }
        )

    avg_fill_ratio = round(sum(i["filled_ratio"] for i in items) / len(items), 4) if items else 0.0
    result = {
        "method": "glm",
        "task": "invoice_property_extraction",
        "input_dir": str(input_dir),
        "total_files": len(items),
        "ocr": {
            "base_url": args.base_url,
            "model": args.model,
            "api_key": args.api_key,
            "dpi": args.dpi,
            "prompt_mode": args.prompt_mode,
        },
        "llm": {"provider": args.llm_provider, "model": args.llm_model or "(default)"},
        "avg_property_fill_ratio": avg_fill_ratio,
        "items": items,
    }

    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ geschrieben: {output}", flush=True)


if __name__ == "__main__":
    main()
