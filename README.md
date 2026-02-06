# doc-extractor

Dokumentenextraktion aus PowerPoint-Dateien und Bildern mit drei Modi — für Produktion (Dental-Projekt) und Uni-Präsentation (OCR-Benchmark).

## Drei Modi

| Modus | Command | Benötigt | Use Case |
|-------|---------|----------|----------|
| **Direct** | `direct` | Nur CPU | Schnelle Textextraktion aus PPTX |
| **Vision-LLM** | `vision` | API-Key (Anthropic/OpenAI) | Dental-Projekt: Flowcharts, Diagramme semantisch erfassen |
| **DeepSeek OCR 2** | `deepseek` | NVIDIA GPU (8-16GB VRAM) | Uni: Lokale OCR, Rechnungen, DSGVO-konform |

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate

# Je nach Modus:
pip install -r requirements.txt           # Direct only
pip install -r requirements-vision.txt    # + Vision-LLM
pip install -r requirements-deepseek.txt  # + DeepSeek OCR 2
```

### API-Keys per `.env` (empfohlen)

```bash
cp .env.example .env
# .env editieren und echte Keys eintragen

set -a; source .env; set +a
```

### Dental-Projekt (Vision-LLM)

```bash
# Standard-Provider ist anthropic
# Default-Modelle (ohne --model):
#   anthropic -> claude-opus-4-5-20251101
#   openai    -> gpt-5.2
python extract.py vision presentation.pptx --format json

# Ergebnis: presentation_vision.json
# → Enthält pro Slide: Titel, strukturierte Beschreibung, Prozessschritte
# → Direkt verwendbar für Embedding/Vektorisierung
```

### Rechnungen scannen (DeepSeek OCR 2)

```bash
# Einzelne Rechnungen
python extract.py deepseek-img rechnung1.png rechnung2.jpg

# PPTX mit DeepSeek
python extract.py deepseek presentation.pptx --quantize-4bit
```

Wichtig für DeepSeek OCR 2:
- Linux + NVIDIA GPU (CUDA) empfohlen/erforderlich für produktiven Einsatz
- Python 3.12 oder 3.13 verwenden (nicht 3.14)

### Benchmark (Uni-Präsentation)

```bash
# Vergleich aller Methoden auf einer PPTX
python extract.py benchmark presentation.pptx

# Nur Vision vs. DeepSeek auf Rechnungen
python extract.py benchmark-img rechnung1.png rechnung2.jpg

# Nur bestimmte Methoden
python extract.py benchmark presentation.pptx --methods direct,vision --slides 1-5
```

Der Benchmark erzeugt:
- `*_benchmark.md` — Lesbarer Report mit Tabelle
- `*_benchmark.json` — Rohdaten für eigene Auswertung

## Alle Commands

```
extract.py direct      <pptx>              Direkte Textextraktion
extract.py vision      <pptx>              Vision-LLM auf PPTX
extract.py vision-img  <bilder...>         Vision-LLM auf Bilder
extract.py deepseek    <pptx>              DeepSeek OCR 2 auf PPTX
extract.py deepseek-img <bilder...>        DeepSeek OCR 2 auf Bilder
extract.py benchmark   <pptx>              Benchmark PPTX
extract.py benchmark-img <bilder...>       Benchmark Bilder
```

### Gemeinsame Optionen

```
-o, --output PATH          Ausgabedatei
-v, --verbose              Debug-Ausgabe
--format text|json          Ausgabeformat (default: json)
--slides 1,3,5-10          Nur bestimmte Slides
--dpi 200                  Render-Auflösung
```

### Vision-spezifisch

```
--provider anthropic|openai    API-Provider (default: anthropic)
--model <name>                 Modellname (optional, sonst Provider-Default)
--prompt-mode slide|invoice    Prompt-Typ
```

### DeepSeek-spezifisch

```
--quantize-4bit                4-bit (8GB VRAM statt 16GB)
--backend transformers|vllm    Inference-Backend
--prompt-mode structured|free|figure|describe
```

## Ausgabeformat (JSON)

```json
[
  {
    "slide_number": 1,
    "title": "Vom potenziellen Kunden zum Neukunden",
    "content": "## Prozessübersicht\n\nDer Slide zeigt einen dreistufigen...",
    "tables": [],
    "notes": "",
    "_meta": {
      "method": "vision-anthropic/claude-opus-4-5-20251101",
      "time_seconds": 3.241,
      "token_count": 487
    }
  }
]
```

## Architektur

```
doc-extractor/
├── extract.py              # CLI (Subcommands)
├── extractor/
│   ├── __init__.py
│   ├── models.py           # SlideData, TableData, BenchmarkResult
│   ├── utils.py            # Slide-Rendering, Base64, Token-Schätzung
│   ├── direct.py           # Modus 1: PPTX-XML Extraktion
│   ├── vision.py           # Modus 2: Vision-LLM (Claude/GPT)
│   ├── deepseek.py         # Modus 3: DeepSeek OCR 2
│   └── benchmark.py        # Vergleichs-Framework
├── requirements.txt
├── requirements-vision.txt
└── requirements-deepseek.txt
```

## Voraussetzungen

### LibreOffice (für Vision & DeepSeek Modi)

Wird benötigt um PPTX-Slides als Bilder zu rendern:

```bash
sudo apt install libreoffice          # Ubuntu
brew install --cask libreoffice       # macOS
```

### Poppler (für `pdf2image` in Vision/DeepSeek)

`pdf2image` benötigt `pdfinfo` und `pdftoppm` (Poppler):

```bash
sudo apt install poppler-utils        # Ubuntu
brew install poppler                  # macOS
```

### NVIDIA GPU (nur DeepSeek)

- Minimum: 8GB VRAM mit `--quantize-4bit`
- Empfohlen: 16GB VRAM für volle Präzision
- CUDA 11.8+
- OS: Linux empfohlen
- Python: 3.12 oder 3.13 (nicht 3.14)

## Hinweise

- **Vision-LLM ist für Flowcharts/Diagramme deutlich überlegen** gegenüber reiner OCR, da es semantische Beziehungen erfasst statt nur Text zu extrahieren.
- **DeepSeek OCR 2 glänzt bei strukturierten Dokumenten** (Rechnungen, Formulare, Tabellen) — hier ist die Layouterkennung mit dem `<|grounding|>`-Tag stark.
- **Die `model.infer()` API** von DeepSeek OCR 2 basiert auf der aktuellen Dokumentation (Jan 2026). Falls sich das Interface ändert, muss `deepseek.py` → `_infer_transformers()` angepasst werden.
- **Für den Benchmark** empfiehlt es sich, identische Dokumente mit beiden Methoden zu verarbeiten und die JSON-Outputs nebeneinander zu vergleichen.
