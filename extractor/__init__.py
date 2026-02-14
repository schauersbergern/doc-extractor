"""doc-extractor: PPTX/Dokumentenextraktion mit mehreren Modi.

Modus 1 (direct):   Direkte XML-Textextraktion — schnell, kein GPU
Modus 2 (vision):   Vision-LLM (Claude/GPT-4o) — semantisch, Cloud
Modus 3 (deepseek): DeepSeek OCR 2 — lokal, DSGVO, GPU
Modus 4 (glm):      GLM-OCR — lokal gehosteter Vision-OCR Endpoint
"""

from .models import SlideData, TableData, BenchmarkResult
from .direct import extract_direct

__all__ = [
    "SlideData",
    "TableData",
    "BenchmarkResult",
    "extract_direct",
]

# Vision — braucht anthropic/openai SDK
try:
    from .vision import extract_vision, extract_vision_images
    __all__.extend(["extract_vision", "extract_vision_images"])
except ImportError:
    pass

# DeepSeek — braucht torch, transformers
try:
    from .deepseek import extract_deepseek, extract_deepseek_images
    __all__.extend(["extract_deepseek", "extract_deepseek_images"])
except ImportError:
    pass

# GLM-OCR — braucht openai SDK + laufenden lokalen Endpoint
try:
    from .glm_ocr import extract_glm, extract_glm_images
    __all__.extend(["extract_glm", "extract_glm_images"])
except ImportError:
    pass

# Benchmark
try:
    from .benchmark import benchmark_pptx, benchmark_images, format_benchmark_report
    __all__.extend(["benchmark_pptx", "benchmark_images", "format_benchmark_report"])
except ImportError:
    pass

# Lokaler OCR-Benchmark
try:
    from .local_benchmark import run_local_ocr_benchmark, format_local_benchmark_report
    __all__.extend(["run_local_ocr_benchmark", "format_local_benchmark_report"])
except ImportError:
    pass
