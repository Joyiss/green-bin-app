import unittest
from unittest.mock import patch

from benchmarks.reliability_benchmark import (
    CHECK_NAMES,
    load_cases,
    run_benchmark,
    _contains_whole_term,
)
from services import vlm_service


EXPECTED_IMAGE_NAMES = {
    "face-cleanser-container.jpg",
    "lotion-bottle.jpg",
    "chocolate-wrapper.jpg",
    "battery.jpg",
    "clean-paper-plate.jpg",
    "stainless-steel-cup.jpg",
    "banana-bunch.jpg",
    "green-leaves.jpg",
}


class ReliabilityBenchmarkTests(unittest.TestCase):
    def test_metadata_covers_all_representative_images_and_control_cases(self):
        cases = load_cases()
        image_names = {
            case["image"].split("/")[-1]
            for case in cases
            if isinstance(case.get("image"), str)
        }

        self.assertEqual(image_names, EXPECTED_IMAGE_NAMES)
        self.assertGreaterEqual(len(cases), len(EXPECTED_IMAGE_NAMES) + 2)
        self.assertIn("intact-reusable-toy-control", {case["id"] for case in cases})
        self.assertIn(
            "primary-metal-secondary-plastic-control",
            {case["id"] for case in cases},
        )

    def test_every_case_has_disposal_relevant_expectations(self):
        for case in load_cases():
            with self.subTest(case=case["id"]):
                self.assertTrue(case["expected_labels"])
                self.assertTrue(case["acceptable_broader_labels"])
                self.assertTrue(case["prohibited_labels"])
                self.assertTrue(case["expected_materials"])
                self.assertTrue(case["expected_categories"])
                self.assertTrue(case["visible_condition"]["value"])
                self.assertTrue(
                    all(
                        isinstance(flag, str) and flag
                        for flag in case.get("prohibited_condition_flags", [])
                    )
                )
                self.assertIn("expected_guidance_behavior", case)
                self.assertTrue(case["prohibited_disposal_actions"])
                self.assertTrue(set(case["known_failures"]).issubset(CHECK_NAMES))

    def test_term_matching_is_token_aware(self):
        self.assertTrue(_contains_whole_term("ceramic mug", "mug"))
        self.assertFalse(_contains_whole_term("stainless steel", "stain"))
        self.assertFalse(_contains_whole_term("opened wrapper", "pen"))

    def test_deterministic_benchmark_records_required_pipeline_context(self):
        report = run_benchmark(
            case_ids=["lotion-bottle-unknown-resin"]
        )

        self.assertEqual(report["metrics"]["case_count"], 1)
        outcome = report["outcomes"][0]
        for field in (
            "predicted_item",
            "vlm_evidence",
            "normalized_result",
            "recognition_confidence",
            "retrieved_chunks",
            "final_disposal_action",
            "guidance_confidence",
            "clarification_requested",
        ):
            self.assertIn(field, outcome)

    def test_full_deterministic_benchmark_has_no_undocumented_regressions(self):
        report = run_benchmark()

        self.assertTrue(report["passed"])
        self.assertEqual(report["unexpected_failure_count"], 0)
        self.assertEqual(report["expected_failure_count"], 4)
        self.assertEqual(report["metrics"]["incorrect_disposal_actions"], 0)
        self.assertEqual(report["metrics"]["case_count"], len(load_cases()))

    def test_live_path_uses_real_image_and_forces_open_recognition(self):
        case = next(
            case
            for case in load_cases()
            if case["id"] == "lotion-bottle-unknown-resin"
        )
        prediction = vlm_service.build_prediction_result(case["recorded_vlm_response"])

        with patch(
            "benchmarks.reliability_benchmark.vlm_service.get_top_predictions",
            return_value=prediction,
        ) as mock_vlm:
            report = run_benchmark(
                mode="live",
                case_ids=[case["id"]],
            )

        self.assertEqual(report["mode"], "live")
        self.assertEqual(report["metrics"]["case_count"], 1)
        self.assertEqual(mock_vlm.call_args.kwargs["recognition_mode"], "open")


if __name__ == "__main__":
    unittest.main()
