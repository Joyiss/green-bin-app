import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from repositories import cache_repository


class CacheRepositoryTests(unittest.TestCase):
    def setUp(self):
        cache_repository._SUPABASE_CLIENT = None
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
        self.addCleanup(setattr, cache_repository, "_SUPABASE_CLIENT", None)

    def test_get_supabase_client_is_lazy_and_cached(self):
        mock_client = Mock()

        with patch("repositories.cache_repository.create_client", return_value=mock_client) as mock_create:
            first_client = cache_repository._get_supabase_client()
            second_client = cache_repository._get_supabase_client()

        self.assertIs(first_client, mock_client)
        self.assertIs(second_client, mock_client)
        mock_create.assert_called_once_with(
            "https://example.supabase.co",
            "service-role-key",
        )

    def test_get_supabase_client_requires_supabase_url(self):
        with patch.dict(os.environ, {"SUPABASE_KEY": "service-role-key"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "SUPABASE_URL is not set"):
                cache_repository._get_supabase_client()

    def test_get_supabase_client_requires_supabase_key(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "SUPABASE_KEY is not set"):
                cache_repository._get_supabase_client()

    def test_save_recognition_record_returns_inserted_row(self):
        expected_row = {
            "id": "record-123",
            "item_label": "Calculator",
            "recognition_source": "manual-test",
            "clip_embedding": None,
            "metadata": {},
        }
        table_builder = Mock()
        insert_builder = Mock()
        insert_builder.execute.return_value = SimpleNamespace(data=[expected_row])
        table_builder.insert.return_value = insert_builder
        mock_client = Mock()
        mock_client.table.return_value = table_builder

        with patch("repositories.cache_repository.create_client", return_value=mock_client):
            saved_row = cache_repository.save_recognition_record(
                item_label="Calculator",
                recognition_source="manual-test",
                clip_embedding=None,
                metadata=None,
            )

        self.assertEqual(saved_row, expected_row)
        mock_client.table.assert_called_once_with("recognition_cache")
        table_builder.insert.assert_called_once_with(
            {
                "phash": None,
                "clip_embedding": None,
                "item_label": "Calculator",
                "recognition_source": "manual-test",
                "confidence": None,
                "verified": False,
                "metadata": {},
            }
        )
        insert_builder.execute.assert_called_once_with()

    def test_save_recognition_record_raises_clear_error_on_supabase_failure(self):
        table_builder = Mock()
        table_builder.insert.side_effect = ValueError("insert failed")
        mock_client = Mock()
        mock_client.table.return_value = table_builder

        with patch("repositories.cache_repository.create_client", return_value=mock_client):
            with self.assertRaisesRegex(
                RuntimeError,
                "Failed to save recognition cache record: insert failed",
            ):
                cache_repository.save_recognition_record(
                    item_label="Calculator",
                    recognition_source="manual-test",
                )

    def test_get_recognition_record_by_id_returns_row_or_none(self):
        expected_row = {"id": "record-123", "item_label": "Calculator"}

        maybe_single_builder = Mock()
        maybe_single_builder.execute.side_effect = [
            SimpleNamespace(data=expected_row),
            None,
        ]
        eq_builder = Mock()
        eq_builder.maybe_single.return_value = maybe_single_builder
        select_builder = Mock()
        select_builder.eq.return_value = eq_builder
        table_builder = Mock()
        table_builder.select.return_value = select_builder
        mock_client = Mock()
        mock_client.table.return_value = table_builder

        with patch("repositories.cache_repository.create_client", return_value=mock_client):
            found_row = cache_repository.get_recognition_record_by_id("record-123")
            missing_row = cache_repository.get_recognition_record_by_id("missing-record")

        self.assertEqual(found_row, expected_row)
        self.assertIsNone(missing_row)
        select_builder.eq.assert_any_call("id", "record-123")
        select_builder.eq.assert_any_call("id", "missing-record")

    def test_get_recognition_record_by_id_raises_clear_error_on_supabase_failure(self):
        select_builder = Mock()
        select_builder.eq.side_effect = ValueError("lookup failed")
        table_builder = Mock()
        table_builder.select.return_value = select_builder
        mock_client = Mock()
        mock_client.table.return_value = table_builder

        with patch("repositories.cache_repository.create_client", return_value=mock_client):
            with self.assertRaisesRegex(
                RuntimeError,
                "Failed to fetch recognition cache record by id: lookup failed",
            ):
                cache_repository.get_recognition_record_by_id("record-123")

    def test_find_recognition_records_by_phash_returns_plain_dicts(self):
        expected_rows = [
            {"id": "record-1", "phash": "abcd1234", "item_label": "Calculator"},
            {"id": "record-2", "phash": "abcd1234", "item_label": "Keyboard"},
        ]
        eq_builder = Mock()
        eq_builder.execute.return_value = SimpleNamespace(data=expected_rows)
        select_builder = Mock()
        select_builder.eq.return_value = eq_builder
        table_builder = Mock()
        table_builder.select.return_value = select_builder
        mock_client = Mock()
        mock_client.table.return_value = table_builder

        with patch("repositories.cache_repository.create_client", return_value=mock_client):
            rows = cache_repository.find_recognition_records_by_phash("abcd1234")

        self.assertEqual(rows, expected_rows)
        select_builder.eq.assert_called_once_with("phash", "abcd1234")

    def test_find_recognition_records_by_phash_raises_clear_error_on_supabase_failure(self):
        select_builder = Mock()
        select_builder.eq.side_effect = ValueError("query failed")
        table_builder = Mock()
        table_builder.select.return_value = select_builder
        mock_client = Mock()
        mock_client.table.return_value = table_builder

        with patch("repositories.cache_repository.create_client", return_value=mock_client):
            with self.assertRaisesRegex(
                RuntimeError,
                "Failed to find recognition cache records by phash: query failed",
            ):
                cache_repository.find_recognition_records_by_phash("abcd1234")

    def test_find_nearest_phash_match_returns_best_row_with_distance(self):
        rows = [
            {"id": "record-1", "phash": "aaaa1111", "verified": False, "confidence": 0.8},
            {"id": "record-2", "phash": "bbbb2222", "verified": True, "confidence": 0.7},
            {"id": "record-3", "phash": None, "verified": True, "confidence": 1.0},
        ]
        execute_builder = Mock()
        execute_builder.execute.return_value = SimpleNamespace(data=rows)
        table_builder = Mock()
        table_builder.select.return_value = execute_builder
        mock_client = Mock()
        mock_client.table.return_value = table_builder

        with (
            patch("repositories.cache_repository.create_client", return_value=mock_client),
            patch("repositories.cache_repository.find_recognition_records_by_phash", return_value=[]),
            patch(
                "repositories.cache_repository.phash_distance",
                side_effect=lambda left, right: {"aaaa1111": 5, "bbbb2222": 3}[right],
            ),
        ):
            match = cache_repository.find_nearest_phash_match("queryhash")

        self.assertEqual(
            match,
            {
                "id": "record-2",
                "phash": "bbbb2222",
                "verified": True,
                "confidence": 0.7,
                "phash_distance": 3,
            },
        )

    def test_find_nearest_phash_match_returns_none_when_no_rows_qualify(self):
        rows = [
            {"id": "record-1", "phash": "aaaa1111", "verified": False, "confidence": 0.8},
        ]
        execute_builder = Mock()
        execute_builder.execute.return_value = SimpleNamespace(data=rows)
        table_builder = Mock()
        table_builder.select.return_value = execute_builder
        mock_client = Mock()
        mock_client.table.return_value = table_builder

        with (
            patch("repositories.cache_repository.create_client", return_value=mock_client),
            patch("repositories.cache_repository.find_recognition_records_by_phash", return_value=[]),
            patch("repositories.cache_repository.phash_distance", return_value=7),
        ):
            match = cache_repository.find_nearest_phash_match("queryhash", max_distance=6)

        self.assertIsNone(match)

    def test_find_nearest_phash_match_tie_breaks_by_verified_then_confidence(self):
        rows = [
            {"id": "record-1", "phash": "aaaa1111", "verified": False, "confidence": 0.95},
            {"id": "record-2", "phash": "bbbb2222", "verified": True, "confidence": 0.3},
            {"id": "record-3", "phash": "cccc3333", "verified": True, "confidence": 0.8},
        ]
        execute_builder = Mock()
        execute_builder.execute.return_value = SimpleNamespace(data=rows)
        table_builder = Mock()
        table_builder.select.return_value = execute_builder
        mock_client = Mock()
        mock_client.table.return_value = table_builder

        with (
            patch("repositories.cache_repository.create_client", return_value=mock_client),
            patch("repositories.cache_repository.find_recognition_records_by_phash", return_value=[]),
            patch("repositories.cache_repository.phash_distance", return_value=4),
        ):
            match = cache_repository.find_nearest_phash_match("queryhash")

        self.assertEqual(match["id"], "record-3")
        self.assertEqual(match["phash_distance"], 4)

    def test_find_nearest_phash_match_raises_clear_error_on_supabase_failure(self):
        select_builder = Mock()
        select_builder.execute.side_effect = ValueError("query failed")
        table_builder = Mock()
        table_builder.select.return_value = select_builder
        mock_client = Mock()
        mock_client.table.return_value = table_builder

        with (
            patch("repositories.cache_repository.create_client", return_value=mock_client),
            patch("repositories.cache_repository.find_recognition_records_by_phash", return_value=[]),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Failed to find nearest recognition cache record by phash: query failed",
            ):
                cache_repository.find_nearest_phash_match("queryhash")

    def test_find_nearest_phash_match_raises_on_unexpected_row_shape(self):
        execute_builder = Mock()
        execute_builder.execute.return_value = SimpleNamespace(data=["bad-row"])
        table_builder = Mock()
        table_builder.select.return_value = execute_builder
        mock_client = Mock()
        mock_client.table.return_value = table_builder

        with (
            patch("repositories.cache_repository.create_client", return_value=mock_client),
            patch("repositories.cache_repository.find_recognition_records_by_phash", return_value=[]),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Failed to find nearest recognition cache record by phash: Supabase returned an unexpected row shape.",
            ):
                cache_repository.find_nearest_phash_match("queryhash")

    def test_find_nearest_phash_match_prefers_exact_match_before_nearest_scan(self):
        exact_matches = [
            {"id": "record-1", "phash": "abcd1234", "verified": False, "confidence": 0.7},
            {"id": "record-2", "phash": "abcd1234", "verified": True, "confidence": 0.6},
        ]
        select_builder = Mock()
        table_builder = Mock()
        table_builder.select.return_value = select_builder
        mock_client = Mock()
        mock_client.table.return_value = table_builder

        with (
            patch("repositories.cache_repository.create_client", return_value=mock_client),
            patch(
                "repositories.cache_repository.find_recognition_records_by_phash",
                return_value=exact_matches,
            ),
        ):
            match = cache_repository.find_nearest_phash_match("abcd1234")

        self.assertEqual(
            match,
            {
                "id": "record-2",
                "phash": "abcd1234",
                "verified": True,
                "confidence": 0.6,
                "phash_distance": 0,
            },
        )
        table_builder.select.assert_not_called()

    def test_delete_recognition_record_by_id_returns_deleted_row_or_none(self):
        expected_row = {"id": "record-123", "item_label": "Calculator"}

        eq_builder = Mock()
        eq_builder.execute.side_effect = [
            SimpleNamespace(data=[expected_row]),
            SimpleNamespace(data=[]),
        ]
        delete_builder = Mock()
        delete_builder.eq.return_value = eq_builder
        table_builder = Mock()
        table_builder.delete.return_value = delete_builder
        mock_client = Mock()
        mock_client.table.return_value = table_builder

        with patch("repositories.cache_repository.create_client", return_value=mock_client):
            deleted_row = cache_repository.delete_recognition_record_by_id("record-123")
            missing_row = cache_repository.delete_recognition_record_by_id("missing-record")

        self.assertEqual(deleted_row, expected_row)
        self.assertIsNone(missing_row)
        delete_builder.eq.assert_any_call("id", "record-123")
        delete_builder.eq.assert_any_call("id", "missing-record")
        self.assertEqual(eq_builder.execute.call_count, 2)

    def test_delete_recognition_record_by_id_raises_clear_error_on_supabase_failure(self):
        delete_builder = Mock()
        delete_builder.eq.side_effect = ValueError("delete failed")
        table_builder = Mock()
        table_builder.delete.return_value = delete_builder
        mock_client = Mock()
        mock_client.table.return_value = table_builder

        with patch("repositories.cache_repository.create_client", return_value=mock_client):
            with self.assertRaisesRegex(
                RuntimeError,
                "Failed to delete recognition cache record by id: delete failed",
            ):
                cache_repository.delete_recognition_record_by_id("record-123")


if __name__ == "__main__":
    unittest.main()
