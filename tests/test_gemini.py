"""Gemini helper logic: key sanitising, key precedence, friendly errors."""
from __future__ import annotations

from src.shared.utils import gemini


def test_clean_key_strips_whitespace_and_quotes():
    assert gemini._clean_key('  "AIzaABC123"  ') == "AIzaABC123"
    assert gemini._clean_key("'key'") == "key"
    assert gemini._clean_key(None) == ""
    assert gemini._clean_key("AIzaPlain") == "AIzaPlain"


def test_settings_key_overrides_env(monkeypatch):
    """A per-user Settings key must take priority over a (bad) .env key."""
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaFromEnv")
    monkeypatch.setattr(gemini.store, "settings",
                        lambda user: {"gemini_key": "AIzaFromSettings"})
    assert gemini._api_key("u@x.com") == "AIzaFromSettings"


def test_env_key_used_when_no_settings_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaFromEnv")
    monkeypatch.setattr(gemini.store, "settings", lambda user: {"gemini_key": ""})
    assert gemini._api_key("u@x.com") == "AIzaFromEnv"


class _FakeExc(Exception):
    pass


def test_friendly_error_for_auth_failure():
    msg = gemini._friendly_error(_FakeExc(
        "401 UNAUTHENTICATED: Request had invalid authentication credentials"))
    assert "API key" in msg and "Settings" in msg


def test_friendly_error_for_access_token_type():
    msg = gemini._friendly_error(_FakeExc("ACCESS_TOKEN_TYPE_UNSUPPORTED"))
    assert "API key" in msg


def test_friendly_error_passes_through_unknown():
    assert gemini._friendly_error(_FakeExc("some novel error")) == "some novel error"
