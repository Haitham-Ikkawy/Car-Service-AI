"""OAuth 2.0 sign-in helpers for Google and Apple (Sign in with Apple).

Google uses the standard authorization-code flow (exchange code -> userinfo).
Apple uses the web redirect flow with ``response_mode=form_post``: the callback
POST carries an ``id_token`` which is validated against Apple's JWKS, so only the
Service ID (client id) is required — no private-key token exchange is needed.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from ... import config

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

APPLE_AUTH_URL = "https://appleid.apple.com/auth/authorize"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"


def google_enabled() -> bool:
    return bool(config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET)


def apple_enabled() -> bool:
    return bool(config.APPLE_CLIENT_ID)


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------

def google_authorize_url(state: str) -> str:
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def google_exchange(code: str) -> dict[str, Any]:
    """Exchange the authorization code and return ``{email, name, provider, provider_id, picture}``.

    The ``sub`` claim from Google's userinfo is stored as ``provider_id``
    and the profile ``picture`` URL is returned when available.
    """
    async with httpx.AsyncClient(timeout=20) as client:
        token_res = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "redirect_uri": config.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        token_res.raise_for_status()
        tokens = token_res.json()
        if not tokens.get("access_token"):
            raise ValueError("Google returned no access token")
        info_res = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        info_res.raise_for_status()
        profile = info_res.json()
    email = str(profile.get("email") or "").strip().lower()
    if not email:
        raise ValueError("Google account has no email address")
    name = str(profile.get("name") or "").strip() or email.split("@")[0]
    return {
        "email": email,
        "name": name,
        "provider": "google",
        "provider_id": str(profile.get("sub") or ""),
        "picture": str(profile.get("picture") or ""),
    }


# ---------------------------------------------------------------------------
# Apple (Sign in with Apple)
# ---------------------------------------------------------------------------

def apple_authorize_url(state: str, nonce: str) -> str:
    params = {
        "client_id": config.APPLE_CLIENT_ID,
        "redirect_uri": config.APPLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "name email",
        "response_mode": "form_post",
        "state": state,
        "nonce": nonce,
    }
    return f"{APPLE_AUTH_URL}?{urlencode(params)}"


async def apple_validate_id_token(id_token: str, nonce: str) -> dict[str, Any]:
    """Verify Apple's ``id_token`` signature/claims and return the profile."""
    jwks = jwt.PyJWKClient(APPLE_JWKS_URL, cache_keys=True)
    key = jwks.get_signing_key_from_jwt(id_token).key
    claims = jwt.decode(
        id_token,
        key,
        algorithms=["ES256"],
        audience=config.APPLE_CLIENT_ID,
        issuer=APPLE_ISSUER,
        options={"verify_aud": True, "verify_iss": True, "verify_exp": True},
    )
    if nonce and claims.get("nonce") != nonce:
        raise ValueError("Apple id_token nonce mismatch")
    email = str(claims.get("email") or "").strip().lower()
    if not email:
        raise ValueError("Apple account has no email address")
    return {"email": email, "name": "", "provider": "apple", "sub": claims.get("sub")}
