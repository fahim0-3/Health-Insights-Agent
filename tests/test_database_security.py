"""Regression checks for the version-controlled Supabase security contract."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (PROJECT_ROOT / "public" / "db" / "script.sql").read_text(encoding="utf-8")
MIGRATION = (
    PROJECT_ROOT / "public" / "db" / "migrations" / "20260914_batch_2_rls.sql"
).read_text(encoding="utf-8")
AUTH_SERVICE = (PROJECT_ROOT / "src" / "auth" / "auth_service.py").read_text(
    encoding="utf-8"
)


def test_profile_schema_uses_supabase_auth_as_the_source_of_truth():
    assert "REFERENCES auth.users(id) ON DELETE CASCADE" in SCHEMA
    assert "CREATE TRIGGER on_auth_user_created" in SCHEMA
    assert "FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user()" in SCHEMA


def test_schema_enables_rls_and_removes_anonymous_table_access():
    for table in ("users", "chat_sessions", "chat_messages"):
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;" in SCHEMA

    assert "REVOKE ALL ON TABLE public.users, public.chat_sessions, public.chat_messages" in SCHEMA
    assert "FROM anon, authenticated;" in SCHEMA


def test_sessions_and_messages_are_scoped_to_the_authenticated_user():
    assert "WITH CHECK ((SELECT auth.uid()) = user_id);" in SCHEMA
    assert "public.chat_sessions.user_id = (SELECT auth.uid())" in SCHEMA


def test_existing_database_migration_and_signup_flow_use_trigger_owned_profiles():
    assert "Cannot link public.users to auth.users" in MIGRATION
    assert "FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE" in MIGRATION
    assert '"options": {"data": {"name": name}}' in AUTH_SERVICE
    assert 'self.supabase.table("users").insert(user_data)' not in AUTH_SERVICE
