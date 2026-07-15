import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from repositories import disposal_guidance_repository


class DisposalGuidanceRepositoryTests(unittest.TestCase):
    def setUp(self):
        disposal_guidance_repository._SUPABASE_CLIENT = None
        self.env_patch = patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_KEY": "service-role-key",
            },
            clear=True,
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.addCleanup(setattr, disposal_guidance_repository, "_SUPABASE_CLIENT", None)

    def test_get_guidance_by_cache_key_ignores_expired_rows(self):
        expired_row = {
            "id": "row-1",
            "cache_key": "cache-key",
            "expires_at": "2000-01-01T00:00:00+00:00",
        }
        limit_builder = Mock()
        limit_builder.execute.return_value = SimpleNamespace(data=[expired_row])
        eq_builder = Mock()
        eq_builder.limit.return_value = limit_builder
        select_builder = Mock()
        select_builder.eq.return_value = eq_builder
        table_builder = Mock()
        table_builder.select.return_value = select_builder
        mock_client = Mock()
        mock_client.table.return_value = table_builder

        with patch(
            "repositories.disposal_guidance_repository.create_client",
            return_value=mock_client,
        ):
            row = disposal_guidance_repository.get_guidance_by_cache_key("cache-key")

        self.assertIsNone(row)
        mock_client.table.assert_called_once_with("disposal_guidance")
        select_builder.eq.assert_called_once_with("cache_key", "cache-key")

    def test_upsert_guidance_cache_row_uses_cache_key_conflict(self):
        expected_row = {"id": "row-1", "cache_key": "cache-key"}
        upsert_builder = Mock()
        upsert_builder.execute.return_value = SimpleNamespace(data=[expected_row])
        table_builder = Mock()
        table_builder.upsert.return_value = upsert_builder
        mock_client = Mock()
        mock_client.table.return_value = table_builder
        payload = {
            "cache_key": "cache-key",
            "steps": ["Use drop-off."],
            "guidance_metadata": {"retrieved_chunk_ids": ["chunk-1"]},
        }

        with patch(
            "repositories.disposal_guidance_repository.create_client",
            return_value=mock_client,
        ):
            row = disposal_guidance_repository.upsert_guidance_cache_row(payload)

        self.assertEqual(row, expected_row)
        table_builder.upsert.assert_called_once_with(
            payload,
            on_conflict="cache_key",
        )

    def test_record_guidance_cache_hit_uses_atomic_rpc_and_fails_softly(self):
        rpc_builder = Mock()
        mock_client = Mock()
        mock_client.rpc.return_value = rpc_builder

        with patch(
            "repositories.disposal_guidance_repository.create_client",
            return_value=mock_client,
        ):
            self.assertTrue(
                disposal_guidance_repository.record_guidance_cache_hit("row-1")
            )

        mock_client.rpc.assert_called_once_with(
            "increment_disposal_guidance_hit_count",
            {"row_id": "row-1"},
        )
        rpc_builder.execute.assert_called_once_with()

        mock_client.rpc.side_effect = ValueError("rpc failed")
        self.assertFalse(disposal_guidance_repository.record_guidance_cache_hit("row-1"))


if __name__ == "__main__":
    unittest.main()
