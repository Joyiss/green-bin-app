import unittest

from materials import resolve_material_label


class ResolveMaterialLabelTests(unittest.TestCase):
    def test_resolves_exact_canonical_label(self):
        self.assertEqual(resolve_material_label("Smartphone"), "Smartphone")

    def test_resolves_minor_label_variant(self):
        self.assertEqual(resolve_material_label(" plastic bottle "), "Plastic water bottle")

    def test_resolves_descriptive_sentence_variant(self):
        self.assertEqual(
            resolve_material_label("This looks like a clear plastic water bottle"),
            "Plastic water bottle",
        )

    def test_resolves_generalized_watermelon_variant(self):
        self.assertEqual(resolve_material_label("watermelon"), "Fruit scraps")

    def test_resolves_notebook_variant(self):
        self.assertEqual(resolve_material_label("notebook"), "Notebook paper")

    def test_returns_none_for_unknown_label(self):
        self.assertIsNone(resolve_material_label("Garden hose"))


if __name__ == "__main__":
    unittest.main()
