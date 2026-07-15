import unittest

from services.guidance_key_service import normalize_guidance_key


class GuidanceKeyServiceTests(unittest.TestCase):
    def test_normalizes_item_labels(self):
        self.assertEqual(normalize_guidance_key("Plastic Bottle"), "plastic_bottle")

    def test_normalizes_material_categories(self):
        self.assertEqual(normalize_guidance_key("Hard Plastic"), "hard_plastic")

    def test_empty_values_return_none(self):
        self.assertIsNone(normalize_guidance_key(None))
        self.assertIsNone(normalize_guidance_key(""))
        self.assertIsNone(normalize_guidance_key("   "))


if __name__ == "__main__":
    unittest.main()
