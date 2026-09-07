"""Templating + request helpers shared by every module.

Sets up the Jinja environment over all module ``templates/`` directories and
exposes :func:`render`, :func:`require`, :func:`user` and
:class:`RedirectException` used across the app.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader, pass_context

from ... import __version__, config
from ..store import store
from . import gemini, translator as i18n
from .language import resolve_lang

SRC_DIR = Path(__file__).resolve().parent.parent.parent
SHARED_TEMPLATES = SRC_DIR / "shared" / "templates"


def _template_dirs() -> list[str]:
    """All template roots: shared shell first, then every module templates dir."""
    dirs = [SHARED_TEMPLATES]
    dirs += sorted(p for p in SRC_DIR.glob("*/templates")
                   if p != SHARED_TEMPLATES and "shared" not in p.parts)
    return [str(d) for d in dirs]


TEMPLATE_DIRS = _template_dirs()
templates = Jinja2Templates(directory=TEMPLATE_DIRS[0])
templates.env.loader = ChoiceLoader([FileSystemLoader(d) for d in TEMPLATE_DIRS])

# Jinja helper: {{ t('key') }} translates a string for the current language.
templates.env.globals["t"] = pass_context(
    lambda ctx, key, **kw: i18n.tr(ctx.get("lang", "en"), key, **kw))


class RedirectException(Exception):
    """Raised to short-circuit a route into a 303 redirect."""

    def __init__(self, url: str):
        self.url = url


def user(request: Request) -> str | None:
    """The logged-in user email, or None."""
    return request.session.get("user")


def require(request: Request) -> str:
    """Return the user email or raise a redirect to /login."""
    u = user(request)
    if not u:
        raise RedirectException("/login")
    return u


def render(request: Request, name: str, status_code: int = 200, **ctx) -> HTMLResponse:
    """Render a template with the standard base context for every page."""
    current_user = user(request)
    lang = resolve_lang(request)
    base = {
        "current_user": current_user,
        "settings": store.settings(current_user) if current_user else {},
        "vehicle": store.vehicle(current_user),
        "is_demo": gemini.is_demo(current_user),
        "lang": lang,
        "dir": "rtl" if lang == "ar" else "ltr",
        "js_i18n": i18n.js_bundle(lang),
        "languages": config.SUPPORTED_LANGUAGES,
        "years": config.VEHICLE_YEARS,
        "fuel_types": config.FUEL_TYPES,
        "transmissions": config.TRANSMISSIONS,
        "manufacturers": config.MANUFACTURERS,
        "app_version": __version__,
        "page_title": i18n.tr(lang, ctx.pop("page_title", "Car Service AI")),
        "active": ctx.pop("active", ""),
    }
    base.update(ctx)
    return templates.TemplateResponse(request, name, base, status_code=status_code)
