"""Language helpers for Car Service AI.

Contains the supported-language registry, Arabic detection and the request-level
language resolver (session > saved user setting > browser ``Accept-Language``).
"""
from __future__ import annotations

import re

from fastapi import Request

from ..store import store

# Supported UI languages (settings picker + top-bar switcher).
SUPPORTED = {"en": "English"}

_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")


def is_arabic(text: str | None) -> bool:
    """True when the text contains Arabic characters."""
    return bool(_ARABIC_RE.search(text or ""))


def detect_lang(accept_header: str | None) -> str:
    """Pick a language from an Accept-Language header (falls back to en)."""
    h = (accept_header or "").lower()
    if re.search(r"(^|[;,])ar([-,;]|$)", h):
        return "ar"
    return "en"


def resolve_lang(request: Request) -> str:
    """Resolve the effective UI language for the request.

    Always returns English.
    """
    return "en"
