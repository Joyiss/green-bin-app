import json
import unittest
from pathlib import Path
from uuid import uuid4

from services.guidance_source_loader import (
    load_trusted_guidance_chunks,
    reset_guidance_source_cache,
)


class GuidanceSourceLoaderTests(unittest.TestCase):
    def setUp(self):
        reset_guidance_source_cache()
        self.addCleanup(reset_guidance_source_cache)

    def _write_temp_json(self, payload) -> Path:
        file_path = (
            Path(__file__).resolve().parent
            / f"trusted_guidance_sources.test.{uuid4().hex}.json"
        )
        self.addCleanup(lambda: file_path.unlink(missing_ok=True))
        file_path.write_text(json.dumps(payload), encoding="utf-8")
        return file_path

    def test_loads_root_list_payload(self):
        file_path = self._write_temp_json(
            [
                {
                    "id": "chunk-1",
                    "source_name": "EPA",
                    "source_url": "[EPA](https://example.com/epa)",
                    "applies_to": {"item_labels": ["batteries"]},
                    "content": "Battery guidance.",
                }
            ]
        )

        chunks = load_trusted_guidance_chunks(file_path=file_path, force_reload=True)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["id"], "chunk-1")
        self.assertEqual(chunks[0]["source_url"], "https://example.com/epa")
        self.assertTrue(chunks[0]["source_grounded"])
        self.assertFalse(chunks[0]["human_reviewed"])
        self.assertEqual(chunks[0]["review_status"], "generated_from_sources")

    def test_loads_object_with_chunks_list(self):
        file_path = self._write_temp_json(
            {
                "chunks": [
                    {
                        "id": "chunk-2",
                        "source_name": "Earth911",
                        "source_url": "https://example.com/earth911",
                        "applies_to": {"materials": ["electronics"]},
                        "content": "Electronics guidance.",
                    }
                ]
            }
        )

        chunks = load_trusted_guidance_chunks(file_path=file_path, force_reload=True)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["id"], "chunk-2")
        self.assertEqual(chunks[0]["applies_to"]["materials"], ["electronics"])

    def test_loads_object_with_entries_list_and_maps_new_schema(self):
        file_path = self._write_temp_json(
            {
                "entries": [
                    {
                        "id": "battery-entry",
                        "section": "batteries",
                        "scope": "national_dropoff",
                        "source": {
                            "name": "Used Lithium-Ion Batteries",
                            "organization": "EPA",
                            "url": "https://example.com/battery",
                            "source_type": "federal_government",
                        },
                        "source_excerpt": "Do not place lithium batteries in household recycling.",
                        "source_claim": "Lithium-ion batteries require a dedicated drop-off program.",
                        "applies_to": {
                            "materials": ["rechargeable_batteries"],
                            "item_examples": ["laptop_batteries"],
                            "conditions": ["pre_dropoff_preparation"],
                        },
                        "decision_signals": {
                            "supports_recycling": True,
                            "supports_composting": False,
                            "supports_trash": False,
                            "supports_donation_or_reuse": False,
                            "requires_dropoff": True,
                            "requires_household_hazardous_waste": False,
                            "avoid_curbside_recycling": True,
                            "avoid_trash": True,
                        },
                        "limitations": ["Check participating sites before visiting."],
                        "confidence": "high",
                    }
                ]
            }
        )

        chunks = load_trusted_guidance_chunks(file_path=file_path, force_reload=True)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["id"], "battery-entry")
        self.assertEqual(chunks[0]["source_name"], "EPA")
        self.assertEqual(chunks[0]["source_url"], "https://example.com/battery")
        self.assertEqual(chunks[0]["location_scope"], "national")
        self.assertTrue(chunks[0]["generalizable"])
        self.assertTrue(chunks[0]["requires_location_check"])
        self.assertIn("laptop_batteries", chunks[0]["applies_to"]["item_labels"])
        self.assertIn("batteries", chunks[0]["applies_to"]["categories"])
        self.assertIn("requires_dropoff", chunks[0]["applies_to"]["condition_flags"])
        self.assertEqual(
            chunks[0]["disposal_actions_supported"],
            ["Drop-off", "Check local guidance"],
        )
        self.assertIn(
            "Do not place this item in curbside recycling",
            chunks[0]["warnings"][0],
        )
        self.assertIn(
            "Lithium-ion batteries require a dedicated drop-off program.",
            chunks[0]["content"],
        )

    def test_missing_file_fails_safely(self):
        missing_path = (
            Path(__file__).resolve().parent / "definitely-missing-guidance.json"
        )
        chunks = load_trusted_guidance_chunks(file_path=missing_path, force_reload=True)
        self.assertEqual(chunks, [])

    def test_malformed_json_fails_safely(self):
        file_path = (
            Path(__file__).resolve().parent
            / f"trusted_guidance_sources.test.{uuid4().hex}.json"
        )
        self.addCleanup(lambda: file_path.unlink(missing_ok=True))
        file_path.write_text("{not-valid-json", encoding="utf-8")

        chunks = load_trusted_guidance_chunks(file_path=file_path, force_reload=True)

        self.assertEqual(chunks, [])

    def test_empty_payload_fails_safely(self):
        file_path = self._write_temp_json({"chunks": []})
        chunks = load_trusted_guidance_chunks(file_path=file_path, force_reload=True)
        self.assertEqual(chunks, [])


if __name__ == "__main__":
    unittest.main()
