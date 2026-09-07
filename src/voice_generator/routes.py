"""Voice Generator module routes."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..shared.utils.templating import render, require

router = APIRouter()


@router.get("/voice")
async def voice_generator_page(request: Request):
    require(request)
    return render(request, "voice_generator.html", active="voice",
                  page_title="AI Voice Generator")
