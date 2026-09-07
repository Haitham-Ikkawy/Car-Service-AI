"""Chat AI module routes (streaming conversation + chat management)."""
from __future__ import annotations

import base64
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..shared.store import store
from ..shared.utils import gemini, openai_provider
from ..shared.utils.language import is_arabic, resolve_lang
from ..shared.utils.templating import render, require

router = APIRouter()


def _diagnosis_panel_ctx(user: str, chat: dict | None) -> dict:
    """If this chat was spawned from a diagnosis, return the result panel context
    so the chat view can show the diagnosis alongside the conversation."""
    if not chat:
        return {}
    sess = store.diag_session_by_chat(user, chat.get("id", ""))
    report = (sess or {}).get("diagnosis")
    if not report:
        return {}
    v = (sess or {}).get("vehicle") or {}
    brand = str(v.get("brand", "")).strip()
    model = str(v.get("model", "")).strip()
    label = " ".join(filter(None, [brand, model])).strip() or report.get("vehicle") or "Your vehicle"
    slug = brand.lower().replace(" ", "-").replace("/", "-").replace("_", "-") if brand else ""
    return {"diagnosis": report, "diag_vehicle_label": label, "diag_brand_slug": slug}


@router.get("/chat")
async def chat_page(request: Request):
    user = require(request)
    chat_id = request.query_params.get("chat_id", "")
    chat = store.set_active_chat(user, chat_id) if chat_id else None
    if not chat:
        chat = store.active_chat(user)
    return render(request, "chat.html", active="chat", page_title="AI Chat",
                  chat=chat, chats=store.chats(user),
                  **_diagnosis_panel_ctx(user, chat))


@router.post("/api/chat/stream")
async def chat_stream(request: Request):
    from ..shared.utils import translator as i18n

    user = require(request)
    lang = resolve_lang(request)
    body = await request.json()
    message = (body.get("message") or "").strip()
    chat_id = body.get("chat_id") or ""
    regenerate = bool(body.get("regenerate"))
    provider = (body.get("provider") or "gemini").strip().lower()

    # --- optional image (data-URL from the composer) ---
    image_bytes: bytes | None = None
    image_mime = "image/jpeg"
    image_url = body.get("image_url") or ""
    if image_url and image_url.startswith("data:"):
        try:
            header, encoded = image_url.split(",", 1)
            image_bytes = base64.b64decode(encoded)
            image_mime = header.split(";")[0].split(":")[1] or "image/jpeg"
        except Exception:
            image_bytes = None  # gracefully ignore malformed data

    if not message and not regenerate and not image_bytes:
        return JSONResponse({"error": i18n.tr(lang, "Message is empty")}, status_code=400)

    chat = store.chat(user, chat_id) if chat_id else store.active_chat(user)
    if not chat:
        return JSONResponse({"error": i18n.tr(lang, "Conversation not found")}, status_code=404)
    chat_id = chat["id"]

    if message or image_bytes:
        label = message or "[image]"
        store.append_message(user, chat_id, "user", label)
    if regenerate:
        # remove the previous assistant reply so we can re-answer
        for i in range(len(chat["messages"]) - 1, -1, -1):
            if chat["messages"][i]["role"] == "assistant":
                chat["messages"].pop(i)
                break

    history = store.history_payload(user, chat_id)
    # Reply in the language of the message when it is clearly Arabic/English.
    msg_lang = "ar" if is_arabic(message) else ("en" if message else None)

    # Select the AI provider
    ai_provider = openai_provider if provider == "openai" else gemini

    async def gen():
        full = ""
        failed = False
        try:
            async for chunk in ai_provider.stream_sse(user, history, lang=lang, msg_lang=msg_lang,
                                                      image_bytes=image_bytes, image_mime=image_mime):
                if chunk.startswith("data: [DONE]"):
                    yield chunk
                    return
                try:
                    data = json.loads(chunk[6:].strip())
                except Exception:
                    yield chunk
                    continue
                if data.get("error"):
                    failed = True
                elif data.get("text"):
                    full += data["text"]
                yield chunk
        finally:
            # Persist the completed reply — also when the client aborts ("Stop")
            # mid-stream, so a partial answer is kept. Never store error text.
            if full.strip() and not failed:
                store.append_message(user, chat_id, "assistant", full.strip())

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/api/chat/new")
async def chat_new(request: Request):
    from ..shared.utils import translator as i18n
    user = require(request)
    body = await request.json()
    vehicle = body.get("vehicle")  # optional: {brand, model}
    diag_id = body.get("diag_id")  # optional: link to diagnosis
    chat = store.new_chat(user, vehicle=vehicle, diag_id=diag_id)
    store.append_message(user, chat["id"], "assistant", i18n.chat_greeting(resolve_lang(request)))
    return JSONResponse({"ok": True, "id": chat["id"], "title": chat["title"]})


@router.post("/api/chat/select")
async def chat_select(request: Request):
    user = require(request)
    body = await request.json()
    chat = store.set_active_chat(user, body.get("id", ""))
    if not chat:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"ok": True, "id": chat["id"], "title": chat["title"],
                         "messages": chat["messages"],
                         "vehicle": chat.get("vehicle", {"brand": "", "model": ""}),
                         "diag_id": chat.get("diag_id")})


@router.post("/api/chat/delete")
async def chat_delete(request: Request):
    user = require(request)
    body = await request.json()
    store.delete_chat(user, body.get("id", ""))
    return JSONResponse({"ok": True})


@router.post("/api/chat/clear")
async def chat_clear(request: Request):
    """Clear every message in a conversation (keeps the thread)."""
    user = require(request)
    body = await request.json()
    ok = store.clear_messages(user, body.get("id", ""))
    if not ok:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"ok": True})


@router.get("/api/chat/search")
async def chat_search(request: Request, q: str = ""):
    user = require(request)
    return JSONResponse({"results": store.search_chats(user, q)})


@router.get("/api/chats")
async def chats_list(request: Request):
    user = require(request)
    items = store.chats_meta(user)
    return JSONResponse({"chats": items})


@router.post("/api/chat/rename")
async def chat_rename(request: Request):
    user = require(request)
    body = await request.json()
    chat_id = body.get("id", "")
    title = body.get("title", "")
    chat = store.rename_chat(user, chat_id, title)
    if not chat:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"ok": True, "id": chat["id"], "title": chat["title"]})


@router.post("/api/chat/save-diagnosis")
async def chat_save_diagnosis(request: Request):
    """Save a diagnosis result as a new chat conversation in the history sidebar."""
    user = require(request)
    body = await request.json()
    diag_type = body.get("type", "text")
    problem = body.get("problem", "")
    result = body.get("result", {})
    session_id = body.get("session_id")  # optional: link to diagnosis session
    vehicle = body.get("vehicle")  # optional: {brand, model}

    # Idempotency: if this diagnosis session already has a linked chat, reuse it
    # so the user keeps the SAME conversation context (item 9) whether they
    # continue from the result workspace or later from "My Diagnoses" — instead
    # of spawning a duplicate thread on every call.
    if session_id:
        _sess = store.diag_session(user, session_id)
        existing_id = (_sess or {}).get("chat_id")
        if existing_id:
            existing = store.chat(user, existing_id)
            if existing:
                store.set_active_chat(user, existing_id)
                return JSONResponse({"ok": True, "id": existing_id,
                                     "title": existing.get("title", ""), "reused": True})

    type_labels = {"text": "By Text", "image": "By Image", "audio": "By Audio"}
    type_label = type_labels.get(diag_type, diag_type)

    # Build smart title with vehicle info
    brand = (vehicle or {}).get("brand", "")
    model_name = (vehicle or {}).get("model", "")
    vehicle_str = " ".join(filter(None, [brand, model_name])).strip()
    if vehicle_str:
        title = f"{vehicle_str} — Diagnosis"
    else:
        title = f"Diagnosis ({type_label}): {problem[:40]}{'…' if len(problem) > 40 else ''}"

    chat = store.new_chat(user, vehicle=vehicle)
    # Update the title after creation
    store.rename_chat(user, chat["id"], title)
    store.append_message(user, chat["id"], "user", f"[{type_label}] {problem}")

    summary_parts = []
    if result.get("problem"):
        summary_parts.append(f"**Problem:** {result['problem']}")
    if result.get("urgency"):
        summary_parts.append(f"**Urgency:** {result['urgency']}")
    if result.get("summary"):
        summary_parts.append(f"**Summary:** {result['summary']}")
    if result.get("causes"):
        summary_parts.append("**Causes:**\n" + "\n".join(f"- {c}" for c in result["causes"]))
    if result.get("cost"):
        summary_parts.append(f"**Estimated cost:** {result['cost']}")
    if result.get("time"):
        summary_parts.append(f"**Estimated time:** {result['time']}")
    if result.get("steps"):
        summary_parts.append("**Repair steps:**\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(result["steps"])))
    if result.get("parts"):
        summary_parts.append("**Required parts:** " + ", ".join(result["parts"]))

    assistant_text = "\n\n".join(summary_parts) if summary_parts else "Diagnosis complete."
    store.append_message(user, chat["id"], "assistant", assistant_text)

    # Link chat to diagnosis session if session_id provided
    if session_id:
        store.link_diag_session_chat(user, session_id, chat["id"])

    return JSONResponse({"ok": True, "id": chat["id"], "title": chat["title"]})
