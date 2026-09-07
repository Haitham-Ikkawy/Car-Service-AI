"""Social sign-in routes — Google OAuth and Sign in with Apple."""
from __future__ import annotations

import json
import logging
import secrets
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ..shared.store import store
from ..shared.utils import oauth
from .. import config
from ..shared.utils.language import resolve_lang
from ..shared.utils.templating import RedirectException
from ..shared.utils.translator import tr

logger = logging.getLogger(__name__)
router = APIRouter()


def _lang(request: Request) -> str:
    return resolve_lang(request)


def _fail(request: Request, key: str) -> RedirectException:
    return RedirectException(f"/login?error={quote(tr(_lang(request), key))}")


def _finish(request: Request, email: str, name: str, lang: str, *,
            provider: str = "", provider_id: str = "",
            picture: str = "") -> RedirectResponse:
    """Create/fetch the user, seed demo data and open a session (same as /login)."""
    from ..app import _seed  # lazy import to avoid an import cycle

    profile = store.login(
        email, name or email.split("@")[0],
        provider=provider, provider_id=provider_id, picture=picture,
    )
    request.session["user"] = email
    request.session["name"] = profile["name"]
    request.session["lang"] = lang
    store.set_lang(email, lang)
    _seed(email, lang)
    return RedirectResponse("/diagnose", status_code=303)


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------

@router.get("/auth/google")
async def google_start(request: Request):
    if request.session.get("user"):
        raise RedirectException("/diagnose")
    if not oauth.google_enabled():
        missing = []
        if not config.GOOGLE_CLIENT_ID:
            missing.append("GOOGLE_CLIENT_ID")
        if not config.GOOGLE_CLIENT_SECRET:
            missing.append("GOOGLE_CLIENT_SECRET")
        if missing:
            detail = f"{', '.join(missing)} is not set."
        else:
            detail = "Credentials are empty."
        raise _fail(
            request,
            f"Google Sign-In is not configured. {detail} "
            "Add your credentials to the project .env file — see .env.example.",
        )
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    return RedirectResponse(oauth.google_authorize_url(state), status_code=303)


@router.get("/auth/google/callback")
async def google_callback(request: Request, code: str = "", state: str = "",
                          error: str = ""):
    if error:
        raise _fail(request, "Sign in with Google failed. Please try again.")
    expected = request.session.pop("oauth_state", None)
    if not expected or state != expected:
        raise _fail(request, "Sign-in session expired. Please try again.")
    lang = _lang(request)
    try:
        info = await oauth.google_exchange(code)
    except Exception as exc:  # noqa: BLE001 — surface a friendly error
        logger.warning("Google sign-in failed: %s", exc)
        raise _fail(request, "Sign in with Google failed. Please try again.")
    if not info.get("email"):
        raise _fail(request, "Sign in with Google failed. Please try again.")
    return _finish(
        request, info["email"], info.get("name", ""), lang,
        provider=info.get("provider", "google"),
        provider_id=info.get("provider_id", ""),
        picture=info.get("picture", ""),
    )


# ---------------------------------------------------------------------------
# Apple (Sign in with Apple)
# ---------------------------------------------------------------------------

@router.get("/auth/apple")
async def apple_start(request: Request):
    if request.session.get("user"):
        raise RedirectException("/diagnose")
    if not oauth.apple_enabled():
        raise _fail(request, "Sign in with Apple is not configured yet.")
    state = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    request.session["oauth_nonce"] = nonce
    return RedirectResponse(oauth.apple_authorize_url(state, nonce), status_code=303)


@router.post("/auth/apple/callback")
async def apple_callback(request: Request, code: str = Form(""), id_token: str = Form(""),
                         state: str = Form(""), user: str = Form(""), error: str = Form("")):
    if error:
        raise _fail(request, "Sign in with Apple failed. Please try again.")
    expected = request.session.pop("oauth_state", None)
    nonce = request.session.pop("oauth_nonce", None)
    if not expected or state != expected:
        raise _fail(request, "Sign-in session expired. Please try again.")
    lang = _lang(request)
    try:
        info = await oauth.apple_validate_id_token(id_token, nonce or "")
    except Exception as exc:  # noqa: BLE001 — surface a friendly error
        logger.warning("Apple sign-in failed: %s", exc)
        raise _fail(request, "Sign in with Apple failed. Please try again.")
    name = _apple_name(user)
    return _finish(
        request, info["email"], name, lang,
        provider=info.get("provider", "apple"),
        provider_id=info.get("sub", ""),
    )


def _apple_name(raw: str) -> str:
    """Apple sends the user's name as a JSON string — only on first sign-in."""
    if not raw:
        return ""
    try:
        data = json.loads(raw)
        n = data.get("name") or {}
        return " ".join(part for part in (n.get("firstName"), n.get("lastName")) if part).strip()
    except (TypeError, ValueError):
        return ""
