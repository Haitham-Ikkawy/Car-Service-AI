"""Settings module routes."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import config
from ..shared.store import store
from ..shared.utils import gemini
from ..shared.utils.templating import render, require
from services import gemini_service

router = APIRouter()


@router.get("/settings")
async def settings_page(request: Request):
    require(request)
    return render(request, "settings.html", active="settings", page_title="Settings",
                  gemini_key=gemini.load_api_key(request.session.get("user")),
                  chatgpt_key=config.CHATGPT_API_KEY,
                  gemini_models=config.SUPPORTED_GEMINI_MODELS,
                  default_model=config.DEFAULT_GEMINI_MODEL)


@router.post("/api/settings")
async def settings_save(request: Request):
    user = require(request)
    body = await request.json()
    if "gemini_key" in body:
        config.save_api_key(str(body["gemini_key"]))
    if "chatgpt_key" in body:
        config.save_chatgpt_key(str(body["chatgpt_key"]))
    store.save_settings(user, body)
    # force re-read of key/model on next call
    gemini._MODEL_CACHE.clear()
    return JSONResponse({"ok": True, "demo": gemini.is_demo(user)})


@router.post("/api/settings/test-gemini")
async def settings_test_gemini(request: Request):
    user = require(request)
    body = await request.json()
    key = (body.get("gemini_key") or "").strip() or None
    result = await gemini_service.test_connection(user, key)
    return JSONResponse(result)


@router.post("/api/settings/clear-cache")
async def settings_clear_cache(request: Request):
    """Drop in-memory caches (Gemini model/connection cache)."""
    require(request)
    gemini._MODEL_CACHE.clear()
    return JSONResponse({"ok": True})
