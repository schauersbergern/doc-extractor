# doc-extractor

Dokumentenextraktion fuer PowerPoint, PDFs, Office-Dateien und Bilder.

Aktueller Fokus:
- Benchmark nur noch **DeepSeek OCR 2** vs. **GLM-OCR**
- Rechnungs-Properties via **LLM** (keine Regex-Heuristik)
- Finaler **Post-Processing Schritt** fuer vektorisierungsbereiten Endtext (Handschrift + PowerPoint)
- Vision-Ordnerworkflow fuer `ppts` mit gaengigen Dateiformaten

## Modi

| Modus | Command | Use Case |
|---|---|---|
| `direct` | `extract.py direct <pptx>` | Schnelle XML-Textextraktion |
| `vision` | `extract.py vision <pptx>` | Vision-LLM auf PPTX |
| `vision-ppts` | `extract.py vision-ppts [ppts]` | Vision-LLM auf alle gaengigen Formate im Ordner |
| `deepseek` | `extract.py deepseek <pptx>` | Lokale OCR mit DeepSeek OCR 2 |
| `deepseek-pdf` | `extract.py deepseek-pdf <pdf>` | PDF -> Bilder -> Markdown (DeepSeek OCR 2) |
| `deepseek-invoices` | `extract.py deepseek-invoices [ordner]` | Rechnungs-PDFs -> OCR + LLM-Properties als JSON |
| `glm` | `extract.py glm <pptx>` | Lokale OCR via GLM-OCR Endpoint |
| `glm-pdf` | `extract.py glm-pdf <pdf>` | PDF -> Bilder -> Markdown (GLM-OCR) |

## Installation

```bash
python -m venv .venv && source .venv/bin/activate

# Basis
pip install -r requirements.txt

# Vision (OpenAI/Anthropic SDKs)
pip install -r requirements-vision.txt

# DeepSeek OCR 2
pip install -r requirements-deepseek.txt

# Lokaler OCR-Benchmark (DeepSeek + GLM + LLM-Property/Post-Processing)
pip install -r requirements-local-ocr.txt
```

## API Keys und GLM Endpoint

```bash
cp .env.example .env
set -a; source .env; set +a
```

Zusatzvariablen fuer GLM:
- `GLM_OCR_BASE_URL` (Default: `http://127.0.0.1:8000/v1`)
- `GLM_OCR_MODEL` (Default: `glm-ocr`)
- `GLM_OCR_API_KEY` (Default: `EMPTY`)

## GLM-OCR lokal (README Option 2)

Lokal gehosteter OpenAI-kompatibler Endpoint, wie in [GLM-OCR](https://github.com/zai-org/GLM-OCR/tree/main):

```bash
# in der GLM-OCR Umgebung
vllm serve zai-org/GLM-OCR-9B --served-model-name glm-ocr --trust-remote-code
```

Danach kann dieses Repo mit `extract.py glm ...` bzw. Benchmarks gegen den lokalen Endpoint laufen.

## Benchmark (nur DeepSeek vs GLM)

```bash
# PPTX
python extract.py benchmark presentation.pptx

# PPTX mit Markdown-Prompt (pptx -> image -> markdown)
python extract.py benchmark presentation.pptx --prompt-mode markdown

# PDF -> Bilder -> Markdown
python extract.py benchmark-pdf rechnung.pdf

# Bilder/Rechnungen
python extract.py benchmark-img rechnung1.png rechnung2.jpg

# Methoden explizit
python extract.py benchmark presentation.pptx --methods deepseek,glm
```

Outputs:
- `*_benchmark.md`
- `*_benchmark.json`

## PDF -> Image -> Markdown (DeepSeek/GLM)

```bash
# DeepSeek OCR 2 (Markdown-Output)
python extract.py deepseek-pdf data/rechnung.pdf --prompt-mode markdown -o results/rechnung_deepseek.md

# GLM-OCR (Markdown-Output)
python extract.py glm-pdf data/rechnung.pdf --prompt-mode markdown -o results/rechnung_glm.md
```

## PPTX -> Image -> Markdown (DeepSeek/GLM)

```bash
# DeepSeek OCR 2 auf PPTX als Markdown
python extract.py deepseek data/praesentation.pptx --prompt-mode markdown --format markdown -o results/praesentation_deepseek.md

# GLM-OCR auf PPTX als Markdown
python extract.py glm data/praesentation.pptx --prompt-mode markdown --format markdown -o results/praesentation_glm.md
```

## Rechnungs-Scan Pipeline

Im lokalen OCR-Benchmark fuer Rechnungen:
1. OCR-Text pro PDF-Seite (DeepSeek oder GLM)
2. **LLM-basierte Property-Extraktion** (`extractor/invoice_properties.py`)
3. Optionales Ground-Truth Matching

Wichtig: Regex-Heuristik wurde durch LLM-Extraktion ersetzt.

Direktlauf (DeepSeek-only, JSON-Output pro Rechnung inkl. Properties):
```bash
python extract.py deepseek-invoices data/rechnungen \
  --backend transformers \
  --prompt-mode structured \
  -o results/invoice_properties_deepseek.json
```

## Finaler Post-Processing Schritt (Vektorisierung)

Fuer Handschrift und PowerPoint wird ein finaler LLM-Transformationsschritt ausgefuehrt:
- Handschrift: OCR-Rauschen normalisieren, sauberen Endtext erzeugen
- PowerPoint: Prozesse/Diagramme in detaillierte textuelle Prozessbeschreibung ueberfuehren

Der Endtext liegt im JSON als `vector_ready_text`.

Deaktivieren (bei Commands mit Post-Processing):
```bash
--no-post-process
```

## Vision auf `ppts` Ordner mit Multi-Format-Erkennung

```bash
python extract.py vision-ppts ppts --provider openai --prompt-mode slide
```

Unterstuetzte Formate:
- Office: `.ppt`, `.pptx`, `.odp`, `.doc`, `.docx`, `.odt`, `.rtf`, `.xls`, `.xlsx`, `.ods`
- PDF: `.pdf`
- Bilder: `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.webp`, `.bmp`, `.gif`

Ablauf:
1. Dateien im `ppts` Ordner erkennen
2. Alles in Bilder umwandeln
3. Vision-LLM OCR
4. Finaler Endtext fuer Vektorisierung

## Lokaler OCR-Benchmark (Handschrift + Rechnungs-PDF)

```bash
python extract.py benchmark-local-ocr \
  --handwriting-dir data/handschrift \
  --invoices-dir data/rechnungen \
  --methods deepseek,glm \
  --quantize-4bit \
  --llm-provider openai \
  -o results/local_ocr_benchmark.md
```

Oder:
```bash
./scripts/run_local_benchmark.sh
```

## Commands

```text
extract.py direct <pptx>
extract.py vision <pptx>
extract.py vision-img <bilder...>
extract.py vision-ppts [ppts]
extract.py deepseek <pptx>
extract.py deepseek-img <bilder...>
extract.py deepseek-pdf <pdf>
extract.py deepseek-invoices [ordner]
extract.py glm <pptx>
extract.py glm-img <bilder...>
extract.py glm-pdf <pdf>
extract.py benchmark <pptx>
extract.py benchmark-img <bilder...>
extract.py benchmark-pdf <pdf>
extract.py benchmark-local-ocr
```

## Systemvoraussetzungen

- LibreOffice CLI (`soffice`) fuer Office->PDF
- Poppler (`pdfinfo`, `pdftoppm`) fuer PDF->Bilder
- NVIDIA GPU fuer DeepSeek OCR 2 (Linux empfohlen)

Beispiele:
```bash
brew install --cask libreoffice
brew install poppler
```
