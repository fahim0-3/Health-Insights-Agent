import streamlit as st
from supabase import create_client
from datetime import datetime
import time
import re
from utils.app_logging import get_logger, log_exception
from auth import persistent_session


logger = get_logger(__name__)


class AuthService:
    def __init__(self):
        try:
            # Initialize Supabase client directly
            # This ensures a fresh client for each session, preventing state leakage
            self.supabase = create_client(
                st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
            )
        except Exception as error:
            log_exception(logger, "supabase_initialization_failed", error, component="auth")
            st.error("The sign-in service is temporarily unavailable. Please try again later.")
            raise RuntimeError("Supabase configuration could not be initialized.") from None

        # Restore only credentials held in the current server-side Streamlit
        # session. Browser local storage is intentionally never used.
        self.try_restore_session()

        # Validate session on initialization
        if "auth_token" in st.session_state:
            user_data = self.validate_session_token()
            if user_data:
                st.session_state.user = user_data
            else:
                # Don't sign out immediately on failure during init to avoid loop
                pass

    def try_restore_session(self):
        """Restore a Supabase client from this Streamlit session, if available."""
        access_token = st.session_state.get("auth_token")
        refresh_token = st.session_state.get("refresh_token")
        if not access_token or not refresh_token:
            # On a browser refresh, Streamlit starts a new connection and its
            # in-memory state is empty. The companion service can recover the
            # credentials server-to-server from an opaque HttpOnly cookie.
            restored = persistent_session.restore_session()
            if restored:
                access_token = restored["access_token"]
                refresh_token = restored["refresh_token"]
                st.session_state.auth_token = access_token
                st.session_state.refresh_token = refresh_token
        if not access_token or not refresh_token:
            return False

        try:
            self.supabase.auth.set_session(access_token, refresh_token)
            return True
        except Exception:
            # A stale token is rejected later by validate_session_token(), which
            # clears the complete server-side session and returns to sign-in.
            return False

    def validate_email(self, email):
        """Validate email format."""
        pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        return bool(re.match(pattern, email))

    def check_existing_user(self, email):
        """Check if user already exists."""
        try:
            result = (
                self.supabase.table("users").select("id").eq("email", email).execute()
            )
            return len(result.data) > 0
        except Exception:
            return False

    def sign_up(self, email, password, name):
        try:
            auth_response = self.supabase.auth.sign_up(
                {
                    "email": email,
                    "password": password,
                    "options": {"data": {"name": name}},
                }
            )

            if not auth_response.user:
                return False, "Failed to create user account"

            # public.users is created by the on_auth_user_created database trigger.
            # The client never inserts a profile row, so it cannot choose another
            # user's ID or bypass the database's ownership rules.
            user_data = {
                "id": auth_response.user.id,
                "email": email,
                "name": name,
            }

            # If we got a session immediately (email confirmation off), store it
            if auth_response.session:
                self.supabase.auth.set_session(
                    auth_response.session.access_token,
                    auth_response.session.refresh_token,
                )
                st.session_state.auth_token = auth_response.session.access_token
                st.session_state.refresh_token = auth_response.session.refresh_token
                persistent_session.update_tokens(
                    auth_response.session.access_token,
                    auth_response.session.refresh_token,
                )
                profile = self.get_user_data(auth_response.user.id)
                st.session_state.user = profile or user_data

            return True, st.session_state.get("user", user_data)

        except Exception as error:
            error_msg = str(error).lower()
            if "duplicate" in error_msg or "already registered" in error_msg:
                return False, "Email already registered"
            log_exception(logger, "sign_up_failed", error, component="auth", operation="sign_up")
            return False, "Unable to create the account. Please check your details and try again."

    def sign_in(self, email, password):
        try:
            # Clear any existing session data first
            # But don't call sign_out() which destroys auth_service in session_state
            # Just clear the supabase client session locally
            try:
                self.supabase.auth.sign_out()
            except Exception:
                pass

            auth_response = self.supabase.auth.sign_in_with_password(
                {"email": email, "password": password}
            )

            if auth_response and auth_response.user:
                self.supabase.auth.set_session(
                    auth_response.session.access_token,
                    auth_response.session.refresh_token,
                )
                # Get user data
                user_data = self.get_user_data(auth_response.user.id)
                if not user_data:
                    return False, "User data not found"

                # Store session info
                st.session_state.auth_token = auth_response.session.access_token
                st.session_state.refresh_token = auth_response.session.refresh_token
                persistent_session.update_tokens(
                    auth_response.session.access_token,
                    auth_response.session.refresh_token,
                )
                st.session_state.user = user_data
                return True, user_data

            return False, "Invalid login response"
        except Exception as error:
            log_exception(logger, "sign_in_failed", error, component="auth", operation="sign_in")
            return False, "Unable to sign in. Check your email and password, then try again."

    def sign_out(self):
        """End the remote Supabase session.

        SessionManager owns clearing Streamlit state so this method is safe to
        call during timeout and logout handling without recursive cleanup.
        """
        try:
            self.supabase.auth.sign_out()
        except Exception:
            pass
        return True, None

    def get_user(self):
        try:
            return self.supabase.auth.get_user()
        except Exception:
            return None

    def create_session(self, user_id, title=None):
        try:
            current_time = datetime.now()
            default_title = f"{current_time.strftime('%d-%m-%Y')} | {current_time.strftime('%H:%M:%S')}"

            session_data = {
                "user_id": user_id,
                "title": title or default_title,
                "created_at": current_time.isoformat(),
            }
            result = self.supabase.table("chat_sessions").insert(session_data).execute()
            return True, result.data[0] if result.data else None
        except Exception as error:
            log_exception(logger, "chat_session_creation_failed", error, component="auth")
            return False, "Could not create a chat session. Please try again."

    def update_session_title(self, session_id, title):
        """Rename a session the signed-in user owns."""
        try:
            result = (
                self.supabase.table("chat_sessions")
                .update({"title": title})
                .eq("id", session_id)
                .execute()
            )
            return True, result.data[0] if result.data else None
        except Exception as error:
            log_exception(logger, "chat_session_title_update_failed", error, component="auth")
            return False, "Could not rename the report session."

    def get_user_sessions(self, user_id):
        try:
            result = (
                self.supabase.table("chat_sessions")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )
            return True, result.data
        except Exception as error:
            log_exception(logger, "chat_sessions_fetch_failed", error, component="auth")
            return False, []

    def save_chat_message(self, session_id, content, role="user"):
        try:
            message_data = {
                "session_id": session_id,
                "content": content,
                "role": role,
                "created_at": datetime.now().isoformat(),
            }
            result = self.supabase.table("chat_messages").insert(message_data).execute()
            return True, result.data[0] if result.data else None
        except Exception as error:
            log_exception(logger, "chat_message_save_failed", error, component="auth")
            return False, "Could not save the message. Please try again."

    def get_session_messages(self, session_id):
        try:
            result = (
                self.supabase.table("chat_messages")
                .select("*")
                .eq("session_id", session_id)
                .order("created_at")
                .execute()
            )
            return True, result.data
        except Exception as error:
            log_exception(logger, "chat_messages_fetch_failed", error, component="auth")
            return False, "Could not load messages. Please try again."

    def get_analysis_quota(self, daily_limit):
        """Read the server-enforced daily analysis allowance for this user."""
        try:
            response = self.supabase.rpc(
                "get_analysis_quota", {"limit_value": daily_limit}
            ).execute()
            return True, response.data[0]
        except Exception:
            return False, "Could not load the daily analysis limit."

    def reserve_analysis_quota(self, daily_limit):
        """Atomically reserve one analysis slot before model generation."""
        try:
            response = self.supabase.rpc(
                "reserve_analysis_quota", {"limit_value": daily_limit}
            ).execute()
            quota = response.data[0]
            if quota["allowed"]:
                return True, quota
            return False, quota
        except Exception:
            return False, "Could not verify the daily analysis limit."

    def release_analysis_quota(self):
        """Return a reserved slot if model generation did not succeed."""
        try:
            self.supabase.rpc("release_analysis_quota").execute()
            return True, None
        except Exception:
            # The analysis did not complete, but retaining a slot is safer than
            # allowing a failed quota update to bypass the daily limit.
            return False, "Could not return the reserved analysis slot."

    def delete_session(self, session_id):
        try:
            self.supabase.table("chat_messages").delete().eq(
                "session_id", session_id
            ).execute()

            self.supabase.table("chat_sessions").delete().eq("id", session_id).execute()

            return True, None
        except Exception as error:
            log_exception(logger, "chat_session_deletion_failed", error, component="auth")
            return False, "Could not delete the session. Please try again."

    def validate_session_token(self):
        """Validate existing session token on startup."""
        try:
            session = self.supabase.auth.get_session()
            if not session or not session.access_token:
                # If no session in Supabase client, but we have tokens in state, try to set session again
                if (
                    "auth_token" in st.session_state
                    and "refresh_token" in st.session_state
                ):
                    try:
                        self.supabase.auth.set_session(
                            st.session_state.auth_token, st.session_state.refresh_token
                        )
                        session = self.supabase.auth.get_session()
                    except Exception:
                        pass

            if not session or not session.access_token:
                return None

            # Relaxed validation: If we have a valid Supabase session, update our state instead of failing
            # This handles token refreshes or slight mismatches
            if session.access_token != st.session_state.get("auth_token"):
                st.session_state.auth_token = session.access_token
                if session.refresh_token:
                    st.session_state.refresh_token = session.refresh_token

            persistent_session.update_tokens(
                session.access_token,
                session.refresh_token or st.session_state.get("refresh_token", ""),
            )

            user = self.supabase.auth.get_user()
            if not user or not user.user:
                return None

            return self.get_user_data(user.user.id)
        except Exception:
            return None

    def get_user_data(self, user_id):
        """Get user data from database."""
        try:
            response = (
                self.supabase.table("users")
                .select("*")
                .eq("id", user_id)
                .single()
                .execute()
            )
            return response.data if response else None
        except Exception:
            return None
