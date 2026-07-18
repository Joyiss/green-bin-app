import unittest

from materials import resolve_material_label


class ResolveMaterialLabelTests(unittest.TestCase):
    def test_resolves_exact_canonical_label(self):
        self.assertEqual(resolve_material_label("Smartphone"), "Smartphone")

    def test_generic_plastic_bottle_remains_unresolved(self):
        self.assertIsNone(resolve_material_label(" plastic bottle "))

    def test_resolves_descriptive_sentence_variant(self):
        self.assertEqual(
            resolve_material_label("This looks like a clear plastic water bottle"),
            "Plastic water bottle",
        )

    def test_resolves_generalized_watermelon_variant(self):
        self.assertEqual(resolve_material_label("watermelon"), "Fruit scraps")

    def test_resolves_notebook_variant(self):
        self.assertEqual(resolve_material_label("notebook"), "Book")

    def test_resolves_supported_garden_hose(self):
        self.assertEqual(resolve_material_label("Garden hose"), "Garden hose")


if __name__ == "__main__":
    unittest.main()
