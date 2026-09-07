"""My Garage + Repair Guide routes."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..shared.store import store
from ..shared.utils import translator as i18n
from ..shared.utils.language import resolve_lang
from ..shared.utils.templating import render, require
from . import guides, twin, vehicle_api

logger = logging.getLogger(__name__)
router = APIRouter()


def _lang(request: Request) -> str:
    return resolve_lang(request)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@router.get("/repair-guide")
async def repair_guide_page(request: Request):
    require(request)
    return render(request, "repair_guide.html", active="repair-guide",
                  page_title="Repair Guide", categories=guides.CATEGORIES, guides=guides.GUIDES)


@router.get("/repair-guide/{slug}")
async def repair_guide_detail(request: Request, slug: str):
    user = require(request)
    guide = guides.guide(slug)
    lang = _lang(request)
    if not guide:
        return JSONResponse({"error": i18n.tr(lang, "Guide not found.")}, status_code=404)
    return render(request, "repair_guide_detail.html", active="repair-guide",
                  page_title=guide["title"], guide=guide, related=guides.related(slug))


# ---------------------------------------------------------------------------
# Vehicle APIs
# ---------------------------------------------------------------------------

# ---- Cascading autocomplete: brand -> model -> engine (live NHTSA/CarQuery) ----

@router.get("/api/vehicles/makes")
async def vehicles_makes(request: Request, q: str = "", limit: int = 12):
    require(request)
    # Cap generously so "View all brands" can list the full make catalogue.
    limit = max(1, min(limit, 600))
    return JSONResponse({"items": await vehicle_api.makes(q, limit=limit)})


@router.get("/api/vehicles/models")
async def vehicles_models(request: Request, make: str = "", q: str = ""):
    require(request)
    return JSONResponse({"items": await vehicle_api.models(make, q)})


@router.get("/api/vehicles/engines")
async def vehicles_engines(request: Request, make: str = "", model: str = "", q: str = ""):
    require(request)
    return JSONResponse({"items": await vehicle_api.engines(make, model, q)})


# TODO: re-enable VIN lookup — temporarily disabled (future work). The frontend
# entry point is also gated off (VIN_LOOKUP_ENABLED = false in diagnose.js) and
# vehicle_api.decode_vin() is kept intact. Un-comment the route below to restore.
# @router.get("/api/vehicles/vin")
# async def vehicles_vin(request: Request, vin: str = ""):
#     """Decode a VIN into structured vehicle fields (NHTSA vPIC)."""
#     require(request)
#     return JSONResponse(await vehicle_api.decode_vin(vin))


@router.get("/api/vehicles/image")
async def vehicles_image(request: Request, make: str = "", model: str = "", year: str = ""):
    """Redirect to a realistic PHOTO of the given vehicle.

    Resolves a real photo (Wikipedia → shipped image → optional licensed render);
    blueprint/schematic (SVG) images are excluded. The client uses this as an
    ``<img src>`` and falls back to an icon via ``onerror`` if nothing is found.
    """
    from fastapi.responses import RedirectResponse, Response
    require(request)
    url = await vehicle_api.photo_url(make, model, year)
    if not url:
        return Response(status_code=404)
    # Wikimedia/Wikipedia images are safe to hotlink from an <img>. Cache at the
    # edge/browser since model photos are effectively static.
    return RedirectResponse(url, headers={"Cache-Control": "public, max-age=86400"})


@router.post("/api/vehicle")
async def vehicle_save(request: Request):
    user = require(request)
    lang = _lang(request)
    body = await request.json()
    manufacturer = str(body.get("manufacturer") or "").strip()
    model = str(body.get("model") or "").strip()
    year = body.get("year")
    fuel = str(body.get("fuel") or "").strip()
    transmission = str(body.get("transmission") or "").strip()
    mileage = body.get("mileage")
    chassis = str(body.get("chassis") or "").strip()

    if not manufacturer or not model:
        return JSONResponse({"error": i18n.tr(lang, "Manufacturer and model are required.")}, status_code=400)

    def _to_int(value: Any) -> int | None:
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else None

    year_i = _to_int(year)
    mile_i = _to_int(mileage)
    data: dict[str, Any] = {"manufacturer": manufacturer, "model": model}
    if year_i:
        data["year"] = year_i
    if fuel:
        data["fuel"] = fuel
    if transmission:
        data["transmission"] = transmission
    if mile_i is not None:
        data["mileage"] = mile_i
    if chassis:
        data["chassis"] = chassis[:24]

    store.set_vehicle(user, data)
    return JSONResponse({"ok": True, "vehicle": store.vehicle(user)})


@router.post("/api/vehicle/detect")
async def vehicle_detect(request: Request):
    user = require(request)
    body = await request.json()
    text = str(body.get("text") or "").strip()
    return JSONResponse(twin.detect_vehicle(text, user))


@router.post("/api/vehicle/twin")
async def vehicle_twin(request: Request):
    user = require(request)
    lang = _lang(request)
    if not store.vehicle(user):
        return JSONResponse({"error": i18n.tr(lang, "Save your vehicle first.")}, status_code=400)
    return JSONResponse(twin.analyze_twin(user))


@router.get("/api/vehicle/parts/{key}")
async def vehicle_part(request: Request, key: str):
    user = require(request)
    vehicle = store.vehicle(user) or {}
    parts = [vehicle.get("year"), vehicle.get("manufacturer"), vehicle.get("model")]
    label = " ".join(str(p) for p in parts if p) or "this vehicle"
    return JSONResponse(twin.part_report(user, key, label))
