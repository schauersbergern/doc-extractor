"""Datenmodelle für die Dokumentenextraktion."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TableData:
    """Extrahierte Tabelle."""
    headers: list[str]
    rows: list[list[str]]

    def to_markdown(self) -> str:
        if not self.headers and not self.rows:
            return ""
        cols = self.headers if self.headers else self.rows[0] if self.rows else []
        col_count = len(cols)
        lines = []
        if self.headers:
            lines.append("| " + " | ".join(self.headers) + " |")
            lines.append("| " + " | ".join(["---"] * col_count) + " |")
            data_rows = self.rows
        else:
            data_rows = self.rows
        for row in data_rows:
            padded = (row + [""] * col_count)[:col_count]
            lines.append("| " + " | ".join(padded) + " |")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {"headers": self.headers, "rows": self.rows}


@dataclass
class SlideData:
    """Extrahierte Daten eines einzelnen Slides oder einer Seite."""
    slide_number: int
    title: str = ""
    content: str = ""
    tables: list[TableData] = field(default_factory=list)
    notes: str = ""
    images_ocr: list[str] = field(default_factory=list)
    # Metadaten für Benchmark
    extraction_method: str = ""
    extraction_time_seconds: float = 0.0
    token_count: int = 0  # Geschätzte Tokens für Embedding

    def to_text(self, include_notes: bool = False) -> str:
        parts = []
        header = f"=== Slide {self.slide_number}"
        if self.title:
            header += f": {self.title}"
        header += " ==="
        parts.append(header)
        if self.content:
            parts.append(self.content)
        for table in self.tables:
            md = table.to_markdown()
            if md:
                parts.append(f"\n[Tabelle]\n{md}")
        for i, ocr_text in enumerate(self.images_ocr):
            if ocr_text.strip():
                parts.append(f"\n[Bild {i + 1} - OCR]\n{ocr_text.strip()}")
        if include_notes and self.notes:
            parts.append(f"\n[Speaker Notes]\n{self.notes}")
        return "\n\n".join(parts)

    def to_dict(self) -> dict:
        result = {
            "slide_number": self.slide_number,
            "title": self.title,
            "content": self.content,
        }
        if self.tables:
            result["tables"] = [t.to_dict() for t in self.tables]
        if self.notes:
            result["notes"] = self.notes
        if self.images_ocr:
            result["images_ocr"] = self.images_ocr
        if self.extraction_method:
            result["_meta"] = {
                "method": self.extraction_method,
                "time_seconds": round(self.extraction_time_seconds, 3),
                "token_count": self.token_count,
            }
        return result


@dataclass
class BenchmarkResult:
    """Vergleichsergebnis für die Uni-Präsentation."""
    method: str
    total_slides: int
    total_time_seconds: float
    avg_time_per_slide: float
    total_chars: int
    total_tokens_estimate: int
    slides: list[SlideData]
    # Kosten-Schätzung
    estimated_cost_usd: float = 0.0
    gpu_required: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "total_slides": self.total_slides,
            "total_time_seconds": round(self.total_time_seconds, 2),
            "avg_time_per_slide": round(self.avg_time_per_slide, 3),
            "total_chars": self.total_chars,
            "total_tokens_estimate": self.total_tokens_estimate,
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
            "gpu_required": self.gpu_required,
            "notes": self.notes,
        }


class Timer:
    """Einfacher Context-Manager für Zeitmessung."""

    def __init__(self):
        self.elapsed: float = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed = time.perf_counter() - self._start
