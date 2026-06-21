import unittest

from services.confidence_router import evaluate_clip_candidates


class ConfidenceRouterTests(unittest.TestCase):
    def test_strong_agreement_returns_use_cache_true(self):
        candidates = [
            {"item_label": "Calculator", "similarity": 0.97},
            {"item_label": " calculator ", "similarity": 0.95},
            {"item_label": "CALCULATOR", "similarity": 0.92},
            {"item_label": "Keyboard", "similarity": 0.75},
            {"item_label": "Mouse", "similarity": 0.7},
        ]

        result = evaluate_clip_candidates(candidates)

        self.assertEqual(
            result,
            {
                "use_cache": True,
                "item_label": "Calculator",
                "reason": "strong_clip_agreement",
                "confidence": 0.97,
                "top_label": "Calculator",
                "top_score": 0.97,
                "label_agreement_count": 3,
                "evaluated_count": 5,
                "best_competing_label": "Keyboard",
                "best_competing_score": 0.75,
                "margin": 0.21999999999999997,
            },
        )

    def test_small_margin_pen_pencil_case_returns_false(self):
        candidates = [
            {"item_label": "Pen", "similarity": 0.96},
            {"item_label": "pen", "similarity": 0.94},
            {"item_label": " PEN ", "similarity": 0.91},
            {"item_label": "Pencil", "similarity": 0.9},
            {"item_label": "pencil", "similarity": 0.89},
        ]

        result = evaluate_clip_candidates(candidates)

        self.assertFalse(result["use_cache"])
        self.assertIsNone(result["item_label"])
        self.assertEqual(result["reason"], "small_label_margin")
        self.assertEqual(result["confidence"], 0.96)
        self.assertEqual(result["top_label"], "Pen")
        self.assertEqual(result["top_score"], 0.96)
        self.assertEqual(result["label_agreement_count"], 3)
        self.assertEqual(result["evaluated_count"], 5)
        self.assertEqual(result["best_competing_label"], "Pencil")
        self.assertEqual(result["best_competing_score"], 0.9)
        self.assertAlmostEqual(result["margin"], 0.06, places=6)

    def test_low_top_similarity_returns_low_top_similarity(self):
        candidates = [
            {"item_label": "Calculator", "similarity": 0.87},
            {"item_label": "calculator", "similarity": 0.85},
            {"item_label": "CALCULATOR", "similarity": 0.83},
            {"item_label": "Keyboard", "similarity": 0.6},
        ]

        result = evaluate_clip_candidates(candidates)

        self.assertFalse(result["use_cache"])
        self.assertIsNone(result["item_label"])
        self.assertEqual(result["reason"], "low_top_similarity")
        self.assertEqual(result["confidence"], 0.87)
        self.assertEqual(result["top_label"], "Calculator")
        self.assertEqual(result["top_score"], 0.87)
        self.assertEqual(result["label_agreement_count"], 3)
        self.assertEqual(result["evaluated_count"], 4)
        self.assertEqual(result["best_competing_label"], "Keyboard")
        self.assertEqual(result["best_competing_score"], 0.6)
        self.assertAlmostEqual(result["margin"], 0.27, places=6)

    def test_weak_label_agreement_returns_weak_label_agreement(self):
        candidates = [
            {"item_label": "Calculator", "similarity": 0.96},
            {"item_label": "calculator", "similarity": 0.91},
            {"item_label": "Keyboard", "similarity": 0.65},
            {"item_label": "Mouse", "similarity": 0.61},
            {"item_label": "Monitor", "similarity": 0.58},
        ]

        result = evaluate_clip_candidates(candidates)

        self.assertFalse(result["use_cache"])
        self.assertIsNone(result["item_label"])
        self.assertEqual(result["reason"], "weak_label_agreement")
        self.assertEqual(result["confidence"], 0.96)
        self.assertEqual(result["top_label"], "Calculator")
        self.assertEqual(result["top_score"], 0.96)
        self.assertEqual(result["label_agreement_count"], 2)
        self.assertEqual(result["evaluated_count"], 5)
        self.assertEqual(result["best_competing_label"], "Keyboard")
        self.assertEqual(result["best_competing_score"], 0.65)
        self.assertAlmostEqual(result["margin"], 0.31, places=6)

    def test_empty_candidates_returns_no_clip_candidates(self):
        result = evaluate_clip_candidates([])

        self.assertEqual(
            result,
            {
                "use_cache": False,
                "item_label": None,
                "reason": "no_clip_candidates",
                "confidence": None,
                "top_label": None,
                "top_score": None,
                "label_agreement_count": 0,
                "evaluated_count": 0,
                "best_competing_label": None,
                "best_competing_score": None,
                "margin": None,
            },
        )

    def test_unknown_and_empty_labels_return_no_valid_clip_candidates(self):
        candidates = [
            {"item_label": "unknown", "similarity": 0.99},
            {"item_label": "   ", "similarity": 0.95},
            {"item_label": "", "similarity": 0.9},
            {"item_label": " Unknown ", "similarity": 0.89},
        ]

        result = evaluate_clip_candidates(candidates)

        self.assertEqual(
            result,
            {
                "use_cache": False,
                "item_label": None,
                "reason": "no_valid_clip_candidates",
                "confidence": None,
                "top_label": None,
                "top_score": None,
                "label_agreement_count": 0,
                "evaluated_count": 4,
                "best_competing_label": None,
                "best_competing_score": None,
                "margin": None,
            },
        )

    def test_invalid_similarity_records_are_ignored_before_sorting(self):
        candidates = [
            {"item_label": "Calculator", "similarity": 0.93},
            {"item_label": "Calculator", "similarity": "0.91"},
            {"item_label": "Calculator", "similarity": 0.89},
            {"item_label": "Keyboard", "similarity": 0.72},
            {"item_label": "Mouse", "similarity": 0.69},
            {"item_label": "Monitor", "similarity": 0.66},
            {"item_label": "BrokenMissing"},
            {"item_label": "BrokenText", "similarity": "not-a-number"},
            {"item_label": "BrokenNone", "similarity": None},
        ]

        result = evaluate_clip_candidates(candidates)

        self.assertTrue(result["use_cache"])
        self.assertEqual(result["item_label"], "Calculator")
        self.assertEqual(result["reason"], "strong_clip_agreement")
        self.assertEqual(result["top_label"], "Calculator")
        self.assertEqual(result["top_score"], 0.93)
        self.assertEqual(result["label_agreement_count"], 3)
        self.assertEqual(result["evaluated_count"], 5)
        self.assertEqual(result["best_competing_label"], "Keyboard")
        self.assertEqual(result["best_competing_score"], 0.72)
        self.assertAlmostEqual(result["margin"], 0.21, places=6)

    def test_only_top_k_sortable_candidates_are_evaluated(self):
        candidates = [
            {"item_label": "Calculator", "similarity": 0.98},
            {"item_label": "Keyboard", "similarity": 0.97},
            {"item_label": "calculator", "similarity": 0.96},
            {"item_label": "Mouse", "similarity": 0.95},
            {"item_label": "Charger", "similarity": 0.94},
            {"item_label": "CALCULATOR", "similarity": 0.93},
            {"item_label": "BrokenText", "similarity": "bad"},
        ]

        result = evaluate_clip_candidates(candidates)

        self.assertFalse(result["use_cache"])
        self.assertIsNone(result["item_label"])
        self.assertEqual(result["reason"], "weak_label_agreement")
        self.assertEqual(result["top_label"], "Calculator")
        self.assertEqual(result["top_score"], 0.98)
        self.assertEqual(result["label_agreement_count"], 2)
        self.assertEqual(result["evaluated_count"], 5)
        self.assertEqual(result["best_competing_label"], "Keyboard")
        self.assertEqual(result["best_competing_score"], 0.97)
        self.assertAlmostEqual(result["margin"], 0.01, places=6)


if __name__ == "__main__":
    unittest.main()
