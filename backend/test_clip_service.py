import io
import unittest
from unittest.mock import Mock, patch

import torch
from PIL import Image

from services import clip_service


def _make_image_bytes() -> bytes:
    image = Image.new("RGB", (24, 24), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _make_rotated_exif_duplicate_bytes() -> bytes:
    base_image = Image.new("RGB", (80, 50), color="white")
    rotated_image = base_image.transpose(Image.Transpose.ROTATE_90)
    rotated_exif = Image.Exif()
    rotated_exif[274] = 6

    buffer = io.BytesIO()
    rotated_image.save(buffer, format="JPEG", exif=rotated_exif)
    return buffer.getvalue()


class ClipServiceTests(unittest.TestCase):
    def setUp(self):
        clip_service._CLIP_MODEL = None
        clip_service._CLIP_PREPROCESS = None
        clip_service._CLIP_DEVICE = None

    def tearDown(self):
        clip_service._CLIP_MODEL = None
        clip_service._CLIP_PREPROCESS = None
        clip_service._CLIP_DEVICE = None

    def test_model_loader_is_lazy_and_cached(self):
        mock_model = Mock()
        mock_model.to.return_value = mock_model
        preprocess = Mock(return_value=torch.ones(3, 4, 4))

        with (
            patch("services.clip_service.torch.cuda.is_available", return_value=False),
            patch(
                "services.clip_service.open_clip.create_model_and_transforms",
                return_value=(mock_model, None, preprocess),
            ) as mock_create,
        ):
            mock_model.encode_image.return_value = torch.tensor([[3.0, 4.0]])

            first_embedding = clip_service.create_clip_embedding(_make_image_bytes())
            second_embedding = clip_service.create_clip_embedding(_make_image_bytes())

        self.assertEqual(mock_create.call_count, 1)
        self.assertEqual(len(first_embedding), 2)
        self.assertAlmostEqual(first_embedding[0], 0.6, places=4)
        self.assertAlmostEqual(first_embedding[1], 0.8, places=4)
        self.assertEqual(first_embedding, second_embedding)

    def test_create_clip_embedding_applies_exif_transpose_and_rgb_conversion(self):
        mock_model = Mock()
        mock_model.to.return_value = mock_model
        seen_image = {}

        def preprocess(image):
            seen_image["size"] = image.size
            seen_image["mode"] = image.mode
            return torch.ones(3, 4, 4)

        with (
            patch("services.clip_service.torch.cuda.is_available", return_value=False),
            patch(
                "services.clip_service.open_clip.create_model_and_transforms",
                return_value=(mock_model, None, preprocess),
            ),
        ):
            mock_model.encode_image.return_value = torch.tensor([[1.0, 0.0]])
            embedding = clip_service.create_clip_embedding(_make_rotated_exif_duplicate_bytes())

        self.assertEqual(seen_image["size"], (80, 50))
        self.assertEqual(seen_image["mode"], "RGB")
        self.assertEqual(embedding, [1.0, 0.0])

    def test_create_clip_embedding_raises_clear_service_error(self):
        mock_model = Mock()
        mock_model.to.return_value = mock_model
        preprocess = Mock(return_value=torch.ones(3, 4, 4))

        with (
            patch("services.clip_service.torch.cuda.is_available", return_value=False),
            patch(
                "services.clip_service.open_clip.create_model_and_transforms",
                return_value=(mock_model, None, preprocess),
            ),
        ):
            mock_model.encode_image.side_effect = RuntimeError("encode failed")

            with self.assertRaisesRegex(
                clip_service.ClipServiceError,
                "Failed to generate CLIP embedding: encode failed",
            ):
                clip_service.create_clip_embedding(_make_image_bytes())


if __name__ == "__main__":
    unittest.main()
