"""Maintenance module routes."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

from ..shared.store import store
from ..shared.utils import translator as i18n
from ..shared.utils.language import resolve_lang
from ..shared.utils.templating import render, require

router = APIRouter()


def _with_progress(items: list[dict], vehicle_km: int) -> list[dict]:
    for m in items:
        last = m.get("last_done_km") or 0
        interval = m.get("interval_km") or 0
        current = m.get("current_km") or vehicle_km or 0
        m["due_in_km"] = max(last + interval - current, 0)
        m["progress"] = min(100, int(max(0, current - last) / max(1, interval) * 100))
        m["next_service_km"] = last + interval
        m["remaining_km"] = last + interval - current
        m["service_status"] = "overdue" if m["remaining_km"] <= 0 else (
            "due_soon" if m["remaining_km"] <= 1000 else "upcoming")
    return items


@router.get("/maintenance")
async def maintenance_page(request: Request):
    user = require(request)
    items = store.maintenance(user)
    vehicle_km = (store.vehicle(user) or {}).get("mileage", 0)
    _with_progress(items, vehicle_km)
    active = [m for m in items if m.get("status") != "done"]
    done = [m for m in items if m.get("status") == "done"]
    return render(request, "maintenance.html", active="maintenance", page_title="Maintenance",
                  items=active, done=done, vehicle_km=vehicle_km)


@router.post("/api/maintenance")
async def maintenance_add(request: Request, title: str = Form(""), category: str = Form(""),
                          interval_km: int = Form(0), last_done_km: int = Form(0),
                          current_km: int = Form(0), notes: str = Form("")):
    user = require(request)
    lang = resolve_lang(request)
    if not title.strip():
        return JSONResponse({"error": i18n.tr(lang, "Title is required.")}, status_code=400)
    item = store.add_maintenance(user, {
        "title": title.strip(), "category": category or "General",
        "interval_km": max(interval_km, 1), "last_done_km": max(last_done_km, 0),
        "current_km": max(current_km, 0), "notes": notes.strip(),
    })
    return JSONResponse({"ok": True, "id": item["id"]})


@router.post("/api/maintenance/{mid}/done")
async def maintenance_done(request: Request, mid: str):
    user = require(request)
    item = store.update_maintenance(user, mid, {"status": "done"})
    return JSONResponse({"ok": bool(item)})


@router.post("/api/maintenance/{mid}/delete")
async def maintenance_delete(request: Request, mid: str):
    user = require(request)
    return JSONResponse({"ok": store.delete_maintenance(user, mid)})


@router.get("/api/maintenance/data")
async def maintenance_data(request: Request):
    user = require(request)
    items = store.maintenance(user)
    vehicle_km = (store.vehicle(user) or {}).get("mileage", 0)
    _with_progress(items, vehicle_km)
    return JSONResponse({
        "active": [m for m in items if m.get("status") != "done"],
        "done": [m for m in items if m.get("status") == "done"],
    })
