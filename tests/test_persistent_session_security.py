"""Regression checks for refresh-safe opaque authentication sessions."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PERSISTENT_SESSION = (PROJECT_ROOT / "src" / "auth" / "persistent_session.py").read_text(
    encoding="utf-8"
)
SESSION_SERVER = (PROJECT_ROOT / "src" / "session_server.py").read_text(
    encoding="utf-8"
)
AUTH_SERVICE = (PROJECT_ROOT / "src" / "auth" / "auth_service.py").read_text(
    encoding="utf-8"
)


def test_refresh_restore_uses_an_opaque_cookie_and_internal_service():
    assert 'COOKIE_NAME = "health_insights_session"' in PERSISTENT_SESSION
    assert '"X-Session-Internal-Key"' in PERSISTENT_SESSION
    assert 'persistent_session.restore_session()' in AUTH_SERVICE
    assert 'target="_self"' in (PROJECT_ROOT / "src" / "components" / "auth_pages.py").read_text(
        encoding="utf-8"
    )


def test_tokens_remain_server_side_and_cookie_has_secure_attributes():
    assert "httponly=True" in SESSION_SERVER
    assert 'samesite="lax"' in SESSION_SERVER
    assert "access_token" not in SESSION_SERVER.split("redirect.set_cookie", 1)[1].split(")", 1)[0]
    assert "localStorage" not in SESSION_SERVER
    assert "sessionStorage" not in SESSION_SERVER


def test_session_service_requires_an_internal_secret_and_revokes_on_logout():
    assert "APP_SESSION_INTERNAL_KEY" in SESSION_SERVER
    assert "hmac.compare_digest" in SESSION_SERVER
    assert "sessions.delete(request.cookies.get(COOKIE_NAME" in SESSION_SERVER


def test_service_restart_treats_an_expired_opaque_cookie_as_logged_out():
    assert "if error.code == 401:" in PERSISTENT_SESSION
    assert "treat its 401 response as a logged-out state" in PERSISTENT_SESSION


def test_example_includes_all_refresh_safe_session_configuration():
    template = (PROJECT_ROOT / ".streamlit" / "secrets.example.toml").read_text(
        encoding="utf-8"
    )
    for setting in (
        "APP_SESSION_INTERNAL_KEY",
        "APP_BASE_URL",
        "SESSION_SERVICE_URL",
        "SESSION_SERVICE_PUBLIC_URL",
        "SESSION_COOKIE_SECURE",
    ):
        assert setting in template
