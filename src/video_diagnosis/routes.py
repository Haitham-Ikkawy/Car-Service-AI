"""Video diagnosis module routes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from ..shared.store import store
from ..shared.utils import gemini, translator as i18n
from ..shared.utils.language import is_arabic, resolve_lang
from ..shared.utils.templating import render, require
from ..shared.utils.video import validate_video

router = APIRouter()


@router.get("/diagnose/video")
async def diagnose_video_page(request: Request):
    require(request)
    return render(request, "diagnose_video.html", active="video",
                  page_title="Diagnose by Video")


@router.post("/api/diagnose/video")
async def diagnose_video_api(request: Request, file: UploadFile, description: str = Form("")):
    user = require(request)
    lang = resolve_lang(request)
    content = await file.read()
    mime = file.content_type or gemini.guess_mime(file.filename or "")
    error = validate_video(file, content, mime, lang)
    if error:
        return JSONResponse({"error": error}, status_code=400)
    try:
        msg_lang = "ar" if is_arabic(description) else "en"
        result = gemini.diagnose(user, "video", description=description.strip(),
                                 video_bytes=content, video_mime=mime, lang=msg_lang)
    except gemini.UnavailableError as exc:
        return JSONResponse(
            {"error": exc.detail or i18n.ai_unavailable(lang), "error_type": "ai_unavailable"},
            status_code=503,
        )
    result["date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    saved = store.add_diagnosis(user, result)
    return JSONResponse({"ok": True, "result": saved})
