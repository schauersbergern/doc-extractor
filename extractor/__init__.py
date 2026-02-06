"""doc-extractor: PPTX/Dokumentenextraktion mit drei Modi.

Modus 1 (direct):   Direkte XML-Textextraktion — schnell, kein GPU
Modus 2 (vision):   Vision-LLM (Claude/GPT-4o) — semantisch, Cloud
Modus 3 (deepseek): DeepSeek OCR 2 — lokal, DSGVO, GPU
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

# Benchmark
try:
    from .benchmark import benchmark_pptx, benchmark_images, format_benchmark_report
    __all__.extend(["benchmark_pptx", "benchmark_images", "format_benchmark_report"])
except ImportError:
    pass
