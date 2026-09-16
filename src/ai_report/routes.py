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
from ..shared.utils.gemini import ask_gemini, UnavailableError, _extract_json
from ..shared.utils.language import is_arabic, resolve_lang
from ..shared.utils.templating import render, require

router = APIRouter()
log = logging.getLogger("car_ai.diagnosis")


# ---------------------------------------------------------------------------
# Diagnosis Sessions API
# ---------------------------------------------------------------------------

@router.get("/my-diagnoses")
async def my_diagnoses_page(request: Request, page: int = 1, q: str = ""):
    """Per-user diagnosis history, paginated (limit/offset) and searchable server-side."""
    user = require(request)
    q = (q or "").strip()
    all_sessions = store.search_diag_sessions(user, q) if q else store.diag_sessions(user)
    per_page = 9
    total = len(all_sessions)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    sessions = all_sessions[start:start + per_page]
    return render(request, "my_diagnoses.html", active="my_diagnoses",
                  page_title="My Diagnoses", sessions=sessions,
                  page=page, total_pages=total_pages, total=total,
                  per_page=per_page, q=q)


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
    # Return full session data (image and video are base64, include them)
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
        "video": session.get("video"),
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
               "answers", "questions", "question_index", "image", "video", "step",
               "status", "title", "diagnosis", "chat_id", "locked", "service_request",
               "questions_from_server"}
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
    # NOTE: the former "cannot delete while diagnosing" 409 guard was removed. A
    # diagnosis runs synchronously within its request, so a persisted "diagnosing"
    # status only ever means a *failed/abandoned* run — which then became
    # undeletable (the reported "Delete does nothing" bug). Users must always be
    # able to delete their own diagnosis. The service-request lock below remains.
    # Safeguard: cannot delete a diagnosis tied to an active service request.
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
    video_data = body.get("video") or ""
    vehicle_data = body.get("vehicle") or None

    log.info("[PERF] T3: Backend received request (%.0f ms after gateway)", (_t_backend_recv - _t_backend_recv) * 1000)
    log.info("[DIAGNOSIS] Request received from user=%s", user)
    if vehicle_data:
        log.info("[DIAGNOSIS] Vehicle: %s %s", vehicle_data.get("brand", ""), vehicle_data.get("model", ""))
    log.info("[DIAGNOSIS] Problem: %s", problem[:200])
    if image_data:
        log.info("[DIAGNOSIS] Image payload: ~%d KB", len(image_data) // 1024)
    if video_data:
        log.info("[DIAGNOSIS] Video payload: ~%d KB", len(video_data) // 1024)

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

    # Handle optional video — decode in thread pool to avoid blocking event loop
    video_bytes = None
    video_mime = "video/mp4"
    if video_data and video_data.startswith("data:"):
        try:
            header, encoded = video_data.split(",", 1)
            video_mime = header.split(";")[0].split(":")[1] or "video/mp4"
            _t_video_decode_start = time.perf_counter()
            video_bytes = await asyncio.to_thread(base64.b64decode, encoded)
            _t_video_decode_end = time.perf_counter()
            log.info("[PERF] Video base64 decode: %.1f ms (%d KB → %d KB)",
                     (_t_video_decode_end - _t_video_decode_start) * 1000,
                     len(encoded) // 1024, len(video_bytes) // 1024)
        except Exception:
            video_bytes = None

    # Determine mode: video takes priority over image
    mode = "video" if video_bytes else ("image" if image_bytes else "text")
    log.info("[DIAGNOSIS] Sending request to Gemini (mode=%s)...", mode)
    _t_gemini_start = time.perf_counter()
    log.info("[PERF] T4: Gemini request starts (%.0f ms after backend recv)",
             (_t_gemini_start - _t_backend_recv) * 1000)
    try:
        msg_lang = "ar" if is_arabic(description) else "en"
        # Detect dialect for Arabic users
        dialect = ""
        dialect_confidence = 0.0
        user_terms = {}
        if msg_lang == "ar":
            from ..shared.utils.arabic_dialect import detect_language_and_dialect
            dialect_result = detect_language_and_dialect(problem)
            dialect = dialect_result.dialect
            dialect_confidence = dialect_result.dialect_confidence
            user_terms = {c["id"]: c["local"] for c in dialect_result.canonical_concepts}
            log.info("[DIALECT] Detected: %s (confidence: %.2f)", dialect, dialect_confidence)

        # Run the BLOCKING Gemini call off the event loop. Called directly it froze
        # the single event loop for the whole diagnosis (10-30s), which is why chat
        # streaming "stopped working" during/after a diagnosis (item 2).
        result = await asyncio.to_thread(
            gemini.diagnose,
            user, mode,
            description=description,
            image_bytes=image_bytes,
            image_mime=image_mime,
            video_bytes=video_bytes,
            video_mime=video_mime,
            lang=msg_lang,
            vehicle_override=vehicle_data,
            image_data_original=image_data if image_bytes else None,
            dialect=dialect,
            dialect_confidence=dialect_confidence,
            user_terms=user_terms,
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
# Dialect Detection & Dialect-Aware Questions
# ---------------------------------------------------------------------------

from ..shared.utils.arabic_dialect import detect_language_and_dialect, find_automotive_terms


@router.post("/api/diagnose/detect-dialect")
async def detect_dialect_api(request: Request):
    """Detect Arabic dialect from user input text."""
    user = require(request)
    body = await request.json()
    text = (body.get("text") or "").strip()

    if not text:
        return JSONResponse({"ok": True, "language": "en", "dialect": "", "dialect_confidence": 0.0})

    result = detect_language_and_dialect(text)

    return JSONResponse({
        "ok": True,
        "language": result.language,
        "dialect": result.dialect,
        "dialect_confidence": result.dialect_confidence,
        "detected_terms": result.detected_terms,
        "canonical_concepts": result.canonical_concepts,
    })


@router.post("/api/diagnose/questions")
async def generate_questions_api(request: Request):
    """Generate dialect-aware diagnostic questions using Gemini.

    Supports two modes:
    - mode="initial": Generate the first batch of 2-3 questions (called once when problem is submitted)
    - mode="followup": Generate the next single question based on previous Q&A (called after each answer)

    The follow-up mode enables truly dynamic, conversation-like diagnostic flows
    where each question depends on the user's previous answers.
    """
    user = require(request)
    body = await request.json()

    problem = (body.get("problem") or "").strip()
    vehicle = body.get("vehicle") or {}
    dialect = body.get("dialect") or "Arabic"
    dialect_confidence = body.get("dialect_confidence") or 0.0
    detected_terms = body.get("detected_terms") or []
    canonical_concepts = body.get("canonical_concepts") or []
    answers = body.get("answers") or {}
    category = body.get("category") or ""
    when = body.get("when") or ""
    where = body.get("where") or ""
    mode = body.get("mode") or "initial"
    previous_questions = body.get("previous_questions") or []

    if len(problem) < 3:
        return JSONResponse({"error": "Problem description too short"}, status_code=400)

    # Build the question generation prompt
    vehicle_label = ""
    if vehicle:
        parts = [vehicle.get("year"), vehicle.get("brand"), vehicle.get("model")]
        vehicle_label = " ".join(str(p) for p in parts if p)
        if vehicle.get("engine"):
            vehicle_label += f" · {vehicle['engine']}"

    # Build user vocabulary context
    vocab_context = ""
    if detected_terms:
        vocab_context = f"\nUser's automotive vocabulary: {', '.join(detected_terms)}"
    if canonical_concepts:
        concepts_str = ", ".join([f"{c.get('local', '')} → {c.get('en', '')}" for c in canonical_concepts])
        vocab_context += f"\nCanonical mappings: {concepts_str}"

    # Build answers context (all previous answers)
    answers_context = ""
    if answers:
        for key, value in answers.items():
            if value and value != "Not sure":
                answers_context += f"\n- {key}: {value}"

    # Build previous questions context
    prev_q_context = ""
    if previous_questions:
        prev_q_context = "\nPREVIOUS QUESTIONS AND ANSWERS:"
        for pq in previous_questions:
            q_title = pq.get("title", "")
            q_answer = pq.get("answer", "")
            prev_q_context += f"\n- Question: {q_title}"
            if q_answer:
                prev_q_context += f"\n  Answer: {q_answer}"

    if mode == "followup":
        # Generate a single follow-up question based on all context
        prompt = f"""You are a senior automotive diagnostic expert helping a car owner diagnose their vehicle problem.

VEHICLE: {vehicle_label or 'Not specified'}
PROBLEM: {problem}
CATEGORY: {category or 'General'}
WHEN: {when or 'Not specified'}
WHERE: {where or 'Not specified'}
{vocab_context}
{answers_context}
{prev_q_context}

LANGUAGE/DIALECT CONTEXT:
- Detected dialect: {dialect}
- Dialect confidence: {dialect_confidence:.0%}
- You MUST generate the NEXT question in the SAME dialect as the user.
- Use the user's natural automotive terminology when possible.
- Do NOT use Modern Standard Arabic unless dialect confidence is very low.
- Do NOT mechanically translate from English.
- Preserve technical diagnostic meaning while adapting to the dialect.

TASK:
Generate exactly ONE follow-up diagnostic question that would be most useful RIGHT NOW based on the information gathered so far.

RULES:
1. The question must be in natural {dialect} Arabic (or neutral Arabic if confidence is low).
2. Use the user's automotive terms when available (e.g., if user says "السكان", use "السكان" not "عجلة القيادة").
3. Do NOT repeat any question already asked (check PREVIOUS QUESTIONS AND ANSWERS).
4. Focus on the MOST IMPORTANT missing diagnostic information.
5. The question should be short, natural, and conversational.
6. Generate 3-5 answer options that are natural in {dialect} Arabic.
7. Include "Not sure" as the last option if appropriate.
8. Each question must advance the diagnosis — no filler questions.

Return a JSON object (NOT an array) with EXACTLY these keys:
{{
  "key": "unique_diagnostic_key",
  "title": "The question in {dialect} Arabic",
  "subtitle": "Brief explanation if needed (in {dialect} Arabic), or empty string",
  "options": ["Option 1 in {dialect} Arabic", "Option 2", "Option 3", "Not sure"]
}}

Return ONLY the JSON object, no markdown, no commentary."""
    else:
        # Initial mode: generate 2-3 questions
        prompt = f"""You are a senior automotive diagnostic expert helping a car owner diagnose their vehicle problem.

VEHICLE: {vehicle_label or 'Not specified'}
PROBLEM: {problem}
CATEGORY: {category or 'General'}
WHEN: {when or 'Not specified'}
WHERE: {where or 'Not specified'}
{vocab_context}
{answers_context}

LANGUAGE/DIALECT CONTEXT:
- Detected dialect: {dialect}
- Dialect confidence: {dialect_confidence:.0%}
- The user writes in Arabic. You MUST generate questions in the SAME dialect.
- Use the user's natural automotive terminology when possible.
- Do NOT use Modern Standard Arabic unless the dialect confidence is very low.
- Do NOT mechanically translate from English.
- Preserve technical diagnostic meaning while adapting to the dialect.

TASK:
Generate 2-3 initial diagnostic questions to start understanding the vehicle problem.

RULES:
1. Questions must be in natural {dialect} Arabic (or neutral Arabic if confidence is low).
2. Use the user's automotive terms when available (e.g., if user says "السكان", use "السكان" not "عجلة القيادة").
3. Each question should target a specific diagnostic need.
4. Questions should be short, natural, and conversational.
5. Include the question key (for programmatic use).
6. Focus on the most important missing information.
7. Generate 3-5 answer options per question that are natural in {dialect} Arabic.

Return a JSON array of question objects:
[
  {{
    "key": "unique_key",
    "title": "Question in {dialect} Arabic",
    "subtitle": "Brief explanation if needed (in {dialect} Arabic)",
    "options": ["Option 1", "Option 2", "Option 3", "Not sure"]
  }}
]

Return ONLY the JSON array, no markdown, no commentary."""

    try:
        # Use existing Gemini architecture
        result = await asyncio.to_thread(
            gemini._generate_question,
            user,
            prompt,
        )
        if mode == "followup":
            # result should be a single dict; wrap in list if needed
            if isinstance(result, list) and len(result) > 0:
                result = result[0]
            elif not isinstance(result, dict):
                result = None
            return JSONResponse({"ok": True, "question": result})
        else:
            return JSONResponse({"ok": True, "questions": result})
    except gemini.UnavailableError as exc:
        return JSONResponse(
            {"error": exc.detail or "AI unavailable", "error_type": "ai_unavailable"},
            status_code=503,
        )
    except Exception as exc:
        log.error("[QUESTIONS] Error generating questions: %s", exc, exc_info=True)
        return JSONResponse(
            {"error": "Failed to generate questions", "error_type": "ai_error"},
            status_code=500,
        )


# ---------------------------------------------------------------------------
# Text Parsing — Vehicle + Fault extraction from natural language
# ---------------------------------------------------------------------------

@router.post("/api/diagnose/parse-text")
async def parse_text_api(request: Request):
    """Parse natural language text to extract vehicle info or fault description.

    Used by voice input and chat-based vehicle/fault selection. Accepts Arabic
    or English text and returns structured data via Gemini.
    """
    user = require(request)
    body = await request.json()
    text = (body.get("text") or "").strip()
    parse_type = body.get("type") or "vehicle"  # "vehicle" or "fault"

    if not text or len(text) < 3:
        return JSONResponse({"ok": True, "parsed": None})

    # Detect dialect for context
    dialect = ""
    dialect_confidence = 0.0
    user_terms = {}
    if is_arabic(text):
        dialect_result = detect_language_and_dialect(text)
        dialect = dialect_result.dialect
        dialect_confidence = dialect_result.dialect_confidence
        user_terms = {c["id"]: c["local"] for c in dialect_result.canonical_concepts}

    if parse_type == "vehicle":
        prompt = f"""Extract vehicle information from this text. Return a JSON object with these fields:
{{
  "brand": "vehicle manufacturer/brand name in English (e.g. Toyota, BMW, Ford)",
  "model": "model name in English (e.g. Camry, Corolla, Civic)",
  "year": "model year as a 4-digit number (e.g. 2020) or null if not mentioned",
  "engine": "engine specification if mentioned (e.g. 2.0L, V6) or empty string"
}}

IMPORTANT RULES:
- Translate Arabic brand/model names to English (e.g. "تويوتا" → "Toyota", "كامري" → "Camry")
- Common Arabic→English mappings: تويوتا→Toyota, هوندا→Honda, نيسان→Nissan, كيا→Kia, هيونداي→Hyundai, فورد→Ford, بي ام دبليو→BMW, مرسيدس→Mercedes-Benz, لاند روفر→Land Rover, توسون→Tucson,لاند كروزر→Land Cruiser
- If the user says only a brand, return brand with null model
- If no year mentioned, return null for year
- Return ONLY the JSON object, no commentary

User text: {text}"""
    else:
        prompt = f"""Extract fault/problem information from this text. Return a JSON object with these fields:
{{
  "problem": "concise problem description in English (e.g. Engine overheating, Brake noise, Car won't start)",
  "symptoms": ["list", "of", "specific symptoms mentioned"],
  "location": "where the issue is felt (e.g. front, rear, engine bay, cabin) or empty string",
  "when": "when the issue occurs (e.g. always, when braking, at startup) or empty string"
}}

IMPORTANT RULES:
- Translate Arabic automotive terms to English
- Common Arabic→English mappings: فرامل→brakes, محرّك→engine, تكييف→AC, بطارية→battery, حرارة→temperature, صوت→sound, اهتزاز→vibration, دخان→smoke, تسريب→leak
- Keep the problem description concise (under 60 chars)
- If no specific symptoms mentioned, return an empty array
- Return ONLY the JSON object, no commentary

User text: {text}"""

    try:
        raw = await asyncio.to_thread(ask_gemini, prompt, user)
        parsed = _extract_json(raw)
        if not parsed:
            return JSONResponse({"ok": True, "parsed": None})
        return JSONResponse({
            "ok": True,
            "parsed": parsed,
            "dialect": dialect,
            "dialect_confidence": dialect_confidence,
        })
    except UnavailableError as exc:
        return JSONResponse(
            {"error": exc.detail or "AI unavailable", "error_type": "ai_unavailable"},
            status_code=503,
        )
    except Exception as exc:
        log.error("[PARSE-TEXT] Error: %s", exc, exc_info=True)
        return JSONResponse({"ok": True, "parsed": None})


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
