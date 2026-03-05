# Runpod Working Guide (Validated)

Stand: 2026-03-04  
Validiert auf Runpod A40 (48 GB VRAM), 1 GPU.

Diese Anleitung dokumentiert nur die Konfigurationen und Commands, die in der Session tatsaechlich funktioniert haben.

## 1) Voraussetzungen

Im Pod:

```bash
cd /workspace/doc-extractor
python3 -m venv .venv
source .venv/bin/activate

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y git poppler-utils libreoffice

python -m pip install -U pip
python -m pip install -r requirements-local-ocr.txt
python -m pip install torchvision
```

Wichtig fuer GLM-OCR:

```bash
python -m pip install -U --pre vllm --torch-backend=auto --extra-index-url https://wheels.vllm.ai/nightly
python -m pip install -U "git+https://github.com/huggingface/transformers.git"
```

## 2) Input-Ordner (funktionierend)

```text
data/handschrift   # PNG/JPG/... fuer Handschrift
data/rechnungen    # PDFs
data/pptx          # PPTX
```

## 3) Wichtige Erkenntnisse aus dem Lauf

- `zai-org/GLM-OCR-9B` hat nicht funktioniert (404/401).  
  Funktionierende Model-ID: `zai-org/GLM-OCR`.
- `benchmark-local-ocr` benoetigt ein Text-LLM fuer Postprocessing/Property-Extraktion.  
  Deshalb muss `OPENAI_API_KEY` gesetzt sein.
- DeepSeek und GLM nicht gleichzeitig auf derselben GPU laufen lassen (VRAM-Konflikte).
- Fuer GLM waren reduzierte Bildgroessen/DPI noetig (sonst `encoder cache size` Fehler).

## 4) DeepSeek-Run (funktionierend)

Vorher sicherstellen, dass kein GLM-vLLM-Server laeuft:

```bash
pkill -9 -f "vllm serve zai-org/GLM-OCR" || true
```

Benchmark (DeepSeek-only, funktionierend):

```bash
cd /workspace/doc-extractor
source .venv/bin/activate
export OPENAI_API_KEY="<DEIN_KEY>"

python3 extract.py benchmark-local-ocr \
  --handwriting-dir data/handschrift \
  --invoices-dir data/rechnungen \
  --methods deepseek \
  --backend vllm \
  -o results/local_ocr_benchmark_deepseek.md
```

## 5) GLM-Server (funktionierend)

```bash
cd /workspace/doc-extractor
source .venv/bin/activate

vllm serve zai-org/GLM-OCR \
  --served-model-name glm-ocr \
  --host 0.0.0.0 \
  --port 8000 \
  --gpu-memory-utilization 0.70 \
  --max-model-len 8192 \
  --limit-mm-per-prompt '{"image": 16}'
```

Healthcheck:

```bash
ss -ltnp | grep 8000
curl -s http://127.0.0.1:8000/v1/models
```

Smoke-Test:

```bash
python3 extract.py glm-img data/handschrift/a01-003x.png \
  --base-url http://127.0.0.1:8000/v1 \
  --model glm-ocr \
  --api-key EMPTY \
  -o results/glm_smoke.json
```

## 6) GLM Benchmark-Run (funktionierend)

Fuer `benchmark-local-ocr --methods glm` mussten die Handschrift-Bilder verkleinert werden:

```bash
cd /workspace/doc-extractor
source .venv/bin/activate
mkdir -p data/handschrift_glm_small

python3 - <<'PY'
from pathlib import Path
from PIL import Image

src = Path("data/handschrift")
dst = Path("data/handschrift_glm_small")
dst.mkdir(parents=True, exist_ok=True)

for p in src.iterdir():
    if not p.is_file() or p.suffix.lower() not in {".png",".jpg",".jpeg",".tif",".tiff",".webp",".bmp"}:
        continue
    img = Image.open(p).convert("RGB")
    max_side = 1200
    if max(img.size) > max_side:
        scale = max_side / max(img.size)
        img = img.resize((int(img.width*scale), int(img.height*scale)), Image.LANCZOS)
    img.save(dst / (p.stem + ".png"), "PNG")
print("done")
PY
```

Danach:

```bash
python3 extract.py benchmark-local-ocr \
  --handwriting-dir data/handschrift_glm_small \
  --invoices-dir data/rechnungen \
  --methods glm \
  --dpi 140 \
  -o results/local_ocr_benchmark_glm.md
```

## 7) PDF -> Image -> Markdown (GLM, funktionierend)

```bash
cd /workspace/doc-extractor
source .venv/bin/activate

for f in data/rechnungen/*.pdf; do
  [ -e "$f" ] || continue
  b="$(basename "$f" .pdf)"
  python3 extract.py glm-pdf "$f" \
    --base-url http://127.0.0.1:8000/v1 \
    --model glm-ocr \
    --api-key EMPTY \
    --prompt-mode markdown \
    --dpi 140 \
    -o "results/${b}_glm.md"
done
```

## 8) PPTX -> Image -> Markdown (GLM, funktionierend)

```bash
cd /workspace/doc-extractor
source .venv/bin/activate

for f in data/pptx/*.pptx; do
  [ -e "$f" ] || continue
  b="$(basename "$f" .pptx)"
  python3 extract.py glm "$f" \
    --base-url http://127.0.0.1:8000/v1 \
    --model glm-ocr \
    --api-key EMPTY \
    --prompt-mode markdown \
    --format markdown \
    --dpi 120 \
    -o "results/${b}_glm.md"
done
```

## 9) Ergebnisse lokal ziehen (SCP)

Auf dem lokalen Rechner:

```bash
scp -i ~/.ssh/id_ed25519 -P <RUNPOD_PORT> -r \
  root@<RUNPOD_IP>:/workspace/doc-extractor/results \
  ./results_from_runpod
```

## 10) Bekannte Fehlerbilder und Fix

- `OPENAI_API_KEY nicht gesetzt`  
  -> `export OPENAI_API_KEY="..."`.

- `Poppler fehlt (pdfinfo/pdftoppm nicht gefunden)`  
  -> `apt-get install -y poppler-utils`.

- `Connection refused` bei GLM  
  -> GLM-Server laeuft nicht / abgestuerzt; Logs pruefen, Server im Vordergrund starten.

- `model type glm_ocr not recognized`  
  -> vLLM nightly + transformers aus GitHub installieren.

- `image item length ... exceeds pre-allocated encoder cache size`  
  -> GLM mit `--limit-mm-per-prompt '{"image": 16}'` starten und/oder DPI/Bildgroesse reduzieren.

- `Free memory ... less than desired GPU memory utilization`  
  -> DeepSeek und GLM nicht parallel starten; Prozesse trennen.

