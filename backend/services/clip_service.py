from __future__ import annotations

import io

import open_clip
import torch
from PIL import Image, ImageOps


_CLIP_MODEL = None
_CLIP_PREPROCESS = None
_CLIP_DEVICE: str | None = None


class ClipServiceError(RuntimeError):
    pass


def _get_clip_runtime():
    global _CLIP_MODEL, _CLIP_PREPROCESS, _CLIP_DEVICE

    if _CLIP_MODEL is None or _CLIP_PREPROCESS is None or _CLIP_DEVICE is None:
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model, _, preprocess = open_clip.create_model_and_transforms(
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

    return _CLIP_MODEL, _CLIP_PREPROCESS, _CLIP_DEVICE


def create_clip_embedding(image_bytes: bytes) -> list[float]:
    try:
        model, preprocess, device = _get_clip_runtime()

        with Image.open(io.BytesIO(image_bytes)) as image:
            normalized_image = ImageOps.exif_transpose(image).convert("RGB")
            image_tensor = preprocess(normalized_image).unsqueeze(0).to(device)

        with torch.no_grad():
            embedding = model.encode_image(image_tensor)

        embedding = embedding / embedding.norm(dim=-1, keepdim=True)
        return embedding.squeeze(0).cpu().tolist()
    except ClipServiceError:
        raise
    except Exception as exc:
        raise ClipServiceError(f"Failed to generate CLIP embedding: {exc}") from exc
