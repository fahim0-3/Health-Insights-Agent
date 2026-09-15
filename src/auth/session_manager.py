"""Server-side session lifecycle helpers for the Streamlit application.

Authentication tokens stay in ``st.session_state`` for the lifetime of the
current Streamlit connection. They are never written into browser storage.
"""

from datetime import datetime, timedelta

import streamlit as st

from config.app_config import SESSION_TIMEOUT_MINUTES
from config.app_config import ANALYSIS_DAILY_LIMIT


class SessionManager:
    """Manage the authenticated state for one Streamlit browser session."""

    @staticmethod
    def init_session():
        """Create the auth client and reject expired or invalid sessions."""
        if "auth_service" not in st.session_state:
            from auth.auth_service import AuthService

            st.session_state.auth_service = AuthService()

        if "user" not in st.session_state:
            return

        last_activity = st.session_state.get("last_activity")
        if last_activity and datetime.now() - last_activity > timedelta(
            minutes=SESSION_TIMEOUT_MINUTES
        ):
            SessionManager._end_session("Session expired. Please log in again.")
            return

        user_data = st.session_state.auth_service.validate_session_token()
        if not user_data:
            SessionManager._end_session("Your session is no longer valid. Please log in again.")
            return

        # Refresh the profile only after the token has been validated.
        st.session_state.user = user_data
        st.session_state.last_activity = datetime.now()

    @staticmethod
    def _end_session(message):
        """End a session, clear server-side state, and return to sign-in."""
        SessionManager.logout()
        st.error(message)
        st.rerun()

    @staticmethod
    def clear_session_state():
        """Remove authentication data from this server-side Streamlit session."""
        # Also invalidate the opaque browser session, if the refresh-safe
        # companion service is in use. No authentication token is exposed to
        # the browser by this call.
        from auth import persistent_session

        persistent_session.revoke_session()
        for key in list(st.session_state.keys()):
            del st.session_state[key]

    @staticmethod
    def is_authenticated():
        """Check whether this Streamlit session has a validated user."""
        return bool(st.session_state.get("user"))

    @staticmethod
    def create_chat_session():
        """Create a new chat session for the current user."""
        if not SessionManager.is_authenticated():
            return False, "Not authenticated"
        return st.session_state.auth_service.create_session(st.session_state.user["id"])

    @staticmethod
    def get_user_sessions():
        """Get chat sessions belonging to the current user."""
        if not SessionManager.is_authenticated():
            return False, []
        return st.session_state.auth_service.get_user_sessions(st.session_state.user["id"])

    @staticmethod
    def delete_session(session_id):
        """Delete one chat session owned by the current user."""
        if not SessionManager.is_authenticated():
            return False, "Not authenticated"
        return st.session_state.auth_service.delete_session(session_id)

    @staticmethod
    def get_analysis_quota():
        """Get today's persistent analysis allowance for the current user."""
        if not SessionManager.is_authenticated():
            return False, "Not authenticated"
        return st.session_state.auth_service.get_analysis_quota(ANALYSIS_DAILY_LIMIT)

    @staticmethod
    def logout():
        """Sign out remotely and remove all local server-side session state."""
        auth_service = st.session_state.get("auth_service")
        if auth_service:
            auth_service.sign_out()
        SessionManager.clear_session_state()

    @staticmethod
    def login(email, password):
        """Sign in and retain credentials only in the current Streamlit session."""
        if "auth_service" not in st.session_state:
            from auth.auth_service import AuthService

            st.session_state.auth_service = AuthService()

        return st.session_state.auth_service.sign_in(email, password)
