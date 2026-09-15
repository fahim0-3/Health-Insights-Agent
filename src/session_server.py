"""Local companion service for refresh-safe Streamlit authentication.

It sets an opaque HttpOnly cookie. Supabase tokens remain only in this process.
For production, place this service behind HTTPS on the same public domain.
"""

import hmac
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
import tomllib

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from supabase import create_client

from utils.app_logging import get_logger, log_exception
from utils.validators import validate_signup_fields


logger = get_logger(__name__)
COOKIE_NAME = "health_insights_session"
SESSION_LIFETIME_MINUTES = 30


@dataclass
class SessionRecord:
    access_token: str
    refresh_token: str
    expires_at: datetime


class TokenUpdate(BaseModel):
    access_token: str
    refresh_token: str


class ServerSessions:
    def __init__(self):
        self._records = {}
        self._lock = threading.Lock()

    def create(self, access_token, refresh_token):
        session_id = secrets.token_urlsafe(32)
        with self._lock:
            self._remove_expired()
            self._records[session_id] = SessionRecord(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=datetime.now(timezone.utc)
                + timedelta(minutes=SESSION_LIFETIME_MINUTES),
            )
        return session_id

    def get(self, session_id):
        with self._lock:
            self._remove_expired()
            return self._records.get(session_id)

    def update(self, session_id, access_token, refresh_token):
        with self._lock:
            record = self._records.get(session_id)
            if not record or record.expires_at <= datetime.now(timezone.utc):
                self._records.pop(session_id, None)
                return False
            record.access_token = access_token
            record.refresh_token = refresh_token
            record.expires_at = datetime.now(timezone.utc) + timedelta(
                minutes=SESSION_LIFETIME_MINUTES
            )
            return True

    def delete(self, session_id):
        with self._lock:
            return self._records.pop(session_id, None)

    def _remove_expired(self):
        now = datetime.now(timezone.utc)
        expired = [key for key, record in self._records.items() if record.expires_at <= now]
        for key in expired:
            self._records.pop(key, None)


def load_settings():
    secrets_path = Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml"
    with secrets_path.open("rb") as file:
        settings = tomllib.load(file)
    required = ("SUPABASE_URL", "SUPABASE_KEY", "APP_SESSION_INTERNAL_KEY")
    missing = [key for key in required if not settings.get(key)]
    if missing:
        raise RuntimeError("Session service configuration is incomplete.")
    return settings


settings = load_settings()
sessions = ServerSessions()
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def configured_return_url(value):
    expected = settings.get("APP_BASE_URL", "http://localhost:8502")
    return expected if value != expected else value


def cookie_secure():
    return bool(settings.get("SESSION_COOKIE_SECURE", False))


def require_internal_request(request):
    supplied = request.headers.get("X-Session-Internal-Key", "")
    expected = settings["APP_SESSION_INTERNAL_KEY"]
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="Forbidden")


def login_page(mode, return_to, message=""):
    action = "/login" if mode == "login" else "/signup"
    alternative = "signup" if mode == "login" else "login"
    alternative_text = "Create an account" if mode == "login" else "Sign in"
    notice = f'<div class="notice">{escape(message)}</div>' if message else ""
    signup_fields = "" if mode == "login" else """
        <label for="name">Full name</label>
        <input id="name" name="name" autocomplete="name" required>
    """
    confirmation_field = "" if mode == "login" else """
        <label for="confirm_password">Confirm password</label>
        <input id="confirm_password" name="confirm_password" type="password" autocomplete="new-password" required>
        <p class="help">Use at least 8 characters, including uppercase, lowercase, and a number.</p>
    """
    password_autocomplete = "current-password" if mode == "login" else "new-password"
    return HTMLResponse(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Health Insights Agent · {'Sign in' if mode == 'login' else 'Create account'}</title>
        <style>
            :root {{ color-scheme: dark; }}
            * {{ box-sizing:border-box; }}
            body {{ margin:0; min-height:100vh; display:grid; place-items:center; padding:2rem 1rem;
                font-family:"Source Sans Pro",ui-sans-serif,system-ui,sans-serif; color:#f4f7ff;
                background:radial-gradient(circle at 12% 8%,#19355b 0,transparent 34rem),#0e1117; }}
            .shell {{ width:min(100%,460px); }}
            .brand {{ text-align:center; margin-bottom:1.5rem; }}
            .brand-mark {{ display:inline-grid; place-items:center; width:3.25rem; height:3.25rem;
                border-radius:1rem; background:linear-gradient(135deg,#64b5f6,#1976d2); font-size:1.7rem;
                box-shadow:0 12px 30px #0007; }}
            h1 {{ margin:.8rem 0 .2rem; font-size:2rem; letter-spacing:-.04em; }}
            .tagline {{ margin:0; color:#aab9cf; }}
            .card {{ background:#262730; border:1px solid #3b4150; border-radius:1rem; padding:1.7rem;
                box-shadow:0 24px 60px #0007; }}
            h2 {{ margin:0 0 .35rem; font-size:1.45rem; }}
            .subtitle,.help {{ color:#aab9cf; font-size:.92rem; line-height:1.45; }}
            .subtitle {{ margin:0 0 1.25rem; }} .help {{ margin:-.45rem 0 1rem; }}
            label {{ display:block; margin:1rem 0 .4rem; font-size:.93rem; font-weight:600; color:#dce5f5; }}
            input {{ width:100%; border:1px solid #596274; border-radius:.5rem; background:#171a21;
                color:#f4f7ff; padding:.75rem .8rem; font:inherit; }}
            input:focus {{ outline:2px solid #64b5f6; outline-offset:1px; border-color:#64b5f6; }}
            button {{ width:100%; margin-top:1.3rem; border:0; border-radius:.5rem; padding:.78rem 1rem;
                background:#1976d2; color:#fff; font:600 1rem inherit; cursor:pointer; }}
            button:hover {{ background:#2185df; }}
            .switch {{ margin:1.25rem 0 0; text-align:center; color:#aab9cf; }}
            a {{ color:#64b5f6; }} .notice {{ margin:0 0 1rem; padding:.75rem .85rem; border-radius:.5rem;
                background:#452b32; border:1px solid #9d4d59; color:#ffd9de; }}
            .privacy {{ margin:1rem 0 0; text-align:center; color:#8591a5; font-size:.78rem; }}
        </style></head>
        <body><main class="shell"><section class="brand"><div class="brand-mark">🩺</div>
        <h1>Health Insights Agent</h1><p class="tagline">Discover a healthier you with AI</p></section>
        <section class="card"><h2>{'Welcome back' if mode == 'login' else 'Create your account'}</h2>
        <p class="subtitle">{'Sign in to continue your health-report conversations.' if mode == 'login' else 'Create an account to keep your report sessions private.'}</p>{notice}
        <form method="post" action="{action}"><input type="hidden" name="return_to" value="{escape(return_to)}">
        {signup_fields}<label for="email">Email</label><input id="email" name="email" type="email" autocomplete="email" required>
        <label for="password">Password</label><input id="password" name="password" type="password" autocomplete="{password_autocomplete}" required>
        {confirmation_field}
        <button type="submit">{'Create account' if mode == 'signup' else 'Sign in'}</button></form>
        <p class="switch">{'Already have an account?' if mode == 'signup' else "Don't have an account?"} <a href="/{alternative}?return_to={escape(return_to)}">{alternative_text}</a></p></section>
        <p class="privacy">Your sign-in is protected with a secure browser session.</p></main></body></html>""",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/login", response_class=HTMLResponse)
def login_form(return_to: str = ""):
    return login_page("login", configured_return_url(return_to))


@app.post("/login", response_class=HTMLResponse)
def login(email: str = Form(...), password: str = Form(...), return_to: str = Form("")):
    target = configured_return_url(return_to)
    try:
        client = create_client(settings["SUPABASE_URL"], settings["SUPABASE_KEY"])
        response = client.auth.sign_in_with_password({"email": email, "password": password})
        if not response.session:
            return login_page("login", target, "Unable to sign in. Check your email and password.")
        session_id = sessions.create(response.session.access_token, response.session.refresh_token)
        redirect = RedirectResponse(target, status_code=303)
        redirect.set_cookie(
            COOKIE_NAME,
            session_id,
            max_age=SESSION_LIFETIME_MINUTES * 60,
            httponly=True,
            secure=cookie_secure(),
            samesite="lax",
            path="/",
        )
        return redirect
    except Exception as error:
        log_exception(logger, "persistent_login_failed", error, component="session_server")
        return login_page("login", target, "Unable to sign in. Please try again.")


@app.get("/signup", response_class=HTMLResponse)
def signup_form(return_to: str = ""):
    return login_page("signup", configured_return_url(return_to))


@app.post("/signup", response_class=HTMLResponse)
def signup(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    return_to: str = Form(""),
):
    target = configured_return_url(return_to)
    is_valid, validation_error = validate_signup_fields(
        name, email, password, confirm_password
    )
    if not is_valid:
        return login_page("signup", target, validation_error)
    try:
        client = create_client(settings["SUPABASE_URL"], settings["SUPABASE_KEY"])
        response = client.auth.sign_up({"email": email, "password": password, "options": {"data": {"name": name}}})
        if not response.session:
            return login_page("login", target, "Account created. Confirm your email, then sign in.")
        session_id = sessions.create(response.session.access_token, response.session.refresh_token)
        redirect = RedirectResponse(target, status_code=303)
        redirect.set_cookie(COOKIE_NAME, session_id, max_age=SESSION_LIFETIME_MINUTES * 60, httponly=True, secure=cookie_secure(), samesite="lax", path="/")
        return redirect
    except Exception as error:
        log_exception(logger, "persistent_signup_failed", error, component="session_server")
        return login_page("signup", target, "Unable to create the account. Please try again.")


@app.post("/internal/session")
def read_session(request: Request):
    require_internal_request(request)
    record = sessions.get(request.cookies.get(COOKIE_NAME, ""))
    if not record:
        raise HTTPException(status_code=401, detail="Session unavailable")
    return {"access_token": record.access_token, "refresh_token": record.refresh_token}


@app.post("/internal/update")
def update_session(request: Request, token_update: TokenUpdate):
    require_internal_request(request)
    if not sessions.update(request.cookies.get(COOKIE_NAME, ""), token_update.access_token, token_update.refresh_token):
        raise HTTPException(status_code=401, detail="Session unavailable")
    return {"status": "updated"}


@app.post("/internal/revoke")
def revoke_session(request: Request):
    require_internal_request(request)
    sessions.delete(request.cookies.get(COOKIE_NAME, ""))
    return {"status": "revoked"}


@app.get("/logout")
def logout(request: Request, return_to: str = ""):
    target = configured_return_url(return_to)
    sessions.delete(request.cookies.get(COOKIE_NAME, ""))
    redirect = RedirectResponse(target, status_code=303)
    redirect.delete_cookie(COOKIE_NAME, path="/")
    return redirect
