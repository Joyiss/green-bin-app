import unittest

from services.guidance_retrieval_service import (
    MIN_RETRIEVAL_SCORE,
    retrieve_guidance_chunks,
)
from services.guidance_source_loader import load_trusted_guidance_chunks


def _chunk(
    *,
    chunk_id: str,
    title: str | None = None,
    section: str | None = None,
    source_name: str = "EPA",
    source_url: str = "https://example.com",
    source_type: str = "federal_government",
    location_scope: str = "national",
    generalizable: bool = True,
    requires_location_check: bool = False,
    item_labels=None,
    materials=None,
    categories=None,
    condition_flags=None,
    disposal_actions_supported=None,
):
    return {
        "id": chunk_id,
        "title": title or chunk_id,
        "section": section,
        "source_name": source_name,
        "source_url": source_url,
        "source_type": source_type,
        "location_scope": location_scope,
        "generalizable": generalizable,
        "requires_location_check": requires_location_check,
        "applies_to": {
            "item_labels": item_labels or [],
            "materials": materials or [],
            "categories": categories or [],
            "condition_flags": condition_flags or [],
        },
        "content": f"Guidance for {chunk_id}.",
        "disposal_actions_supported": disposal_actions_supported or ["Recycle"],
        "warnings": [],
        "limitations": [],
        "confidence": "high",
        "verified": True,
        "source_grounded": True,
        "human_reviewed": False,
        "review_status": "generated_from_sources",
    }


class GuidanceRetrievalServiceTests(unittest.TestCase):
    def test_exact_item_label_match_retrieves_correct_chunk(self):
        chunks = [
            _chunk(chunk_id="battery", item_labels=["batteries"]),
            _chunk(chunk_id="paper", item_labels=["newspapers"]),
        ]

        results = retrieve_guidance_chunks(
            item_label="batteries",
            material=None,
            category=None,
            chunks=chunks,
        )

        self.assertEqual(results[0]["chunk_id"], "battery")
        self.assertIn("item_label_exact", results[0]["matched_fields"])

    def test_material_match_retrieves_correct_chunk(self):
        chunks = [
            _chunk(
                chunk_id="paintcare",
                source_name="PaintCare",
                generalizable=False,
                requires_location_check=True,
                materials=["paint"],
                disposal_actions_supported=["Drop-off"],
            )
        ]

        results = retrieve_guidance_chunks(
            item_label=None,
            material="paint",
            category=None,
            chunks=chunks,
        )

        self.assertEqual(results[0]["chunk_id"], "paintcare")
        self.assertIn("material", results[0]["matched_fields"])

    def test_category_match_retrieves_correct_chunk(self):
        chunks = [
            _chunk(
                chunk_id="organic",
                categories=["organic waste"],
                disposal_actions_supported=["Compost"],
            )
        ]

        results = retrieve_guidance_chunks(
            item_label=None,
            material=None,
            category="organic waste",
            chunks=chunks,
        )

        self.assertEqual(results[0]["chunk_id"], "organic")
        self.assertIn("category", results[0]["matched_fields"])

    def test_condition_flag_boost_prioritizes_relevant_chunk(self):
        chunks = [
            _chunk(chunk_id="plain-cardboard", categories=["cardboard"]),
            _chunk(
                chunk_id="greasy-cardboard",
                categories=["cardboard"],
                condition_flags=["food_soiled"],
            ),
        ]

        results = retrieve_guidance_chunks(
            item_label=None,
            material=None,
            category="cardboard",
            condition_flags=["food_soiled"],
            chunks=chunks,
        )

        self.assertEqual(results[0]["chunk_id"], "greasy-cardboard")
        self.assertIn("condition_flags", results[0]["matched_fields"])

    def test_singular_plural_normalization_works(self):
        chunks = [_chunk(chunk_id="jar", item_labels=["glass jars"])]

        results = retrieve_guidance_chunks(
            item_label="glass jar",
            material=None,
            category=None,
            chunks=chunks,
        )

        self.assertEqual(results[0]["chunk_id"], "jar")
        self.assertIn("item_label_normalized", results[0]["matched_fields"])

    def test_minimum_score_threshold_blocks_weak_matches(self):
        chunks = [
            _chunk(
                chunk_id="generic-fallback",
                generalizable=True,
                item_labels=[],
                materials=[],
                categories=[],
                condition_flags=[],
            )
        ]

        results = retrieve_guidance_chunks(
            item_label="mystery object",
            material=None,
            category=None,
            chunks=chunks,
            min_score=MIN_RETRIEVAL_SCORE + 1.0,
        )

        self.assertEqual(results, [])

    def test_dsny_chunks_are_excluded_when_location_missing(self):
        chunks = [
            _chunk(
                chunk_id="dsny",
                source_name="NYC DSNY Recycling & Disposal",
                source_type="city_government",
                location_scope="city: New York City",
                generalizable=False,
                categories=["paper/cardboard"],
            )
        ]

        results = retrieve_guidance_chunks(
            item_label=None,
            material=None,
            category="paper/cardboard",
            chunks=chunks,
            location=None,
        )

        self.assertEqual(results, [])

    def test_dsny_chunks_apply_for_nyc_location(self):
        chunks = [
            _chunk(
                chunk_id="dsny",
                source_name="NYC DSNY Recycling & Disposal",
                source_type="city_government",
                location_scope="city: New York City",
                generalizable=False,
                categories=["paper/cardboard"],
            )
        ]

        results = retrieve_guidance_chunks(
            item_label=None,
            material=None,
            category="paper/cardboard",
            chunks=chunks,
            location={"city": "New York City", "state": "NY"},
        )

        self.assertEqual(results[0]["chunk_id"], "dsny")

    def test_calrecycle_chunks_are_excluded_when_location_missing(self):
        chunks = [
            _chunk(
                chunk_id="calrecycle",
                source_name="CalRecycle",
                source_type="state_government",
                location_scope="state: California",
                generalizable=False,
                categories=["organic waste"],
                disposal_actions_supported=["Compost"],
            )
        ]

        results = retrieve_guidance_chunks(
            item_label=None,
            material=None,
            category="organic waste",
            chunks=chunks,
            location=None,
        )

        self.assertEqual(results, [])

    def test_calrecycle_chunks_apply_for_california_location(self):
        chunks = [
            _chunk(
                chunk_id="calrecycle",
                source_name="CalRecycle",
                source_type="state_government",
                location_scope="state: California",
                generalizable=False,
                categories=["organic waste"],
                disposal_actions_supported=["Compost"],
            )
        ]

        results = retrieve_guidance_chunks(
            item_label=None,
            material=None,
            category="organic waste",
            chunks=chunks,
            location={"state": "California"},
        )

        self.assertEqual(results[0]["chunk_id"], "calrecycle")

    def test_paintcare_preserves_location_check_requirement(self):
        chunks = [
            _chunk(
                chunk_id="paintcare",
                source_name="PaintCare",
                generalizable=False,
                requires_location_check=True,
                materials=["paint"],
                disposal_actions_supported=["Drop-off"],
            )
        ]

        results = retrieve_guidance_chunks(
            item_label=None,
            material="paint",
            category=None,
            chunks=chunks,
            location=None,
        )

        self.assertEqual(results[0]["chunk_id"], "paintcare")
        self.assertTrue(results[0]["requires_location_check"])

    def test_battery_retrieval_includes_primary_battery_chunk(self):
        results = retrieve_guidance_chunks(
            item_label="battery",
            material="battery",
            category="batteries",
            item_candidates=["battery", "rechargeable batteries"],
            material_candidates=["battery", "lithium-ion battery"],
            category_candidates=["battery", "electronics"],
            condition_flags=["requires_dropoff", "hazardous"],
            location=None,
            chunks=load_trusted_guidance_chunks(),
        )

        chunk_ids = [result["chunk_id"] for result in results]
        self.assertIn("batteries_01", chunk_ids)

    def test_wired_mouse_excludes_battery_chunks_without_battery_signals(self):
        chunks = [
            _chunk(
                chunk_id="electronics_01",
                title="Electronics drop-off",
                section="electronics",
                item_labels=["computer mouse", "electronics"],
                categories=["electronics/e-waste"],
                disposal_actions_supported=["Drop-off"],
            ),
            _chunk(
                chunk_id="batteries_01",
                title="Battery recycling",
                section="batteries",
                item_labels=["battery", "rechargeable batteries"],
                materials=["battery"],
                categories=["electronics/e-waste"],
                condition_flags=["battery"],
                disposal_actions_supported=["Drop-off"],
            ),
        ]

        results = retrieve_guidance_chunks(
            item_label="Computer Mouse",
            material="Electronics",
            category="Electronics",
            item_candidates=["Computer Mouse", "Mouse"],
            material_candidates=["Electronics"],
            category_candidates=["Electronics"],
            condition_flags=["electronics", "requires_dropoff"],
            visual_evidence="Curved shape, cord, glossy rigid body.",
            chunks=chunks,
        )

        chunk_ids = [result["chunk_id"] for result in results]
        self.assertIn("electronics_01", chunk_ids)
        self.assertNotIn("batteries_01", chunk_ids)

    def test_wireless_mouse_can_include_battery_chunks(self):
        chunks = [
            _chunk(
                chunk_id="electronics_01",
                title="Electronics drop-off",
                section="electronics",
                item_labels=["computer mouse", "electronics"],
                categories=["electronics/e-waste"],
                disposal_actions_supported=["Drop-off"],
            ),
            _chunk(
                chunk_id="batteries_01",
                title="Battery recycling",
                section="batteries",
                item_labels=["battery", "rechargeable batteries"],
                materials=["battery"],
                categories=["electronics/e-waste"],
                condition_flags=["battery"],
                disposal_actions_supported=["Drop-off"],
            ),
        ]

        results = retrieve_guidance_chunks(
            item_label="Wireless Mouse",
            material="Electronics",
            category="Electronics",
            item_candidates=["Wireless Mouse", "Computer Mouse"],
            material_candidates=["Electronics"],
            category_candidates=["Electronics"],
            condition_flags=["electronics", "requires_dropoff"],
            visual_evidence="Wireless mouse with battery compartment visible.",
            chunks=chunks,
        )

        chunk_ids = [result["chunk_id"] for result in results]
        self.assertIn("batteries_01", chunk_ids)

    def test_visual_observations_can_make_battery_chunk_relevant(self):
        chunks = [
            _chunk(
                chunk_id="electronics_01",
                title="Electronics drop-off",
                section="electronics",
                item_labels=["computer mouse", "electronics"],
                categories=["electronics/e-waste"],
                disposal_actions_supported=["Drop-off"],
            ),
            _chunk(
                chunk_id="batteries_01",
                title="Battery recycling",
                section="batteries",
                item_labels=["battery", "rechargeable batteries"],
                materials=["battery"],
                categories=["electronics/e-waste"],
                condition_flags=["battery"],
                disposal_actions_supported=["Drop-off"],
            ),
        ]

        results = retrieve_guidance_chunks(
            item_label="Computer Mouse",
            material="Electronics",
            category="Electronics",
            item_candidates=["Computer Mouse"],
            material_candidates=["Electronics"],
            category_candidates=["Electronics"],
            condition_flags=["electronics", "requires_dropoff"],
            visual_observations=[
                {
                    "aspect": "power_source",
                    "value": "battery compartment visible",
                    "confidence": 0.86,
                    "evidence": "Small removable cover on underside.",
                }
            ],
            chunks=chunks,
        )

        chunk_ids = [result["chunk_id"] for result in results]
        self.assertIn("batteries_01", chunk_ids)

    def test_specific_visual_context_blocks_generic_category_only_match(self):
        chunks = [
            _chunk(
                chunk_id="generic-plastic",
                categories=["plastic"],
                disposal_actions_supported=["Recycle"],
            )
        ]

        results = retrieve_guidance_chunks(
            item_label="Used snack wrapper",
            material="Mixed Material",
            category="Plastic",
            item_candidates=["Used snack wrapper"],
            material_candidates=["Mixed Material"],
            category_candidates=["Plastic"],
            condition_flags=["single_use", "contaminated"],
            visual_observations=[
                {
                    "aspect": "form_factor",
                    "value": "flexible crinkly wrapper",
                    "confidence": 0.9,
                    "evidence": "Thin pouch-like packaging.",
                }
            ],
            specific_context_required=True,
            chunks=chunks,
        )

        self.assertEqual(results, [])

    def test_textile_retrieval_includes_earth911_chunk(self):
        results = retrieve_guidance_chunks(
            item_label="clothing",
            material="fabric",
            category="textiles",
            item_candidates=["clothing", "shirt", "old clothes"],
            material_candidates=["fabric", "textile"],
            category_candidates=["textiles", "reuse/donation"],
            condition_flags=["clean_and_dry"],
            location=None,
            chunks=load_trusted_guidance_chunks(),
        )

        chunk_ids = [result["chunk_id"] for result in results]
        self.assertIn("textiles_donation_01", chunk_ids)

    def test_pencil_mixed_material_does_not_retrieve_earth911_by_generic_material(self):
        results = retrieve_guidance_chunks(
            item_label="Pencil",
            material="Mixed Material",
            category="Mixed Material",
            item_candidates=["Pencil"],
            material_candidates=["Mixed Material", "Unknown"],
            category_candidates=["Mixed Material", "Household item"],
            condition_flags=[],
            location=None,
            chunks=load_trusted_guidance_chunks(),
        )

        chunk_ids = [result["chunk_id"] for result in results]
        self.assertNotIn("textiles_donation_01", chunk_ids)

    def test_curtain_generic_household_terms_do_not_retrieve_earth911(self):
        results = retrieve_guidance_chunks(
            item_label="Curtain",
            material="Unknown",
            category="Household item",
            item_candidates=["Curtain"],
            material_candidates=["Unknown", "Mixed Material"],
            category_candidates=["Household item", "General", "Other"],
            condition_flags=[],
            location=None,
            chunks=load_trusted_guidance_chunks(),
        )

        chunk_ids = [result["chunk_id"] for result in results]
        self.assertNotIn("textiles_donation_01", chunk_ids)

    def test_battery_retrieval_does_not_include_paintcare_chunk(self):
        results = retrieve_guidance_chunks(
            item_label="battery",
            material="battery",
            category="batteries",
            item_candidates=["battery", "rechargeable batteries"],
            material_candidates=["battery"],
            category_candidates=["battery", "electronics"],
            condition_flags=["requires_dropoff", "hazardous"],
            location=None,
            chunks=load_trusted_guidance_chunks(),
        )

        chunk_ids = [result["chunk_id"] for result in results]
        self.assertNotIn("hhw_02", chunk_ids)

    def test_condition_flag_overlap_alone_is_not_enough_to_pass_threshold(self):
        chunks = [
            _chunk(
                chunk_id="paintcare-like",
                source_name="PaintCare",
                generalizable=False,
                requires_location_check=True,
                materials=["paint"],
                categories=["paint/household hazardous waste"],
                condition_flags=["requires_dropoff", "hazardous"],
                disposal_actions_supported=["Drop-off"],
            )
        ]

        results = retrieve_guidance_chunks(
            item_label="battery",
            material="battery",
            category="batteries",
            condition_flags=["requires_dropoff", "hazardous"],
            location=None,
            chunks=chunks,
        )

        self.assertEqual(results, [])

    def test_electronics_aliases_match_e_waste_category_chunks(self):
        chunks = [
            _chunk(
                chunk_id="electronics-dropoff",
                categories=["electronics/e-waste"],
                condition_flags=["requires_dropoff"],
                disposal_actions_supported=["Drop-off"],
            )
        ]

        results = retrieve_guidance_chunks(
            item_label=None,
            material=None,
            category="Electronics",
            category_candidates=["electronics", "e-waste", "electronic waste"],
            condition_flags=["requires_dropoff"],
            chunks=chunks,
        )

        self.assertEqual(results[0]["chunk_id"], "electronics-dropoff")
        self.assertIn("category", results[0]["matched_fields"])

    def test_electronics_retrieval_includes_electronics_chunk(self):
        results = retrieve_guidance_chunks(
            item_label="old laptop",
            material="electronics",
            category="electronics",
            item_candidates=["old laptop"],
            material_candidates=["electronics"],
            category_candidates=["electronics", "e-waste"],
            condition_flags=["requires_dropoff", "electronics"],
            location=None,
            chunks=load_trusted_guidance_chunks(),
        )

        chunk_ids = [result["chunk_id"] for result in results]
        self.assertIn("electronics_01", chunk_ids)

    def test_battery_alias_match_allows_condition_flag_boost_without_paintcare_false_positive(self):
        chunks = [
            _chunk(
                chunk_id="battery-dropoff",
                categories=["batteries"],
                condition_flags=["requires_dropoff", "hazardous"],
                disposal_actions_supported=["Drop-off"],
            ),
            _chunk(
                chunk_id="paintcare-like",
                source_name="PaintCare",
                generalizable=False,
                requires_location_check=True,
                materials=["paint"],
                categories=["paint/household hazardous waste"],
                condition_flags=["requires_dropoff", "hazardous"],
                disposal_actions_supported=["Drop-off"],
            ),
        ]

        results = retrieve_guidance_chunks(
            item_label="rechargeable batteries",
            material="battery",
            category="electronics",
            item_candidates=["battery", "rechargeable batteries"],
            material_candidates=["battery"],
            category_candidates=["battery", "electronics"],
            condition_flags=["requires_dropoff", "hazardous", "dropoff_recommended"],
            chunks=chunks,
        )

        chunk_ids = [result["chunk_id"] for result in results]
        self.assertIn("battery-dropoff", chunk_ids)
        self.assertNotIn("paintcare-like", chunk_ids)

    def test_battery_retrieval_can_include_preparation_guidance_chunk(self):
        results = retrieve_guidance_chunks(
            item_label="battery",
            material="battery",
            category="batteries",
            item_candidates=["battery", "rechargeable batteries"],
            material_candidates=["battery"],
            category_candidates=["battery", "electronics"],
            condition_flags=["requires_dropoff", "hazardous", "battery"],
            location=None,
            chunks=load_trusted_guidance_chunks(),
        )

        chunk_ids = [result["chunk_id"] for result in results]
        self.assertIn("batteries_01", chunk_ids)
        self.assertIn("batteries_02", chunk_ids)


if __name__ == "__main__":
    unittest.main()
