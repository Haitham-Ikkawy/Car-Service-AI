"""AI report module routes."""
from __future__ import annotations

import asyncio
import base64
import logging
import time
import re
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..shared.store import store
from ..shared.utils import gemini, translator as i18n
from ..shared.utils.language import is_arabic, resolve_lang
from ..shared.utils.templating import render, require

router = APIRouter()
log = logging.getLogger("car_ai.diagnosis")


# ---------------------------------------------------------------------------
# Diagnosis Sessions API
# ---------------------------------------------------------------------------

@router.get("/my-diagnoses")
async def my_diagnoses_page(request: Request):
    user = require(request)
    sessions = store.diag_sessions(user)
    return render(request, "my_diagnoses.html", active="my_diagnoses",
                  page_title="My Diagnoses", sessions=sessions)


@router.post("/api/diag-sessions/new")
async def diag_session_new(request: Request):
    """Create a new empty diagnosis session."""
    user = require(request)
    body = await request.json()
    vehicle = body.get("vehicle") or None
    problem = body.get("problem") or ""
    session = store.new_diag_session(user, vehicle=vehicle, problem=problem)
    return JSONResponse({"ok": True, "session": {
        "id": session["id"],
        "title": session["title"],
        "status": session["status"],
    }})


@router.get("/api/diag-sessions")
async def diag_sessions_list(request: Request, q: str = ""):
    """List all diagnosis sessions, optionally filtered by search query."""
    user = require(request)
    if q:
        sessions = store.search_diag_sessions(user, q)
    else:
        sessions = store.diag_sessions(user)
    items = []
    for s in sessions:
        items.append({
            "id": s["id"],
            "title": s["title"],
            "status": s["status"],
            "created_at": s["created_at"],
            "updated_at": s["updated_at"],
            "time_ago": s.get("time_ago", ""),
            "vehicle": s.get("vehicle", {}),
            "problem": s.get("problem", ""),
            "has_diagnosis": s.get("diagnosis") is not None,
            "has_chat": s.get("chat_id") is not None,
        })
    return JSONResponse({"ok": True, "sessions": items})


@router.get("/api/diag-sessions/{session_id}")
async def diag_session_get(request: Request, session_id: str):
    """Get a single diagnosis session with all data."""
    user = require(request)
    session = store.diag_session(user, session_id)
    if not session:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    # Return full session data (image is base64, include it)
    return JSONResponse({"ok": True, "session": {
        "id": session["id"],
        "title": session["title"],
        "status": session["status"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "vehicle": session.get("vehicle", {}),
        "problem": session.get("problem", ""),
        "notice": session.get("notice", ""),
        "category": session.get("category", ""),
        "when": session.get("when", ""),
        "where": session.get("where", ""),
        "answers": session.get("answers", {}),
        "questions": session.get("questions", []),
        "question_index": session.get("question_index", 0),
        "image": session.get("image"),
        "step": session.get("step", "welcome"),
        "diagnosis": session.get("diagnosis"),
        "chat_id": session.get("chat_id"),
    }})


@router.post("/api/diag-sessions/{session_id}/update")
async def diag_session_update(request: Request, session_id: str):
    """Update a diagnosis session (autosave from wizard)."""
    user = require(request)
    body = await request.json()
    session = store.diag_session(user, session_id)
    if not session:
        return JSONResponse({"error": "Session not found"}, status_code=404)

    # Only update fields that are provided
    allowed = {"vehicle", "problem", "notice", "category", "when", "where",
               "answers", "questions", "question_index", "image", "step",
               "status", "title", "diagnosis", "chat_id", "locked", "service_request"}
    updates = {k: v for k, v in body.items() if k in allowed}
    updated = store.update_diag_session(user, session_id, updates)
    return JSONResponse({"ok": True, "title": updated["title"] if updated else session["title"]})


@router.post("/api/diag-sessions/{session_id}/rename")
async def diag_session_rename(request: Request, session_id: str):
    """Rename a diagnosis session."""
    user = require(request)
    body = await request.json()
    title = (body.get("title") or "").strip()
    if not title:
        return JSONResponse({"error": "Title is required"}, status_code=400)
    session = store.rename_diag_session(user, session_id, title)
    if not session:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return JSONResponse({"ok": True, "title": session["title"]})


@router.post("/api/diag-sessions/{session_id}/delete")
async def diag_session_delete(request: Request, session_id: str):
    """Delete a diagnosis session — guarded against active work / service requests."""
    user = require(request)
    lang = resolve_lang(request)
    session = store.diag_session(user, session_id)
    if not session:
        return JSONResponse({"error": i18n.tr(lang, "Session not found")}, status_code=404)
    # Safeguard 1: cannot delete while a diagnosis is actively running.
    if session.get("status") == "diagnosing":
        return JSONResponse(
            {"error": i18n.tr(lang, "This diagnosis is still running — please wait for it to finish before deleting."),
             "code": "in_progress"}, status_code=409)
    # Safeguard 2: cannot delete a diagnosis tied to an active service request.
    if session.get("locked") or (session.get("service_request") or {}).get("active"):
        return JSONResponse(
            {"error": i18n.tr(lang, "This diagnosis is linked to an active service request. Cancel the service request before deleting."),
             "code": "locked"}, status_code=409)
    ok = store.delete_diag_session(user, session_id)
    if not ok:
        return JSONResponse({"error": i18n.tr(lang, "Session not found")}, status_code=404)
    return JSONResponse({"ok": True})


@router.post("/api/diag-sessions/{session_id}/service-request")
async def diag_session_service_request(request: Request, session_id: str):
    """Toggle whether this diagnosis is tied to an active service request.

    An active request locks the session against deletion (item 10 safeguard).
    """
    user = require(request)
    lang = resolve_lang(request)
    body = await request.json()
    active = bool(body.get("active"))
    session = store.diag_session(user, session_id)
    if not session:
        return JSONResponse({"error": i18n.tr(lang, "Session not found")}, status_code=404)
    sr = {"active": True, "requested_at": datetime.now().strftime("%Y-%m-%d %H:%M")} if active else {"active": False}
    store.update_diag_session(user, session_id, {"service_request": sr, "locked": active})
    return JSONResponse({"ok": True, "active": active})


@router.post("/api/diag-sessions/{session_id}/complete")
async def diag_session_complete(request: Request, session_id: str):
    """Mark a diagnosis session as completed with AI results."""
    user = require(request)
    body = await request.json()
    session = store.diag_session(user, session_id)
    if not session:
        return JSONResponse({"error": "Session not found"}, status_code=404)

    # Update diagnosis data and status
    updates = {
        "diagnosis": body.get("diagnosis"),
        "status": "completed",
    }
    store.update_diag_session(user, session_id, updates)
    return JSONResponse({"ok": True})


@router.post("/api/diag-sessions/{session_id}/link-chat")
async def diag_session_link_chat(request: Request, session_id: str):
    """Link a chat thread to a diagnosis session."""
    user = require(request)
    body = await request.json()
    chat_id = body.get("chat_id", "")
    store.link_diag_session_chat(user, session_id, chat_id)
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Guided Diagnosis Wizard
# ---------------------------------------------------------------------------

@router.get("/diagnose")
async def diagnose_wizard(request: Request):
    user = require(request)
    return render(request, "diagnose.html", active="diagnose",
                  page_title="AI Diagnosis", vehicle=store.vehicle(user))


@router.post("/api/diagnose/complete")
async def diagnose_complete(request: Request):
    """Accept the full wizard data and run a single AI diagnosis."""
    _t_backend_recv = time.perf_counter()
    user = require(request)
    lang = resolve_lang(request)
    body = await request.json()

    problem = (body.get("problem") or "").strip()
    answers = body.get("answers") or {}
    image_data = body.get("image") or ""
    vehicle_data = body.get("vehicle") or None

    log.info("[PERF] T3: Backend received request (%.0f ms after gateway)", (_t_backend_recv - _t_backend_recv) * 1000)
    log.info("[DIAGNOSIS] Request received from user=%s", user)
    if vehicle_data:
        log.info("[DIAGNOSIS] Vehicle: %s %s", vehicle_data.get("brand", ""), vehicle_data.get("model", ""))
    log.info("[DIAGNOSIS] Problem: %s", problem[:200])
    if image_data:
        log.info("[DIAGNOSIS] Image payload: ~%d KB", len(image_data) // 1024)

    if len(problem) < 5:
        log.warning("[DIAGNOSIS] Rejected: problem too short (len=%d)", len(problem))
        return JSONResponse(
            {"error": "Please describe the problem in more detail."},
            status_code=400,
        )

    # Build a comprehensive description from the wizard data
    parts = [f"Problem: {problem}"]
    answer_labels = {
        "when": "When it happens",
        "location": "Location of issue",
        "started": "When first noticed",
        "warning_light": "Warning lights",
        "severity": "Severity",
        "noise_type": "Type of noise",
        "temperature": "Temperature behavior",
        "driving_condition": "Driving conditions",
        "recent_work": "Recent repairs or service",
        "fuel_level": "Fuel level",
        "dashboard": "Dashboard indicators",
    }
    for key, value in answers.items():
        if value and value != "Not sure":
            label = answer_labels.get(key, key.replace("_", " ").title())
            parts.append(f"{label}: {value}")

    description = "\n".join(parts)

    # Handle optional image — decode in thread pool to avoid blocking event loop
    image_bytes = None
    image_mime = "image/jpeg"
    if image_data and image_data.startswith("data:"):
        try:
            header, encoded = image_data.split(",", 1)
            image_mime = header.split(";")[0].split(":")[1] or "image/jpeg"
            _t_decode_start = time.perf_counter()
            image_bytes = await asyncio.to_thread(base64.b64decode, encoded)
            _t_decode_end = time.perf_counter()
            log.info("[PERF] Image base64 decode: %.1f ms (%d KB → %d KB)",
                     (_t_decode_end - _t_decode_start) * 1000,
                     len(encoded) // 1024, len(image_bytes) // 1024)
        except Exception:
            image_bytes = None

    mode = "image" if image_bytes else "text"
    log.info("[DIAGNOSIS] Sending request to Gemini (mode=%s)...", mode)
    _t_gemini_start = time.perf_counter()
    log.info("[PERF] T4: Gemini request starts (%.0f ms after backend recv)",
             (_t_gemini_start - _t_backend_recv) * 1000)
    try:
        msg_lang = "ar" if is_arabic(description) else "en"
        result = gemini.diagnose(
            user, mode,
            description=description,
            image_bytes=image_bytes,
            image_mime=image_mime,
            lang=msg_lang,
            vehicle_override=vehicle_data,
            image_data_original=image_data if image_bytes else None,
        )
        _t_gemini_end = time.perf_counter()
        log.info("[PERF] T5: Gemini response received (%.1f ms)", (_t_gemini_end - _t_gemini_start) * 1000)
        log.info("[GEMINI] Response received (problem=%s)", (result.get("problem") or "")[:80])
    except gemini.UnavailableError as exc:
        log.error("[GEMINI] Unavailable: %s", exc.detail or "no detail")
        return JSONResponse(
            {"error": exc.detail or i18n.ai_unavailable(lang), "error_type": "ai_unavailable"},
            status_code=503,
        )
    except Exception as exc:
        log.error("[GEMINI] Unexpected error: %s: %s", type(exc).__name__, exc, exc_info=True)
        return JSONResponse(
            {"error": "Diagnosis service encountered an error. Please try again.",
             "error_type": "ai_error"},
            status_code=500,
        )

    result["date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    saved = store.add_diagnosis(user, result)
    log.info("[DIAGNOSIS] Saved as id=%s", saved.get("id"))

    # Also update the diagnosis session if a session_id was provided
    session_id = body.get("session_id")
    if session_id:
        store.update_diag_session(user, session_id, {
            "diagnosis": saved,
            "status": "completed",
        })
        # Auto-rename the session to a distinct, descriptive name based on the
        # fault the AI actually detected (e.g. "Audi A4 — Worn brake pads").
        store.set_session_title_from_diagnosis(user, session_id, saved)

    _t_response = time.perf_counter()
    log.info("[PERF] T6: Backend sending response (%.0f ms after recv, %.0f ms Gemini)",
             (_t_response - _t_backend_recv) * 1000,
             (_t_gemini_end - _t_gemini_start) * 1000)
    log.info("[PERF] ────────────────────────────────────")
    log.info("[PERF] Backend receive → Gemini start:  %.0f ms", (_t_gemini_start - _t_backend_recv) * 1000)
    log.info("[PERF] Gemini API call:                 %.0f ms", (_t_gemini_end - _t_gemini_start) * 1000)
    log.info("[PERF] Gemini end → Response sent:      %.0f ms", (_t_response - _t_gemini_end) * 1000)
    log.info("[PERF] TOTAL backend:                   %.0f ms", (_t_response - _t_backend_recv) * 1000)
    log.info("[PERF] ────────────────────────────────────")

    return JSONResponse({"ok": True, "result": saved})


# ---------------------------------------------------------------------------
# Legacy diagnosis endpoints (kept for API compatibility)
# ---------------------------------------------------------------------------

@router.get("/diagnose/text")
async def diagnose_text_page(request: Request):
    require(request)
    return RedirectResponse("/diagnose")


@router.post("/api/diagnose/text")
async def diagnose_text_api(request: Request):
    user = require(request)
    lang = resolve_lang(request)
    body = await request.json()
    description = (body.get("description") or "").strip()
    if len(description) < 8:
        return JSONResponse({"error": i18n.tr(lang, "Please describe the problem in at least a few words.")},
                            status_code=400)
    try:
        msg_lang = "ar" if is_arabic(description) else "en"
        result = gemini.diagnose(user, "text", description=description, lang=msg_lang)
    except gemini.UnavailableError as exc:
        return JSONResponse(
            {"error": exc.detail or i18n.ai_unavailable(lang), "error_type": "ai_unavailable"},
            status_code=503,
        )
    result["date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    saved = store.add_diagnosis(user, result)
    return JSONResponse({"ok": True, "result": saved})


@router.get("/diagnosis/{diag_id}")
async def diagnosis_detail(request: Request, diag_id: str):
    user = require(request)
    lang = resolve_lang(request)
    report = store.diagnosis(user, diag_id)
    if not report:
        return render(request, "404.html", active="", page_title=i18n.tr(lang, "Page not found"), status_code=404)
    report["urgency_meta"] = gemini.urgency_meta(report.get("urgency", "low"), lang)
    return render(request, "diagnosis.html", active="", page_title=i18n.tr(lang, "Repair Result"),
                  report=report)


@router.get("/diagnosis/{diag_id}/print")
async def diagnosis_print(request: Request, diag_id: str):
    user = require(request)
    lang = resolve_lang(request)
    report = store.diagnosis(user, diag_id)
    if not report:
        return render(request, "404.html", active="", page_title=i18n.tr(lang, "Page not found"), status_code=404)
    report["urgency_meta"] = gemini.urgency_meta(report.get("urgency", "low"), lang)
    return render(request, "diagnosis_print.html", page_title=i18n.tr(lang, "Repair Result"), report=report)


@router.get("/reports")
async def reports(request: Request):
    user = require(request)
    items = store.diagnoses(user)
    total_cost = _cost_mid(items) if items else 0
    return render(request, "reports.html", active="reports", page_title="Reports",
                  reports=items, total_cost=total_cost)


def _cost_mid(reports):
    total = 0
    for r in reports:
        try:
            nums = re_find_numbers(r.get("cost", ""))
            total += sum(nums) / max(len(nums), 1)
        except Exception:
            continue
    return int(total)


def re_find_numbers(text: str):
    return [float(x) for x in re.findall(r"\$?\s*([\d,]+(?:\.\d+)?)", text) if float(x.replace(",", "")) > 5]
