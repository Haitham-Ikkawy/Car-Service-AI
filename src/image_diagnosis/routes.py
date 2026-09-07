"""Image diagnosis module routes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse

from ..shared.store import store
from ..shared.utils import gemini, translator as i18n
from ..shared.utils.image_ai import validate_image
from ..shared.utils.language import is_arabic, resolve_lang
from ..shared.utils.templating import render, require

router = APIRouter()


@router.get("/diagnose/image")
async def diagnose_image_page(request: Request):
    require(request)
    return RedirectResponse("/diagnose")


@router.post("/api/diagnose/image")
async def diagnose_image_api(request: Request, file: UploadFile, description: str = Form("")):
    user = require(request)
    lang = resolve_lang(request)
    content = await file.read()
    mime = file.content_type or gemini.guess_mime(file.filename or "")
    error = validate_image(file, content, mime, lang)
    if error:
        return JSONResponse({"error": error}, status_code=400)
    try:
        msg_lang = "ar" if is_arabic(description) else "en"
        result = gemini.diagnose(user, "image", description=description.strip(),
                                 image_bytes=content, image_mime=mime, lang=msg_lang)
    except gemini.UnavailableError as exc:
        return JSONResponse(
            {"error": exc.detail or i18n.ai_unavailable(lang), "error_type": "ai_unavailable"},
            status_code=503,
        )
    result["date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    saved = store.add_diagnosis(user, result)
    return JSONResponse({"ok": True, "result": saved})
