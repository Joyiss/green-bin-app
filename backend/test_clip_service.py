import io
import unittest
from unittest.mock import MagicMock, Mock, patch

from PIL import Image

from services import clip_service


def _make_image_bytes() -> bytes:
    image = Image.new("RGB", (24, 24), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


class ClipServiceTests(unittest.TestCase):
    def setUp(self):
        clip_service._CLIP_MODEL = None
        clip_service._CLIP_PREPROCESS = None
        clip_service._CLIP_DEVICE = None
        clip_service._TORCH_MODULE = None
        clip_service._WARMUP_THREAD = None

    def tearDown(self):
        clip_service._CLIP_MODEL = None
        clip_service._CLIP_PREPROCESS = None
        clip_service._CLIP_DEVICE = None
        clip_service._TORCH_MODULE = None
        clip_service._WARMUP_THREAD = None

    def test_readiness_check_never_imports_dependencies(self):
        with patch("services.clip_service.importlib.import_module") as mock_import:
            self.assertFalse(clip_service.is_clip_initialized())
        mock_import.assert_not_called()

    def test_embedding_refuses_to_cold_load(self):
        with patch("services.clip_service.importlib.import_module") as mock_import:
            with self.assertRaisesRegex(clip_service.ClipServiceError, "not initialized"):
                clip_service.create_clip_embedding(_make_image_bytes())
        mock_import.assert_not_called()

    def test_warmup_imports_and_initializes_once(self):
        torch_module = Mock()
        torch_module.cuda.is_available.return_value = False
        open_clip_module = Mock()
        model = Mock()
        model.to.return_value = model
        preprocess = Mock()
        open_clip_module.create_model_and_transforms.return_value = (model, None, preprocess)

        def import_dependency(name):
            return {"torch": torch_module, "open_clip": open_clip_module}[name]

        with patch("services.clip_service.importlib.import_module", side_effect=import_dependency) as mock_import:
            self.assertTrue(clip_service.warmup_clip_model())
            self.assertTrue(clip_service.warmup_clip_model())

        self.assertTrue(clip_service.is_clip_initialized())
        self.assertEqual(mock_import.call_count, 2)
        open_clip_module.create_model_and_transforms.assert_called_once()

    def test_initialized_embedding_uses_cached_runtime(self):
        torch_module = Mock()
        torch_module.no_grad.return_value.__enter__ = Mock()
        torch_module.no_grad.return_value.__exit__ = Mock(return_value=False)
        model = Mock()
        embedding = MagicMock()
        normalized_embedding = MagicMock()
        squeezed_embedding = MagicMock()
        model.encode_image.return_value = embedding
        embedding.norm.return_value = 2
        embedding.__truediv__.return_value = normalized_embedding
        normalized_embedding.squeeze.return_value = squeezed_embedding
        squeezed_embedding.cpu.return_value.tolist.return_value = [0.6, 0.8]
        tensor = Mock()
        preprocess = Mock(return_value=tensor)
        clip_service._CLIP_MODEL = model
        clip_service._CLIP_PREPROCESS = preprocess
        clip_service._CLIP_DEVICE = "cpu"
        clip_service._TORCH_MODULE = torch_module

        with patch("services.clip_service.importlib.import_module") as mock_import:
            result = clip_service.create_clip_embedding(_make_image_bytes())

        self.assertEqual(result, [0.6, 0.8])
        mock_import.assert_not_called()

    def test_background_warmup_is_non_blocking_and_failure_safe(self):
        release = __import__("threading").Event()

        def delayed_failure():
            release.wait(timeout=1)
            return False

        with patch("services.clip_service.warmup_clip_model", side_effect=delayed_failure):
            thread = clip_service.start_background_warmup()
            self.assertTrue(thread.is_alive())
            release.set()
            thread.join(timeout=1)
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
