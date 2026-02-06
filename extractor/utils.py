"""Gemeinsame Utilities: Slide-Rendering, Bildverarbeitung."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


def _find_libreoffice_binary() -> str:
    """Findet ein verfügbares LibreOffice-CLI Binary auf Linux/macOS."""
    for candidate in ("libreoffice", "soffice"):
        path = shutil.which(candidate)
        if path:
            return path

    # Standardpfad auf macOS bei App-Installation
    macos_bundle_binary = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    if macos_bundle_binary.exists():
        return str(macos_bundle_binary)

    raise FileNotFoundError(
        "LibreOffice CLI nicht gefunden. Installiere LibreOffice und stelle sicher, "
        "dass 'soffice' oder 'libreoffice' im PATH ist.\n"
        "macOS: brew install --cask libreoffice"
    )


def _find_poppler_path() -> str | None:
    """Liefert das Verzeichnis mit pdfinfo/pdftoppm für pdf2image."""
    pdfinfo = shutil.which("pdfinfo")
    pdftoppm = shutil.which("pdftoppm")
    if pdfinfo and pdftoppm:
        return str(Path(pdfinfo).parent)

    # Typische Homebrew-Pfade
    for path in (Path("/opt/homebrew/bin"), Path("/usr/local/bin")):
        if (path / "pdfinfo").exists() and (path / "pdftoppm").exists():
            return str(path)

    return None


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
        _find_libreoffice_binary(), "--headless",
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

    poppler_path = _find_poppler_path()
    if poppler_path is None:
        raise RuntimeError(
            "Poppler fehlt (pdfinfo/pdftoppm nicht gefunden).\n"
            "Installation:\n"
            "  macOS:  brew install poppler\n"
            "  Ubuntu: sudo apt install poppler-utils"
        )

    logger.info(f"PDF → Bilder (DPI={dpi})")
    images = convert_from_path(str(pdf_path), dpi=dpi, poppler_path=poppler_path)

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
