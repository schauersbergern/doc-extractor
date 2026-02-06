"""Modus 3: DeepSeek OCR 2 — lokale OCR mit Vision-Language-Modell.

3B-Parameter-Modell für Dokumentenverständnis.
Benötigt NVIDIA GPU mit min. 8GB VRAM (4-bit) / 16GB (volle Präzision).

Einsatz: Rechnungen scannen, Uni-Präsentation, Benchmark vs. Vision-LLM.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Literal

from .models import SlideData, Timer
from .utils import estimate_tokens, pptx_to_images

logger = logging.getLogger(__name__)

# Globaler Model-Cache (Modell nur einmal laden)
_model_cache: dict = {}


def _load_model(quantize_4bit: bool = False, backend: str = "transformers"):
    """Lädt DeepSeek OCR 2. Cached nach erstem Aufruf.

    Args:
        quantize_4bit: 4-bit Quantisierung
        backend: 'transformers' oder 'vllm'

    Returns:
        Dict mit 'model', 'tokenizer', 'backend'
    """
    cache_key = f"{backend}_{quantize_4bit}"
    if cache_key in _model_cache:
        logger.info("Modell aus Cache geladen")
        return _model_cache[cache_key]

    if backend == "vllm":
        return _load_vllm()
    else:
        return _load_transformers(quantize_4bit)


def _load_transformers(quantize_4bit: bool = False) -> dict:
    """Lädt via Hugging Face Transformers."""
    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
    except ImportError:
        raise ImportError(
            "Transformers nicht installiert.\n"
            "pip install torch>=2.6.0 transformers==4.46.3 tokenizers==0.20.3 "
            "einops addict easydict"
        )

    model_name = "deepseek-ai/DeepSeek-OCR-2"
    logger.info(f"Lade {model_name} (4-bit={quantize_4bit})...")

    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)

    kwargs = {
        "trust_remote_code": True,
        "use_safetensors": True,
    }

    # Flash Attention
    try:
        import flash_attn  # noqa: F401
        kwargs["_attn_implementation"] = "flash_attention_2"
        logger.info("Flash Attention 2 aktiviert")
    except ImportError:
        logger.warning("flash-attn fehlt — langsamere Inferenz")

    if quantize_4bit:
        import torch
        try:
            from transformers import BitsAndBytesConfig
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_quant_type="nf4",
            )
        except ImportError:
            raise ImportError("bitsandbytes fehlt: pip install bitsandbytes")

    model = AutoModel.from_pretrained(model_name, **kwargs)

    if not quantize_4bit:
        import torch
        model = model.eval().cuda().to(torch.bfloat16)
    else:
        model = model.eval()

    result = {
        "model": model,
        "tokenizer": tokenizer,
        "backend": "transformers",
    }
    _model_cache[f"transformers_{quantize_4bit}"] = result
    logger.info("Modell geladen ✓")
    return result


def _load_vllm() -> dict:
    """Lädt via vLLM (schneller, Batch-fähig)."""
    try:
        from vllm import LLM, SamplingParams
        from vllm.model_executor.models.deepseek_ocr import NGramPerReqLogitsProcessor
    except ImportError:
        raise ImportError(
            "vLLM nicht installiert.\n"
            "pip install -U vllm --pre --extra-index-url https://wheels.vllm.ai/nightly"
        )

    llm = LLM(
        model="deepseek-ai/DeepSeek-OCR-2",
        enable_prefix_caching=False,
        mm_processor_cache_gb=0,
        logits_processors=[NGramPerReqLogitsProcessor],
    )

    result = {"model": llm, "tokenizer": None, "backend": "vllm"}
    _model_cache["vllm_False"] = result
    logger.info("vLLM-Modell geladen ✓")
    return result


# === Prompts ===

PROMPTS = {
    "structured": "<image>\n<|grounding|>Convert the document to markdown.",
    "free": "<image>\nFree OCR.",
    "figure": "<image>\nParse the figure.",
    "describe": "<image>\nDescribe this image in detail.",
}


def _infer_transformers(
    model,
    tokenizer,
    image_path: Path,
    prompt: str,
    output_dir: Path,
) -> str:
    """Inferenz via Transformers-Backend."""
    result = model.infer(
        tokenizer,
        prompt=prompt,
        image_file=str(image_path),
        output_path=str(output_dir),
        base_size=1024,
        image_size=768,
        crop_mode=True,
        save_results=False,
    )

    if isinstance(result, str):
        return result
    elif isinstance(result, dict) and "text" in result:
        return result["text"]
    elif isinstance(result, list):
        return "\n".join(str(r) for r in result)
    return str(result)


def _infer_vllm_batch(
    llm,
    image_paths: list[Path],
    prompt: str,
) -> list[str]:
    """Batch-Inferenz via vLLM (deutlich schneller)."""
    from vllm import SamplingParams
    from PIL import Image

    model_input = []
    for img_path in image_paths:
        img = Image.open(img_path).convert("RGB")
        model_input.append({
            "prompt": prompt,
            "multi_modal_data": {"image": img},
        })

    sampling_params = SamplingParams(
        temperature=0.0,
        max_tokens=8192,
        extra_args=dict(
            ngram_size=30,
            window_size=90,
            whitelist_token_ids={128821, 128822},
        ),
        skip_special_tokens=False,
    )

    outputs = llm.generate(model_input, sampling_params)
    return [o.outputs[0].text for o in outputs]


def extract_deepseek(
    pptx_path: str | Path,
    slide_numbers: list[int] | None = None,
    quantize_4bit: bool = False,
    prompt_mode: Literal["structured", "free", "figure", "describe"] = "structured",
    backend: Literal["transformers", "vllm"] = "transformers",
    dpi: int = 200,
) -> list[SlideData]:
    """Extrahiert Text aus PPTX via DeepSeek OCR 2.

    Args:
        pptx_path: Pfad zur PPTX-Datei
        slide_numbers: Nur diese Slides (1-basiert)
        quantize_4bit: 4-bit Quantisierung
        prompt_mode: OCR-Modus
        backend: 'transformers' oder 'vllm'
        dpi: Render-Auflösung

    Returns:
        Liste von SlideData
    """
    pptx_path = Path(pptx_path)
    if not pptx_path.exists():
        raise FileNotFoundError(f"Nicht gefunden: {pptx_path}")

    prompt = PROMPTS.get(prompt_mode, PROMPTS["structured"])

    with tempfile.TemporaryDirectory(prefix="deepseek_") as tmp:
        tmp_path = Path(tmp)
        img_dir = tmp_path / "slides"
        ocr_dir = tmp_path / "ocr_out"
        ocr_dir.mkdir()

        # Slides rendern
        image_paths = pptx_to_images(pptx_path, img_dir, dpi=dpi)

        # Filter
        if slide_numbers:
            items = [
                (int(p.stem.split("_")[1]), p)
                for p in image_paths
                if int(p.stem.split("_")[1]) in slide_numbers
            ]
        else:
            items = [(i + 1, p) for i, p in enumerate(image_paths)]

        # Modell laden
        ctx = _load_model(quantize_4bit=quantize_4bit, backend=backend)

        # Inferenz
        if ctx["backend"] == "vllm":
            # Batch-Verarbeitung
            with Timer() as batch_timer:
                paths = [p for _, p in items]
                texts = _infer_vllm_batch(ctx["model"], paths, prompt)

            results = []
            per_slide_time = batch_timer.elapsed / len(items) if items else 0
            for (slide_num, _), text in zip(items, texts):
                results.append(SlideData(
                    slide_number=slide_num,
                    content=text,
                    extraction_method=f"deepseek-ocr2/vllm/{prompt_mode}",
                    extraction_time_seconds=per_slide_time,
                    token_count=estimate_tokens(text),
                ))
        else:
            # Sequenzielle Verarbeitung
            results = []
            for slide_num, img_path in items:
                logger.info(f"DeepSeek OCR Slide {slide_num}: {img_path.name}")

                with Timer() as timer:
                    text = _infer_transformers(
                        ctx["model"], ctx["tokenizer"],
                        img_path, prompt, ocr_dir,
                    )

                results.append(SlideData(
                    slide_number=slide_num,
                    content=text,
                    extraction_method=f"deepseek-ocr2/transformers/{prompt_mode}",
                    extraction_time_seconds=timer.elapsed,
                    token_count=estimate_tokens(text),
                ))
                logger.info(f"  → {len(text)} Zeichen, {timer.elapsed:.2f}s")

    return results


def extract_deepseek_images(
    image_paths: list[str | Path],
    quantize_4bit: bool = False,
    prompt_mode: Literal["structured", "free", "figure", "describe"] = "structured",
    backend: Literal["transformers", "vllm"] = "transformers",
) -> list[SlideData]:
    """Extrahiert Text direkt aus Bilddateien (Rechnungen, Scans).

    Args:
        image_paths: Liste von Bildpfaden
        quantize_4bit: 4-bit Quantisierung
        prompt_mode: OCR-Modus
        backend: 'transformers' oder 'vllm'

    Returns:
        Liste von SlideData
    """
    prompt = PROMPTS.get(prompt_mode, PROMPTS["structured"])
    ctx = _load_model(quantize_4bit=quantize_4bit, backend=backend)

    paths = [Path(p) for p in image_paths]

    if ctx["backend"] == "vllm":
        with Timer() as timer:
            texts = _infer_vllm_batch(ctx["model"], paths, prompt)

        per_item = timer.elapsed / len(paths) if paths else 0
        return [
            SlideData(
                slide_number=i + 1,
                title=p.stem,
                content=text,
                extraction_method=f"deepseek-ocr2/vllm/{prompt_mode}",
                extraction_time_seconds=per_item,
                token_count=estimate_tokens(text),
            )
            for i, (p, text) in enumerate(zip(paths, texts))
        ]
    else:
        results = []
        with tempfile.TemporaryDirectory() as tmp:
            for i, img_path in enumerate(paths):
                logger.info(f"DeepSeek OCR Bild {i + 1}: {img_path.name}")
                with Timer() as timer:
                    text = _infer_transformers(
                        ctx["model"], ctx["tokenizer"],
                        img_path, prompt, Path(tmp),
                    )
                results.append(SlideData(
                    slide_number=i + 1,
                    title=img_path.stem,
                    content=text,
                    extraction_method=f"deepseek-ocr2/transformers/{prompt_mode}",
                    extraction_time_seconds=timer.elapsed,
                    token_count=estimate_tokens(text),
                ))
        return results
