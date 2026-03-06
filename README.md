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
| `direct` | `python3 extract.py direct <pptx>` | Schnelle XML-Textextraktion |
| `vision` | `python3 extract.py vision <pptx>` | Vision-LLM auf PPTX |
| `vision-ppts` | `python3 extract.py vision-ppts [ppts]` | Vision-LLM auf alle gaengigen Formate im Ordner |
| `deepseek` | `python3 extract.py deepseek <pptx>` | Lokale OCR mit DeepSeek OCR 2 |
| `deepseek-pdf` | `python3 extract.py deepseek-pdf <pdf>` | PDF -> Bilder -> Markdown (DeepSeek OCR 2) |
| `deepseek-invoices` | `python3 extract.py deepseek-invoices [ordner]` | Rechnungs-PDFs -> OCR + LLM-Properties als JSON |
| `glm` | `python3 extract.py glm <pptx>` | Lokale OCR via GLM-OCR Endpoint |
| `glm-pdf` | `python3 extract.py glm-pdf <pdf>` | PDF -> Bilder -> Markdown (GLM-OCR) |

## Installation

```bash
python3 -m venv .venv && source .venv/bin/activate

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
python3 extract.py benchmark presentation.pptx

# PPTX mit Markdown-Prompt (pptx -> image -> markdown)
python3 extract.py benchmark presentation.pptx --prompt-mode markdown

# PDF -> Bilder -> Markdown
python3 extract.py benchmark-pdf rechnung.pdf

# Bilder/Rechnungen
python3 extract.py benchmark-img rechnung1.png rechnung2.jpg

# Methoden explizit
python3 extract.py benchmark presentation.pptx --methods deepseek,glm
```

Outputs:
- `*_benchmark.md`
- `*_benchmark.json`

## PDF -> Image -> Markdown (DeepSeek/GLM)

```bash
# DeepSeek OCR 2 (Markdown-Output)
python3 extract.py deepseek-pdf data/rechnung.pdf --prompt-mode markdown -o results/rechnung_deepseek.md

# GLM-OCR (Markdown-Output)
python3 extract.py glm-pdf data/rechnung.pdf --prompt-mode markdown -o results/rechnung_glm.md
```

## PPTX -> Image -> Markdown (DeepSeek/GLM)

```bash
# DeepSeek OCR 2 auf PPTX als Markdown
python3 extract.py deepseek data/praesentation.pptx --prompt-mode markdown --format markdown -o results/praesentation_deepseek.md

# GLM-OCR auf PPTX als Markdown
python3 extract.py glm data/praesentation.pptx --prompt-mode markdown --format markdown -o results/praesentation_glm.md
```

## Rechnungs-Scan Pipeline

Im lokalen OCR-Benchmark fuer Rechnungen:
1. OCR-Text pro PDF-Seite (DeepSeek oder GLM)
2. **LLM-basierte Property-Extraktion** (`extractor/invoice_properties.py`)
3. Optionales Ground-Truth Matching

Wichtig: Regex-Heuristik wurde durch LLM-Extraktion ersetzt.

Direktlauf (DeepSeek-only, JSON-Output pro Rechnung inkl. Properties):
```bash
python3 extract.py deepseek-invoices data/rechnungen \
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
python3 extract.py vision-ppts ppts \
  --provider openai \
  --prompt-mode slide \
  --vector-ready-output results/ppts_vector_ready.md \
  --only-vector-ready
```

Dieser Befehl verarbeitet alle unterstuetzten Dokumente im Ordner `ppts` und schreibt nur das finale Vector-Ready-Markdown nach `results/ppts_vector_ready.md`.

Wichtig:
- `.json` Dateien werden nicht verarbeitet, weil nur unterstuetzte Office-, PDF- und Bildformate eingesammelt werden.
- Ohne `--only-vector-ready` wird zusaetzlich ein Rohoutput (`ppts_vision.json` oder `-o ...`) geschrieben.
- Fuer Unterordner kann `--recursive` verwendet werden.

Unterstuetzte Formate:
- Office: `.ppt`, `.pptx`, `.odp`, `.doc`, `.docx`, `.odt`, `.rtf`, `.xls`, `.xlsx`, `.ods`
- PDF: `.pdf`
- Bilder: `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.webp`, `.bmp`, `.gif`

Ablauf:
1. Dateien im `ppts` Ordner erkennen
2. Alles in Bilder umwandeln
3. Vision-LLM OCR
4. Finaler Endtext fuer Vektorisierung
5. Alle `vector_ready_text` Inhalte in einer Markdown-Datei zusammenfassen

## Lokaler OCR-Benchmark (Handschrift + Rechnungs-PDF)

```bash
python3 extract.py benchmark-local-ocr \
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
python3 extract.py direct <pptx>
python3 extract.py vision <pptx>
python3 extract.py vision-img <bilder...>
python3 extract.py vision-ppts [ppts] [--vector-ready-output <datei.md>] [--only-vector-ready]
python3 extract.py deepseek <pptx>
python3 extract.py deepseek-img <bilder...>
python3 extract.py deepseek-pdf <pdf>
python3 extract.py deepseek-invoices [ordner]
python3 extract.py glm <pptx>
python3 extract.py glm-img <bilder...>
python3 extract.py glm-pdf <pdf>
python3 extract.py benchmark <pptx>
python3 extract.py benchmark-img <bilder...>
python3 extract.py benchmark-pdf <pdf>
python3 extract.py benchmark-local-ocr
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
