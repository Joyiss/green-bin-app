import unittest
from unittest.mock import MagicMock, patch

from repositories import service_provider_repository as repository


class Query:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def select(self, *_args): return self
    def eq(self, field, value):
        self.filters.append((field, value))
        return self
    def order(self, *_args, **_kwargs): return self
    def execute(self):
        response = MagicMock()
        response.data = self.rows
        return response


class ServiceProviderRepositoryTests(unittest.TestCase):
    def test_current_provider_is_hash_scoped_and_location_specific(self):
        query = Query([
            {"id": "old", "city": "Atlanta", "county": "Fulton", "state": "Georgia"},
            {"id": "current", "city": "  Seattle ", "county": None, "state": "WASHINGTON"},
        ])
        client = MagicMock()
        client.table.return_value = query
        with patch.object(repository, "_client", return_value=client):
            result = repository.current_provider(
                client_id_hash="a" * 64, city="seattle", county="", state="washington"
            )
        self.assertEqual(result["id"], "current")
        self.assertIn(("client_id_hash", "a" * 64), query.filters)

    def test_different_location_returns_none(self):
        query = Query([{"id": "old", "city": "Atlanta", "county": None, "state": "Georgia"}])
        client = MagicMock()
        client.table.return_value = query
        with patch.object(repository, "_client", return_value=client):
            result = repository.current_provider(
                client_id_hash="b" * 64, city="Seattle", county=None, state="Washington"
            )
        self.assertIsNone(result)

    def test_rpc_parameters_use_only_client_hash(self):
        with patch.object(repository, "_rpc_row", return_value={"allowed": True}) as rpc:
            repository.reserve_verification(
                client_id_hash="c" * 64, key="provider-key",
                now=__import__("datetime").datetime.now(__import__("datetime").UTC),
            )
        params = rpc.call_args.args[1]
        self.assertEqual(params["p_client_id_hash"], "c" * 64)
        self.assertNotIn("client_id", params)


if __name__ == "__main__":
    unittest.main()
