"""Server-to-server access to refresh-safe, opaque browser sessions."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st

from utils.app_logging import get_logger, log_exception


logger = get_logger(__name__)
COOKIE_NAME = "health_insights_session"


def is_configured():
    """Return whether the companion session service has been configured."""
    return bool(getattr(st, "secrets", {}).get("APP_SESSION_INTERNAL_KEY"))


def public_login_url(mode="login"):
    """Return the browser-facing sign-in or sign-up URL."""
    public_url = st.secrets.get("SESSION_SERVICE_PUBLIC_URL", "http://localhost:8503")
    base_url = st.secrets.get("APP_BASE_URL", "http://localhost:8502")
    return f"{public_url}/{mode}?return_to={base_url}"


def restore_session():
    """Retrieve tokens server-side for the opaque cookie presented by the browser."""
    session_id = _browser_session_id()
    if not session_id or not is_configured():
        return None

    try:
        payload = _internal_request("/internal/session", session_id)
        return payload if payload.get("access_token") and payload.get("refresh_token") else None
    except HTTPError as error:
        # The local companion service keeps sessions in memory. A normal
        # service restart leaves the browser with an expired opaque cookie;
        # treat its 401 response as a logged-out state, not an application
        # error. The next sign-in replaces the cookie.
        if error.code == 401:
            return None
        log_exception(logger, "persistent_session_restore_failed", error, component="auth")
        return None
    except (URLError, ValueError, KeyError) as error:
        log_exception(logger, "persistent_session_restore_failed", error, component="auth")
        return None


def update_tokens(access_token, refresh_token):
    """Keep refreshed Supabase credentials in the server-only session record."""
    session_id = _browser_session_id()
    if not session_id or not is_configured():
        return False

    try:
        _internal_request(
            "/internal/update",
            session_id,
            {"access_token": access_token, "refresh_token": refresh_token},
        )
        return True
    except (HTTPError, URLError, ValueError) as error:
        log_exception(logger, "persistent_session_update_failed", error, component="auth")
        return False


def revoke_session():
    """Invalidate the server-side session after logout or expiry."""
    session_id = _browser_session_id()
    if not session_id or not is_configured():
        return False

    try:
        _internal_request("/internal/revoke", session_id)
        return True
    except (HTTPError, URLError, ValueError) as error:
        log_exception(logger, "persistent_session_revoke_failed", error, component="auth")
        return False


def _internal_request(path, session_id, body=None):
    service_url = st.secrets.get("SESSION_SERVICE_URL", "http://127.0.0.1:8503")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        f"{service_url}{path}",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Cookie": f"{COOKIE_NAME}={session_id}",
            "X-Session-Internal-Key": st.secrets["APP_SESSION_INTERNAL_KEY"],
        },
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _browser_session_id():
    """Read the opaque cookie if this Streamlit runtime exposes it."""
    context = getattr(st, "context", None)
    cookies = getattr(context, "cookies", {})
    return cookies.get(COOKIE_NAME)
