import unittest
from pathlib import Path


class ServiceProviderMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = (Path(__file__).parent / "migrations" / "007_service_providers.sql").read_text()
        cls.lower = cls.sql.lower()

    def test_uses_client_hash_and_normalized_unique_index(self):
        self.assertIn("client_id_hash text not null", self.lower)
        self.assertNotIn("user_id", self.lower)
        self.assertIn("service_providers_client_provider_location_uidx", self.lower)
        self.assertIn("coalesce(public.normalize_service_provider_field(county), '')", self.lower)

    def test_tables_have_rls_and_backend_only_grants(self):
        for table in (
            "service_providers", "service_provider_verification_cache",
            "service_provider_limit_state",
        ):
            self.assertIn(f"alter table public.{table} enable row level security", self.lower)
            self.assertIn(f"revoke all on public.{table} from public, anon, authenticated", self.lower)
        self.assertNotIn("auth.uid", self.lower)

    def test_rpcs_are_invoker_locked_and_grant_asserted(self):
        self.assertNotIn("security definer", self.lower)
        self.assertGreaterEqual(self.lower.count("security invoker"), 6)
        self.assertIn("set search_path = pg_catalog, public", self.lower)
        self.assertIn("has_function_privilege('anon'", self.lower)
        self.assertIn("acl.grantee = 0", self.lower)
        self.assertIn("grant execute on function public.confirm_service_provider", self.lower)

    def test_confirmation_updates_before_insert(self):
        update_at = self.lower.index("update public.service_providers")
        insert_at = self.lower.index("insert into public.service_providers", update_at)
        self.assertLess(update_at, insert_at)


if __name__ == "__main__":
    unittest.main()
