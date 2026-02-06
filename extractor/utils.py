"""Gemeinsame Utilities: Slide-Rendering, Bildverarbeitung."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


def pptx_to_images(
    pptx_path: Path,
    output_dir: Path | None = None,
    dpi: int = 200,
) -> list[Path]:
    """Konvertiert PPTX-Slides zu PNG-Bildern via LibreOffice.

    Args:
        pptx_path: Pfad zur PPTX-Datei
        output_dir: Zielverzeichnis (erstellt temp-dir wenn None)
        dpi: Render-Auflösung

    Returns:
        Sortierte Liste der Bild-Pfade
    """
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="slides_"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # Schritt 1: PPTX -> PDF via LibreOffice
    pdf_dir = output_dir / "_pdf_temp"
    pdf_dir.mkdir(exist_ok=True)

    cmd = [
        "libreoffice", "--headless",
        "--convert-to", "pdf",
        "--outdir", str(pdf_dir),
        str(pptx_path),
    ]

    logger.info(f"Rendere Slides: {pptx_path.name} → PDF")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        raise RuntimeError(
            f"LibreOffice-Konvertierung fehlgeschlagen:\n{result.stderr}\n\n"
            "Installation:\n"
            "  Ubuntu: sudo apt install libreoffice\n"
            "  macOS:  brew install --cask libreoffice"
        )

    pdf_path = pdf_dir / f"{pptx_path.stem}.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF nicht erzeugt: {pdf_path}")

    # Schritt 2: PDF -> PNGs
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise ImportError("pdf2image fehlt: pip install pdf2image")

    logger.info(f"PDF → Bilder (DPI={dpi})")
    images = convert_from_path(str(pdf_path), dpi=dpi)

    image_paths = []
    for i, img in enumerate(images):
        img_path = output_dir / f"slide_{i + 1:03d}.png"
        img.save(str(img_path), "PNG")
        image_paths.append(img_path)

    # Cleanup PDF
    pdf_path.unlink(missing_ok=True)
    try:
        pdf_dir.rmdir()
    except OSError:
        pass

    logger.info(f"{len(image_paths)} Slide-Bilder erzeugt")
    return sorted(image_paths)


def image_to_base64(image_path: Path, max_size: int = 2048) -> tuple[str, str]:
    """Konvertiert Bild zu Base64 für API-Calls.

    Args:
        image_path: Pfad zum Bild
        max_size: Maximale Kantenlänge (Resize wenn größer)

    Returns:
        Tuple von (base64_string, media_type)
    """
    import base64
    import io

    img = Image.open(image_path)

    # Resize wenn nötig
    if max(img.size) > max_size:
        ratio = max_size / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    # Zu PNG konvertieren
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return b64, "image/png"


def estimate_tokens(text: str) -> int:
    """Grobe Token-Schätzung (ca. 4 Zeichen pro Token für Deutsch)."""
    return max(1, len(text) // 4)
