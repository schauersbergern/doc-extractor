#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT_DIR="${INPUT_DIR:-$ROOT_DIR/data/rechnungen}"
OUTPUT_JSON="${OUTPUT_JSON:-$ROOT_DIR/results/invoice_properties_glm.json}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000/v1}"
MODEL_NAME="${MODEL_NAME:-glm-ocr}"
API_KEY="${API_KEY:-EMPTY}"
DPI="${DPI:-140}"
PROMPT_MODE="${PROMPT_MODE:-structured}"
LLM_PROVIDER="${LLM_PROVIDER:-openai}"
LLM_MODEL="${LLM_MODEL:-}"

cd "$ROOT_DIR"
source .venv/bin/activate

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  python3 scripts/extract_glm_invoice_properties.py --help
  exit 0
fi

mkdir -p "$(dirname "$OUTPUT_JSON")"

CMD=(
  python3 scripts/extract_glm_invoice_properties.py
  --input-dir "$INPUT_DIR"
  --output "$OUTPUT_JSON"
  --base-url "$BASE_URL"
  --model "$MODEL_NAME"
  --api-key "$API_KEY"
  --dpi "$DPI"
  --prompt-mode "$PROMPT_MODE"
  --llm-provider "$LLM_PROVIDER"
)

if [[ -n "$LLM_MODEL" ]]; then
  CMD+=(--llm-model "$LLM_MODEL")
fi

echo "Starte GLM Invoice Property Extraction..."
echo "Input:  $INPUT_DIR"
echo "Output: $OUTPUT_JSON"
echo "GLM:    $BASE_URL ($MODEL_NAME)"
echo "LLM:    $LLM_PROVIDER ${LLM_MODEL:-'(default)'}"

"${CMD[@]}"
