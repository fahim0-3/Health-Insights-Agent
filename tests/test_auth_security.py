"""Regression tests for secure Streamlit authentication-session handling."""

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SESSION_MANAGER_SOURCE = (
    PROJECT_ROOT / "src" / "auth" / "session_manager.py"
).read_text(encoding="utf-8")
AUTH_SERVICE_SOURCE = (PROJECT_ROOT / "src" / "auth" / "auth_service.py").read_text(
    encoding="utf-8"
)


class FakeSessionState(dict):
    """Small stand-in for Streamlit's dict-like session state."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def __setattr__(self, name, value):
        self[name] = value


def load_session_manager(monkeypatch, session_state):
    fake_streamlit = SimpleNamespace(
        session_state=session_state,
        errors=[],
        rerun_calls=0,
    )
    fake_streamlit.error = fake_streamlit.errors.append
    fake_streamlit.rerun = lambda: setattr(
        fake_streamlit, "rerun_calls", fake_streamlit.rerun_calls + 1
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    sys.modules.pop("auth.session_manager", None)
    module = importlib.import_module("auth.session_manager")
    return module.SessionManager, fake_streamlit


def test_auth_session_code_does_not_use_browser_storage_or_injected_javascript():
    assert "localStorage" not in SESSION_MANAGER_SOURCE
    assert "sessionStorage" not in SESSION_MANAGER_SOURCE
    assert "unsafe_allow_html" not in SESSION_MANAGER_SOURCE
    assert "_save_to_persistent_storage" not in SESSION_MANAGER_SOURCE
    assert "_restore_from_storage" not in SESSION_MANAGER_SOURCE


def test_auth_service_restores_only_tokens_held_in_streamlit_session():
    assert 'st.session_state.get("auth_token")' in AUTH_SERVICE_SOURCE
    assert 'st.session_state.get("refresh_token")' in AUTH_SERVICE_SOURCE
    assert "Browser local storage is intentionally never used." in AUTH_SERVICE_SOURCE


def test_logout_signs_out_and_removes_all_server_side_session_data(monkeypatch):
    class AuthService:
        def __init__(self):
            self.sign_out_calls = 0

        def sign_out(self):
            self.sign_out_calls += 1

    auth_service = AuthService()
    state = FakeSessionState(
        auth_service=auth_service,
        user={"id": "user-a"},
        auth_token="access-token",
        refresh_token="refresh-token",
        current_session={"id": "chat-a"},
    )
    SessionManager, _ = load_session_manager(monkeypatch, state)

    SessionManager.logout()

    assert auth_service.sign_out_calls == 1
    assert state == {}


def test_idle_session_is_ended_before_any_authenticated_action(monkeypatch):
    class AuthService:
        def __init__(self):
            self.sign_out_calls = 0

        def sign_out(self):
            self.sign_out_calls += 1

        def validate_session_token(self):
            raise AssertionError("Expired sessions must not validate a token")

    auth_service = AuthService()
    state = FakeSessionState(
        auth_service=auth_service,
        user={"id": "user-a"},
        auth_token="access-token",
        refresh_token="refresh-token",
        last_activity=datetime.now() - timedelta(minutes=31),
    )
    SessionManager, fake_streamlit = load_session_manager(monkeypatch, state)

    SessionManager.init_session()

    assert auth_service.sign_out_calls == 1
    assert state == {}
    assert fake_streamlit.rerun_calls == 1
    assert fake_streamlit.errors == ["Session expired. Please log in again."]


def test_invalid_token_ends_the_session(monkeypatch):
    class AuthService:
        def __init__(self):
            self.sign_out_calls = 0

        def sign_out(self):
            self.sign_out_calls += 1

        def validate_session_token(self):
            return None

    auth_service = AuthService()
    state = FakeSessionState(
        auth_service=auth_service,
        user={"id": "user-a"},
        auth_token="access-token",
        refresh_token="refresh-token",
        last_activity=datetime.now(),
    )
    SessionManager, fake_streamlit = load_session_manager(monkeypatch, state)

    SessionManager.init_session()

    assert auth_service.sign_out_calls == 1
    assert state == {}
    assert fake_streamlit.rerun_calls == 1
    assert fake_streamlit.errors == [
        "Your session is no longer valid. Please log in again."
    ]
