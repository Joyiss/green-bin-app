import unittest

from fastapi.testclient import TestClient

from main import app
from materials import MATERIAL_LABELS


class MaterialLabelsEndpointTests(unittest.TestCase):
    def test_material_labels_returns_supported_inventory(self):
        client = TestClient(app)

        response = client.get("/material_labels")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"labels": MATERIAL_LABELS})


if __name__ == "__main__":
    unittest.main()
