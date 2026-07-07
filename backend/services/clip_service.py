from __future__ import annotations

import io
import importlib
import logging
import threading
from typing import Any

from PIL import Image, ImageOps


logger = logging.getLogger(__name__)

_CLIP_MODEL = None
_CLIP_PREPROCESS = None
_CLIP_DEVICE: str | None = None
_TORCH_MODULE: Any | None = None
_RUNTIME_LOCK = threading.Lock()
_WARMUP_START_LOCK = threading.Lock()
_WARMUP_THREAD: threading.Thread | None = None


class ClipServiceError(RuntimeError):
    pass


def is_clip_initialized() -> bool:
    """Check only in-memory state; never import dependencies or load weights."""
    return (
        _CLIP_MODEL is not None
        and _CLIP_PREPROCESS is not None
        and _CLIP_DEVICE is not None
        and _TORCH_MODULE is not None
    )


def _get_clip_runtime():
    global _CLIP_MODEL, _CLIP_PREPROCESS, _CLIP_DEVICE, _TORCH_MODULE

    if not is_clip_initialized():
        with _RUNTIME_LOCK:
            if is_clip_initialized():
                return _CLIP_MODEL, _CLIP_PREPROCESS, _CLIP_DEVICE, _TORCH_MODULE

            try:
                torch_module = importlib.import_module("torch")
                open_clip_module = importlib.import_module("open_clip")
                device = "cuda" if torch_module.cuda.is_available() else "cpu"
                model, _, preprocess = open_clip_module.create_model_and_transforms(
                    "ViT-B-32",
                    pretrained="laion2b_s34b_b79k",
                )
                model = model.to(device)
                model.eval()
            except Exception as exc:
                raise ClipServiceError(f"Failed to load CLIP model: {exc}") from exc

            _CLIP_MODEL = model
            _CLIP_PREPROCESS = preprocess
            _CLIP_DEVICE = device
            _TORCH_MODULE = torch_module

    return _CLIP_MODEL, _CLIP_PREPROCESS, _CLIP_DEVICE, _TORCH_MODULE


def warmup_clip_model() -> bool:
    try:
        _get_clip_runtime()
        logger.info("CLIP background warmup completed.")
        return True
    except Exception as exc:
        logger.warning("CLIP background warmup failed safely: %s", exc)
        return False


def start_background_warmup() -> threading.Thread:
    global _WARMUP_THREAD

    with _WARMUP_START_LOCK:
        if _WARMUP_THREAD is not None and _WARMUP_THREAD.is_alive():
            return _WARMUP_THREAD

        thread = threading.Thread(
            target=warmup_clip_model,
            name="clip-warmup",
            daemon=True,
        )
        _WARMUP_THREAD = thread
        thread.start()
        return thread


def create_clip_embedding(image_bytes: bytes) -> list[float]:
    if not is_clip_initialized():
        raise ClipServiceError("CLIP model is not initialized.")

    try:
        model, preprocess, device, torch_module = _get_clip_runtime()

        with Image.open(io.BytesIO(image_bytes)) as image:
            normalized_image = ImageOps.exif_transpose(image).convert("RGB")
            image_tensor = preprocess(normalized_image).unsqueeze(0).to(device)

        with torch_module.no_grad():
            embedding = model.encode_image(image_tensor)

        embedding = embedding / embedding.norm(dim=-1, keepdim=True)
        return embedding.squeeze(0).cpu().tolist()
    except ClipServiceError:
        raise
    except Exception as exc:
        raise ClipServiceError(f"Failed to generate CLIP embedding: {exc}") from exc
