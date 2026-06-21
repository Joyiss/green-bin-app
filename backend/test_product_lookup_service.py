import unittest
from unittest.mock import Mock, patch

import requests

from services.product_lookup_service import (
    get_product_by_barcode,
    map_product_to_item_label,
)


class ProductLookupServiceTests(unittest.TestCase):
    @patch("services.product_lookup_service.requests.get")
    def test_get_product_by_barcode_returns_normalized_success(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "status": 1,
            "product": {
                "product_name": "Spring Water",
                "brands": "Acme",
                "categories": "Waters, Beverages",
                "categories_tags": ["en:waters", "en:beverages"],
                "packaging": "Plastic bottle",
                "packaging_tags": ["en:plastic-bottle"],
                "quantity": "500 ml",
                "generic_name": "Bottled water",
            },
        }
        mock_get.return_value = response

        result = get_product_by_barcode("0123456789012")

        self.assertEqual(
            result,
            {
                "barcode_value": "0123456789012",
                "product_name": "Spring Water",
                "brand": "Acme",
                "category": "Waters, Beverages",
                "packaging": "Plastic bottle",
                "quantity": "500 ml",
                "generic_name": "Bottled water",
                "source": "open_food_facts",
                "raw_categories": ["en:waters", "en:beverages"],
                "raw_packaging_tags": ["en:plastic-bottle"],
            },
        )
        self.assertNotIn("product", result)
        self.assertEqual(
            mock_get.call_args.kwargs["params"]["fields"],
            "code,status,status_verbose,product_name,brands,categories,categories_tags,packaging,packaging_tags,quantity,generic_name",
        )
        self.assertEqual(
            mock_get.call_args.kwargs["headers"],
            {"User-Agent": "GreenBin/0.1 (student project; contact: local-dev)"},
        )

    @patch("services.product_lookup_service.requests.get")
    def test_get_product_by_barcode_accepts_known_open_food_facts_barcode(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "code": "3017624010701",
            "status": 1,
            "status_verbose": "product found",
            "product": {
                "product_name": "Nutella",
                "brands": "Ferrero",
                "categories": "Spreads, Chocolate spreads",
                "categories_tags": ["en:spreads", "en:chocolate-spreads"],
                "packaging": "Jar",
                "packaging_tags": ["en:glass-jar"],
                "quantity": "400 g",
                "generic_name": "Hazelnut cocoa spread",
            },
        }
        mock_get.return_value = response

        result = get_product_by_barcode("3017624010701")

        self.assertEqual(
            result,
            {
                "barcode_value": "3017624010701",
                "product_name": "Nutella",
                "brand": "Ferrero",
                "category": "Spreads, Chocolate spreads",
                "packaging": "Jar",
                "quantity": "400 g",
                "generic_name": "Hazelnut cocoa spread",
                "source": "open_food_facts",
                "raw_categories": ["en:spreads", "en:chocolate-spreads"],
                "raw_packaging_tags": ["en:glass-jar"],
            },
        )

    @patch("services.product_lookup_service.requests.get")
    def test_get_product_by_barcode_returns_none_for_product_not_found(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"status": 0, "product": None}
        mock_get.return_value = response

        self.assertIsNone(get_product_by_barcode("0123456789012"))

    @patch("services.product_lookup_service.requests.get", side_effect=requests.Timeout())
    def test_get_product_by_barcode_returns_none_for_request_error(self, _mock_get):
        self.assertIsNone(get_product_by_barcode("0123456789012"))

    def test_map_product_to_item_label_maps_plastic_bottle(self):
        result = map_product_to_item_label(
            {
                "product_name": "Spring Water",
                "brand": "Acme",
                "category": "Waters",
                "packaging": "Plastic bottle",
                "quantity": "500 ml",
                "source": "open_food_facts",
                "raw_categories": ["en:waters"],
                "raw_packaging_tags": ["en:plastic-bottle"],
            }
        )

        self.assertEqual(
            result,
            {
                "item_label": "Plastic water bottle",
                "confidence": 0.85,
                "reason": "open_food_facts_keyword_match",
            },
        )

    def test_map_product_to_item_label_maps_aluminum_can(self):
        result = map_product_to_item_label(
            {
                "product_name": "Cola",
                "brand": "Acme",
                "category": "Soft drinks",
                "packaging": "Aluminum can",
                "quantity": "330 ml",
                "source": "open_food_facts",
                "raw_categories": ["en:soft-drinks"],
                "raw_packaging_tags": ["en:aluminum-can"],
            }
        )

        self.assertEqual(
            result,
            {
                "item_label": "Soda can",
                "confidence": 0.85,
                "reason": "open_food_facts_keyword_match",
            },
        )

    def test_map_product_to_item_label_maps_carton(self):
        result = map_product_to_item_label(
            {
                "product_name": "Orange Juice",
                "brand": "Acme",
                "category": "Juices",
                "packaging": "Drink carton",
                "quantity": "1 L",
                "source": "open_food_facts",
                "raw_categories": ["en:juices"],
                "raw_packaging_tags": ["en:carton"],
            }
        )

        self.assertEqual(
            result,
            {
                "item_label": "Drink carton",
                "confidence": 0.85,
                "reason": "open_food_facts_keyword_match",
            },
        )

    def test_map_product_to_item_label_returns_none_for_unclear_product(self):
        result = map_product_to_item_label(
            {
                "product_name": "Organic Lentils",
                "brand": "Acme",
                "category": "Legumes",
                "packaging": "Bag",
                "quantity": "500 g",
                "source": "open_food_facts",
                "raw_categories": ["en:legumes"],
                "raw_packaging_tags": ["en:bag"],
            }
        )

        self.assertIsNone(result)

    def test_map_product_to_item_label_does_not_map_food_category_without_packaging_evidence(self):
        result = map_product_to_item_label(
            {
                "barcode_value": "0072554001628",
                "product_name": "Frozen dairy dessert cone",
                "brand": "Acme",
                "category": "Ice cream cones",
                "packaging": None,
                "quantity": "120 ml",
                "generic_name": None,
                "source": "open_food_facts",
                "raw_categories": ["en:ice-cream-cones"],
                "raw_packaging_tags": [],
            }
        )

        self.assertIsNone(result)

    def test_map_product_to_item_label_maps_nutella_glass_jar(self):
        result = map_product_to_item_label(
            {
                "barcode_value": "3017624010701",
                "product_name": "Nutella",
                "brand": "Ferrero",
                "category": "Spreads, Chocolate spreads",
                "packaging": "Jar",
                "quantity": "400 g",
                "generic_name": "Hazelnut cocoa spread",
                "source": "open_food_facts",
                "raw_categories": ["en:spreads", "en:chocolate-spreads"],
                "raw_packaging_tags": ["en:glass-jar"],
            }
        )

        self.assertEqual(
            result,
            {
                "item_label": "Glass jar",
                "confidence": 0.85,
                "reason": "open_food_facts_keyword_match",
            },
        )


if __name__ == "__main__":
    unittest.main()
