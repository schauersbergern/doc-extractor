#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HANDWRITING_DIR="${HANDWRITING_DIR:-$ROOT_DIR/data/handschrift}"
INVOICES_DIR="${INVOICES_DIR:-$ROOT_DIR/data/rechnungen}"
RESULTS_DIR="${RESULTS_DIR:-$ROOT_DIR/results}"
METHODS="${METHODS:-deepseek,easyocr}"
BACKEND="${BACKEND:-transformers}"
DPI="${DPI:-250}"
QUANTIZE_FLAG="${QUANTIZE_FLAG:---quantize-4bit}"
GROUND_TRUTH_ARG="${GROUND_TRUTH_ARG:-}"

if [[ -n "${1:-}" ]]; then HANDWRITING_DIR="$1"; fi
if [[ -n "${2:-}" ]]; then INVOICES_DIR="$2"; fi
if [[ -n "${3:-}" ]]; then METHODS="$3"; fi

mkdir -p "$HANDWRITING_DIR" "$INVOICES_DIR" "$RESULTS_DIR"

IMG_COUNT="$(find "$HANDWRITING_DIR" -maxdepth 1 -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.tif' -o -iname '*.tiff' -o -iname '*.webp' -o -iname '*.bmp' \) | wc -l | tr -d ' ')"
PDF_COUNT="$(find "$INVOICES_DIR" -maxdepth 1 -type f -iname '*.pdf' | wc -l | tr -d ' ')"

if [[ "$IMG_COUNT" -eq 0 ]]; then
  echo "Keine Handschrift-Bilder in: $HANDWRITING_DIR"
  echo "Erwartet: .png/.jpg/.jpeg/.tif/.tiff/.webp/.bmp"
  exit 1
fi

if [[ "$PDF_COUNT" -eq 0 ]]; then
  echo "Keine Rechnungs-PDFs in: $INVOICES_DIR"
  echo "Erwartet: .pdf"
  exit 1
fi

OUTPUT_MD="$RESULTS_DIR/local_ocr_benchmark.md"

cd "$ROOT_DIR"
source .venv/bin/activate

if [[ "$METHODS" == *"easyocr"* ]]; then
  if ! python3 -c "import easyocr" >/dev/null 2>&1; then
    echo "Fehlt: easyocr"
    echo "Installiere zuerst: pip install -r requirements-local-ocr.txt"
    exit 1
  fi
fi

if [[ "$METHODS" == *"deepseek"* ]]; then
  if ! python3 -c "import torch, transformers, tokenizers" >/dev/null 2>&1; then
    echo "Fehlen DeepSeek-Abhängigkeiten."
    echo "Installiere zuerst: pip install -r requirements-deepseek.txt"
    exit 1
  fi

  if [[ -n "$QUANTIZE_FLAG" ]]; then
    if ! python3 -c "import bitsandbytes, accelerate" >/dev/null 2>&1; then
      echo "Für 4-bit fehlen Abhängigkeiten: bitsandbytes/accelerate"
      echo "Installiere zuerst: pip install -r requirements-deepseek.txt"
      exit 1
    fi
  fi
fi

CMD=(
  python3 extract.py benchmark-local-ocr
  --handwriting-dir "$HANDWRITING_DIR"
  --invoices-dir "$INVOICES_DIR"
  --methods "$METHODS"
  --backend "$BACKEND"
  --dpi "$DPI"
  -o "$OUTPUT_MD"
)

if [[ -n "$QUANTIZE_FLAG" ]]; then
  CMD+=("$QUANTIZE_FLAG")
fi

if [[ -n "$GROUND_TRUTH_ARG" ]]; then
  CMD+=(--ground-truth "$GROUND_TRUTH_ARG")
fi

echo "Starte lokalen OCR-Benchmark..."
echo "Handschrift: $HANDWRITING_DIR ($IMG_COUNT Dateien)"
echo "Rechnungen:  $INVOICES_DIR ($PDF_COUNT PDFs)"
echo "Methoden:    $METHODS"

"${CMD[@]}"

echo
echo "Fertig:"
echo "Report: $OUTPUT_MD"
echo "JSON:   ${OUTPUT_MD%.md}.json"
