"""Dashboard module — redirects to the Guided AI Diagnosis page."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ..shared.utils.templating import require

router = APIRouter()


@router.get("/dashboard")
async def dashboard(request: Request):
    require(request)
    return RedirectResponse(url="/diagnose", status_code=303)
