"""Regression checks for Batch 4 cache isolation and persistent quotas."""

from pathlib import Path

from services.report_cache import build_report_cache_key


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (PROJECT_ROOT / "public" / "db" / "script.sql").read_text(encoding="utf-8")
MIGRATION = (
    PROJECT_ROOT / "public" / "db" / "migrations" / "20260914_batch_4_persistent_quota.sql"
).read_text(encoding="utf-8")
ANALYSIS_AGENT = (PROJECT_ROOT / "src" / "agents" / "analysis_agent.py").read_text(
    encoding="utf-8"
)


def test_report_cache_key_changes_for_content_owner_and_chat_session():
    original = build_report_cache_key("user-a", "session-a", "report-one")

    assert original != build_report_cache_key("user-a", "session-a", "report-two")
    assert original != build_report_cache_key("user-b", "session-a", "report-one")
    assert original != build_report_cache_key("user-a", "session-b", "report-one")


def test_report_cache_key_does_not_contain_report_text():
    report = "Sensitive patient report text"
    cache_key = build_report_cache_key("user-a", "session-a", report)

    assert report not in cache_key
    assert cache_key == build_report_cache_key("user-a", "session-a", report)


def test_database_quota_is_persistent_and_only_exposed_through_authenticated_rpcs():
    assert "CREATE TABLE public.analysis_usage" in SCHEMA
    assert "ALTER TABLE public.analysis_usage ENABLE ROW LEVEL SECURITY;" in SCHEMA
    assert "REVOKE ALL ON TABLE public.users, public.chat_sessions, public.chat_messages, public.analysis_usage" in SCHEMA
    assert "CREATE OR REPLACE FUNCTION public.reserve_analysis_quota" in SCHEMA
    assert "GRANT EXECUTE ON FUNCTION public.reserve_analysis_quota(INTEGER) TO authenticated;" in SCHEMA
    assert "FROM anon, authenticated" in MIGRATION


def test_quota_reservation_is_atomic_and_agent_releases_failed_analyses():
    assert "ON CONFLICT (user_id) DO UPDATE" in MIGRATION
    assert "analysis_count < limit_value" in MIGRATION
    assert "reserve_analysis_quota(ANALYSIS_DAILY_LIMIT)" in ANALYSIS_AGENT
    assert "release_analysis_quota()" in ANALYSIS_AGENT
    assert "st.session_state.analysis_count" not in ANALYSIS_AGENT
