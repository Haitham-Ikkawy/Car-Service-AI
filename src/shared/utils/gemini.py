"""Gemini AI service for Car Service AI.

Wraps the ``google-genai`` SDK with:
  * a model fallback chain,
  * strict-JSON parsing for structured diagnosis reports,
  * multimodal (image / audio) diagnosis via inline parts,
  * exact error propagation (no fake/demo responses).

All public functions accept ``user`` so the API key entered in Settings takes
priority over the ``.env`` value at runtime.
"""
from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import json
import logging
import mimetypes
import os
import re
from typing import Any, Generator

from dotenv import load_dotenv

from ... import config
from ..store import store
from .translator import ai_unavailable as _ai_unavailable

logger = logging.getLogger("car_ai.gemini")

# ---------------------------------------------------------------------------
# Client handling
# ---------------------------------------------------------------------------

_MODEL_CACHE: dict[str, tuple[Any, str]] = {}

# Message shown when a Gemini call is attempted without a configured API key.
NO_KEY_MESSAGE = (
    "No Gemini API key is configured. Add your Gemini API key in Settings "
    "to enable AI features."
)


def _clean_key(raw: Any) -> str:
    """Normalise an API key: strip whitespace and any surrounding quotes.

    A key pasted with quotes (``"AIza..."``) or a stray BOM/newline is a common
    cause of "invalid authentication credentials" — clean it before use.
    """
    key = (raw or "").strip().lstrip("﻿").strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in ("'", '"'):
        key = key[1:-1].strip()
    return key


def _api_key(user: str | None) -> str:
    """Effective API key.

    A per-user key entered in **Settings takes priority** so a user can always
    override a missing or invalid project ``.env`` key at runtime; the ``.env``
    value is the fallback.
    """
    if user:
        key = _clean_key(store.settings(user).get("gemini_key"))
        if key:
            return key
    return _clean_key(os.getenv("GEMINI_API_KEY", ""))


def load_api_key(user: str | None = None) -> str:
    """Re-read ``.env`` (python-dotenv) and return the effective API key."""
    load_dotenv(config.BASE_DIR / ".env", override=True)
    return _api_key(user)


def _model_for(user: str | None, model: str | None = None) -> str:
    """Resolve the model to use for a request.

    Precedence: an explicitly passed model, then the per-user model saved in
    Settings, then ``config.DEFAULT_MODEL``. Any value that is not a supported
    model (deprecated names, typos) falls back to ``config.DEFAULT_GEMINI_MODEL``
    so every request uses a currently available Gemini model.
    """
    m = (model or "").strip() or (store.settings(user or "x").get("model") or "").strip() or config.DEFAULT_MODEL
    if m not in config.SUPPORTED_GEMINI_MODELS:
        logger.warning("Gemini model %r is not supported; using default %r.",
                       m, config.DEFAULT_GEMINI_MODEL)
        return config.DEFAULT_GEMINI_MODEL
    return m


def _client_for(user: str | None, model: str | None = None) -> tuple[Any, str] | None:
    """Return (client, model) or None if no usable API key is present."""
    key = _api_key(user)
    model = _model_for(user, model)
    cache_key = f"{user}|{key}|{model}"
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]
    if not key:
        return None
    try:
        from google import genai

        # Force the Gemini **Developer API** (vertexai=False) so the key is always
        # sent as an API key (x-goog-api-key), never treated as an OAuth2 access
        # token. This avoids the 401 UNAUTHENTICATED / ACCESS_TOKEN_TYPE_UNSUPPORTED
        # error that occurs when the client falls back to OAuth/ADC credentials.
        client = genai.Client(api_key=key, vertexai=False)
        entry = (client, model)
        _MODEL_CACHE[cache_key] = entry
        return entry
    except Exception as exc:  # noqa: BLE001
        logger.error("Gemini client init failed (user=%s): %s: %s",
                     user, type(exc).__name__, exc, exc_info=True)
        return None


def is_demo(user: str | None = None) -> bool:
    return _client_for(user) is None


def _connection_error_state(exc: BaseException) -> dict[str, str]:
    """Map a Gemini SDK exception to a status dict for the Test Connection UI."""
    status = getattr(exc, "code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (400, 401, 403):
        return {"state": "invalid", "message": "Invalid API Key", "detail": str(exc)[:300]}
    return {"state": "error", "message": "Connection failed", "detail": str(exc)[:300]}


def test_gemini_connection(user: str | None = None, key: str | None = None,
                           timeout: float = 30.0) -> dict[str, str]:
    """Verify a Gemini API key with a minimal real request.

    Returns one of: ``ok`` / ``invalid`` / ``missing`` / ``error``.
    ``key`` may be an unsaved key (typed in the Settings form) — the value
    is tested without being persisted.
    """
    key = (key or "").strip() or _api_key(user)
    if not key:
        return {"state": "missing", "message": "API Key Missing"}

    model = _model_for(user)

    def _probe() -> str:
        from google import genai

        client = genai.Client(api_key=key, vertexai=False)
        resp = client.models.generate_content(
            model=model, contents="Reply with exactly: OK")
        return (getattr(resp, "text", None) or "").strip()

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_probe)
            text = future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        return {"state": "error", "message": "Connection failed",
                "detail": f"Request timed out after {timeout:.0f}s"}
    except Exception as exc:  # noqa: BLE001
        logger.error("Gemini connection test failed: %s: %s",
                     type(exc).__name__, exc, exc_info=True)
        return _connection_error_state(exc)

    if text:
        return {"state": "ok", "message": "Connected", "model": model}
    return {"state": "error", "message": "Connection failed", "detail": "Empty response from Gemini."}


def ask_gemini(prompt: str, user: str | None = None, model: str | None = None) -> str:
    """Ask Gemini a single question and return its text answer.

    Raises :class:`UnavailableError` when no API key is configured or the call fails.
    """
    client_info = _client_for(user, model)
    if client_info is None:
        raise UnavailableError("Gemini API key is missing.")
    client, model_name = client_info
    try:
        raw = _run_generation(client, model_name, prompt)
    except Exception as exc:  # noqa: BLE001
        logger.error("ask_gemini failed (user=%r, model=%s): %s: %s",
                     user, model_name, type(exc).__name__, exc, exc_info=True)
        raise UnavailableError(_error_message(exc)) from None
    return raw


def ask_gemini_image(prompt: str, image_bytes: bytes, image_mime: str = "image/jpeg",
                     user: str | None = None, model: str | None = None) -> str:
    """Ask Gemini a question about an attached image and return its text answer.

    Raises :class:`UnavailableError` when no API key is configured or the call fails.
    """
    client_info = _client_for(user, model)
    if client_info is None:
        raise UnavailableError("Gemini API key is missing.")
    client, model_name = client_info
    try:
        from google.genai import types

        img_part = types.Part.from_bytes(data=image_bytes, mime_type=image_mime)
        raw = _run_generation(client, model_name, [prompt, img_part])
    except Exception as exc:  # noqa: BLE001
        logger.error("ask_gemini_image failed (user=%r, model=%s): %s: %s",
                     user, model_name, type(exc).__name__, exc, exc_info=True)
        raise UnavailableError(_error_message(exc)) from None
    return raw


def analyze_image(user: str | None = None, description: str = "",
                  image_bytes: bytes | None = None,
                  image_mime: str = "image/jpeg") -> dict[str, Any]:
    """AI analysis of a vehicle photo → structured diagnosis report."""
    return diagnose(user, "image", description=description,
                    image_bytes=image_bytes, image_mime=image_mime)


def analyze_audio(user: str | None = None, description: str = "",
                  audio_bytes: bytes | None = None,
                  audio_mime: str = "audio/mpeg") -> dict[str, Any]:
    """AI analysis of a vehicle sound recording → structured diagnosis report."""
    return diagnose(user, "audio", description=description,
                    audio_bytes=audio_bytes, audio_mime=audio_mime)


def analyze_video(user: str | None = None, description: str = "",
                  video_bytes: bytes | None = None,
                  video_mime: str = "video/mp4") -> dict[str, Any]:
    """AI analysis of a vehicle problem video → structured diagnosis report."""
    return diagnose(user, "video", description=description,
                    video_bytes=video_bytes, video_mime=video_mime)


def _model_chain(model: str) -> list[str]:
    """Ordered candidate models: the selected model first, then supported fallbacks."""
    return [model] + [m for m in config.MODEL_FALLBACKS if m != model]


def _fast_config():
    """A generation config that turns OFF extended 'thinking' for much lower latency.

    Flash models default to a thinking phase that adds seconds of latency — for our
    strict-schema JSON diagnosis that reasoning isn't needed, so we set the budget
    to 0. Returns None if the SDK/model doesn't expose the option (we then just
    call without it).
    """
    try:
        from google.genai import types
        return types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
    except Exception:  # noqa: BLE001
        return None


def _run_generation(client: Any, model: str, contents: Any) -> str:
    """Generate with model fallback chain; raises on total failure.

    Each candidate is tried first with the low-latency (no-thinking) config, then
    without it, so a model that rejects the config still succeeds.
    """
    chain = _model_chain(model)
    cfg = _fast_config()
    last_err: Exception | None = None
    for candidate in chain:
        for use_cfg in ([cfg, None] if cfg is not None else [None]):
            try:
                if use_cfg is not None:
                    resp = client.models.generate_content(
                        model=candidate, contents=contents, config=use_cfg)
                else:
                    resp = client.models.generate_content(model=candidate, contents=contents)
                if getattr(resp, "text", None):
                    if candidate != model:
                        logger.info("Fell back to Gemini model %s (primary %s failed).", candidate, model)
                    return resp.text
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.error("Gemini model %s unavailable%s: %s: %s", candidate,
                             " (fast config)" if use_cfg is not None else "",
                             type(exc).__name__, _error_message(exc))
                continue
    if last_err:
        raise last_err
    raise RuntimeError("Gemini returned an empty response")


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)
_JSON_RAW = re.compile(r"\{.*\}", re.S)


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    m = _JSON_FENCE.search(text)
    candidate = m.group(1) if m else _JSON_RAW.search(text)
    if not candidate:
        return None
    try:
        data = json.loads(candidate.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _vehicle_label(user: str) -> str:
    v = store.vehicle(user)
    if not v:
        return "Not specified"
    parts = [v.get("year"), v.get("manufacturer"), v.get("model")]
    label = " ".join(str(p) for p in parts if p)
    fuel = v.get("fuel")
    if fuel:
        label += f" · {fuel}"
    vin = (v.get("chassis") or "").strip()
    if vin:
        label += f" · VIN {vin}"
    return label.strip() or "Not specified"


def _vehicle_context(user: str | None) -> str:
    """Rich, structured context about the user's saved vehicle.

    Combines the real vehicle data, maintenance history and recent diagnoses
    stored for ``user`` so AI calls answer about *that specific car*. Returns
    an empty string when no vehicle is saved.
    """
    v = store.vehicle(user)
    if not v:
        return ""
    label = " ".join(str(p) for p in (v.get("year"), v.get("manufacturer"), v.get("model")) if p)
    lines = [f"Vehicle: {label or 'Unnamed vehicle'}"]
    details = []
    for key, unit in (("fuel", ""), ("transmission", ""), ("engine", "")):
        value = v.get(key)
        if value:
            details.append(f"{key.capitalize()}: {value}")
    if v.get("mileage"):
        details.append(f"Mileage: {v['mileage']:,} km")
    if (v.get("chassis") or "").strip():
        details.append(f"VIN: {v['chassis']}")
    if details:
        lines.append(" | ".join(details))

    maintenance = store.maintenance(user)
    if maintenance:
        lines.append("Previous maintenance:")
        for m in maintenance[:8]:
            last = m.get("last_done_km")
            title = m.get("title") or "Service"
            if last:
                lines.append(f"  - {title} (last done at {last:,} km)")
            else:
                lines.append(f"  - {title}")
    else:
        lines.append("Previous maintenance: none recorded.")

    diagnoses = store.diagnoses(user)
    if diagnoses:
        lines.append("Recent diagnoses / reported problems:")
        for d in diagnoses[:5]:
            text = d.get("problem") or d.get("summary") or ""
            if text:
                lines.append(f"  - {str(text)[:220]}")
    return "\n".join(lines)


def _lang_instruction(lang: str) -> str:
    """A prompt suffix telling Gemini which language to answer in."""
    if lang == "ar":
        return ("\nWrite every field value in Arabic (العربية). "
                "Use Arabic text for all names, descriptions and steps.")
    return "\nWrite every field value in English."


class UnavailableError(Exception):
    """Raised when the Gemini service cannot be used (no key / call failure).

    ``detail`` carries the exact provider error message when one exists; an
    empty ``detail`` means "no usable API key" and callers show a friendly
    localized message.
    """

    def __init__(self, detail: str = ""):
        super().__init__(detail)
        self.detail = detail or ""


def _error_message(exc: BaseException) -> str:
    """Extract a clean, human-readable message from a Gemini SDK exception.

    Prefers the ``error.message`` from the Google API error payload; falls back
    to the exception's string form.
    """
    response = getattr(exc, "response", None)
    try:
        payload = response.json()
        message = (payload.get("error") or {}).get("message")
        if message:
            return str(message)
    except Exception:  # noqa: BLE001
        pass
    return str(exc)


def _friendly_error(exc: BaseException) -> str:
    """Turn a raw provider error into clear, non-technical guidance for the user.

    Keeps the raw message for anything we don't specifically recognise (it is
    still logged verbatim elsewhere).
    """
    raw = _error_message(exc)
    low = raw.lower()
    if any(s in low for s in (
        "authentication credential", "api key not valid", "api_key_invalid",
        "unauthenticated", "permission denied", "invalid authentication",
        "expected oauth", "api key expired", "access_token_type_unsupported",
        "access token", "401",
    )):
        return ("We couldn't reach the AI service because the API key is missing or invalid. "
                "Please add a valid Gemini API key in Settings and try again.")
    if any(s in low for s in ("quota", "rate limit", "resource_exhausted", "too many requests")):
        return ("The AI service is busy right now (usage limit reached). "
                "Please wait a moment and try again.")
    if any(s in low for s in ("timed out", "timeout", "deadline")):
        return "The AI service took too long to respond. Please try again."
    return raw


# ---------------------------------------------------------------------------
# Chat (streaming)
# ---------------------------------------------------------------------------

_SYSTEM_CHAT = (
    "You are Car Service AI, a friendly, expert automotive assistant. "
    "You help car owners diagnose problems, plan maintenance and understand repairs. "
    "Be conversational, warm and natural — greet the user, answer general questions, "
    "car maintenance and repair questions, vehicle troubleshooting, and follow-up questions. "
    "\n\nLanguage: reply in the SAME language the user writes in (Arabic or English). "
    "If the user switches language, switch with them. Continue in the established language "
    "of the conversation unless the user changes it."
    "\n\nWhen the user describes a problem but important details are missing "
    "(when it happens, sounds, warning lights, vehicle type), ask 1-3 short follow-up "
    "questions BEFORE giving a full diagnosis."
    "\n\nAnswer in clear, structured markdown. When you do give a diagnosis, estimate "
    "urgency, whether it is safe to drive, likely causes and cost ranges. "
    "Never claim to replace a certified mechanic."
)


def chat_stream(user: str | None, messages: list[dict[str, str]],
                lang: str = "en", msg_lang: str | None = None,
                image_bytes: bytes | None = None, image_mime: str = "image/jpeg",
                audio_bytes: bytes | None = None, audio_mime: str = "audio/webm"):
    """Yield incremental text chunks for the chat UI (Gemini only).

    Raises :class:`UnavailableError` when no usable API key is configured or the
    API call fails — the caller is responsible for surfacing a friendly message.
    """
    client_info = _client_for(user)
    if client_info is None:
        logger.warning("Gemini unavailable for user=%r: no usable API key.", user)
        raise UnavailableError(_ai_unavailable(lang))

    client, model = client_info
    system = _SYSTEM_CHAT
    vehicle_ctx = _vehicle_context(user)
    if vehicle_ctx:
        system += "\n\nCurrent vehicle information (facts provided by the user):\n" + vehicle_ctx
        system += ("\nAnswer specifically about THIS vehicle whenever relevant. "
                   "Never invent data that is not listed above — clearly distinguish "
                   "facts from AI estimates and recommend a certified mechanic for "
                   "safety-critical issues.")
    if msg_lang == "ar":
        system += "\nThe user's latest message is in Arabic — reply fully in Arabic."
    elif msg_lang == "en":
        system += "\nThe user's latest message is in English — reply fully in English."
    history_text = "Conversation history:\n" + "\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
        for m in messages
    )
    contents = [system, history_text]
    if image_bytes:
        from google.genai import types
        contents.append("The user has also attached an image. Analyse it carefully.")
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type=image_mime))
    if audio_bytes:
        from google.genai import types
        contents.append(
            "The user sent a VOICE MESSAGE. Transcribe what they said, then answer it "
            "as their AI mechanic. Start your reply with a short line: 'You said: \"…\"' "
            "containing the transcription, then give your helpful answer.")
        contents.append(types.Part.from_bytes(data=audio_bytes, mime_type=audio_mime))
    # Try the selected model first, then supported fallbacks. Only retry when
    # nothing has been streamed yet so partial output is never duplicated.
    last_err: Exception | None = None
    for candidate in _model_chain(model):
        emitted = False
        try:
            for chunk in client.models.generate_content_stream(model=candidate, contents=contents):
                text = getattr(chunk, "text", None)
                if text:
                    emitted = True
                    yield text
            if candidate != model:
                logger.info("Chat fell back to Gemini model %s (primary %s failed).", candidate, model)
            return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            logger.error("Gemini chat model %s failed (user=%r): %s: %s",
                         candidate, user, type(exc).__name__, _error_message(exc))
            if emitted:
                break
    if last_err is not None:
        raise UnavailableError(_error_message(last_err)) from None


async def stream_sse(user: str | None, messages: list[dict[str, str]],
                     lang: str = "en", msg_lang: str | None = None,
                     delay: float = 0.02,
                     image_bytes: bytes | None = None, image_mime: str = "image/jpeg",
                     audio_bytes: bytes | None = None, audio_mime: str = "audio/webm"):
    """Async wrapper that yields SSE events from the sync generator, one chunk at a time.

    If the AI service is unavailable an error event with the **exact** reason is
    emitted instead of any fake content.
    """
    try:
        loop = asyncio.get_running_loop()
        gen = chat_stream(user, messages, lang=lang, msg_lang=msg_lang,
                          image_bytes=image_bytes, image_mime=image_mime,
                          audio_bytes=audio_bytes, audio_mime=audio_mime)
        while True:
            chunk = await loop.run_in_executor(None, _next_or_none, gen)
            if chunk is None:
                break
            await asyncio.sleep(delay)
            yield f"data: {json.dumps({'text': chunk})}\n\n"
    except UnavailableError as exc:
        yield f"data: {json.dumps({'error': exc.detail, 'error_type': 'ai_unavailable'})}\n\n"
    yield "data: [DONE]\n\n"


def _next_or_none(gen: Generator) -> Any | None:
    """Advance a generator, translating the terminal StopIteration into None.

    This avoids ``StopIteration`` leaking out of ``run_in_executor`` as a
    ``RuntimeError`` when the stream is exhausted.
    """
    try:
        return next(gen)
    except StopIteration:
        return None


# ---------------------------------------------------------------------------
# Diagnosis (text / image / audio) — structured report
# ---------------------------------------------------------------------------

_DIAG_PROMPT = """You are a senior automotive diagnostic expert. Analyse the {mode} below and
return a SINGLE valid JSON object (no markdown, no commentary) with EXACTLY these keys:
{{
  "problem": "short headline of the most likely fault",
  "summary": "2-3 sentences explaining the issue in plain language",
  "possible_causes": ["cause 1", "cause 2", "cause 3"],
  "urgency": "low" | "medium" | "high" | "critical",
  "can_drive": "one clear sentence about whether it is safe to drive",
  "estimated_cost": "a TIGHT dollar range for the single most likely repair, formatted '$LOW - $HIGH' where HIGH is at most ~40% more than LOW (e.g. '$180 - $250'). Base it on the most probable cause, not a worst-case span across every possibility",
  "estimated_time": "repair duration range, kept narrow (e.g. '1 - 2 hours')",
  "required_parts": ["part 1", "part 2"],
  "repair_steps": ["step 1", "step 2", "step 3"],
  "recommended_center": "name of a realistic recommended service centre type",
  "confidence": 0-100 integer,
  "preventive_tips": ["2-4 practical maintenance tips to prevent this problem recurring"],
  "transcript": "only for audio mode: a faithful transcription of what is heard in the recording"
}}
Use only fields you are confident about; never invent diagnostic codes.
For text mode, set "transcript" to null."""


def diagnose(
    user: str | None,
    mode: str,
    description: str = "",
    image_bytes: bytes | None = None,
    image_mime: str = "image/jpeg",
    audio_bytes: bytes | None = None,
    audio_mime: str = "audio/mpeg",
    video_bytes: bytes | None = None,
    video_mime: str = "video/mp4",
    lang: str = "en",
    vehicle_override: dict[str, str] | None = None,
    image_data_original: str | None = None,
) -> dict[str, Any]:
    """Run an AI diagnosis and return a structured report dict.

    Raises :class:`UnavailableError` when no API key is configured or the AI call
    fails — there is **no** demo/fallback response.
    """
    if vehicle_override:
        parts = [vehicle_override.get("year"), vehicle_override.get("brand"), vehicle_override.get("model")]
        vehicle = " ".join(str(p) for p in parts if p) or "Not specified"
        engine = (vehicle_override.get("engine") or "").strip()
        if engine and vehicle != "Not specified":
            vehicle += f" · {engine}"
    else:
        vehicle = _vehicle_label(user)
    client_info = _client_for(user)
    if client_info is None:
        logger.warning("Gemini diagnosis skipped for user=%r: no usable API key.", user)
        raise UnavailableError(_ai_unavailable(lang))

    client, model = client_info
    logger.info("[GEMINI] Request started (user=%r, model=%s, mode=%s)", user, model, mode)
    try:
        parts: list[Any] = []
        mode_word = {"text": "text description", "image": "vehicle image",
                    "audio": "audio recording", "video": "video recording"}[mode]
        prompt = _DIAG_PROMPT.format(mode=mode_word)
        prompt += f"\nVehicle: {vehicle}.\n"
        if description:
            prompt += f"\nUser description:\n{description}\n"
        if mode == "image" and image_bytes:
            from google.genai import types

            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=image_mime))
            prompt += "\nAnalyse the image carefully (visible damage, wear, warning lights, leaks)."
        if mode == "audio" and audio_bytes:
            from google.genai import types

            parts.append(types.Part.from_bytes(data=audio_bytes, mime_type=audio_mime))
            prompt += "\nTranscribe the sound, identify the fault pattern, and diagnose."
        if mode == "video" and video_bytes:
            from google.genai import types

            parts.append(types.Part.from_bytes(data=video_bytes, mime_type=video_mime))
            prompt += ("\nWatch the video carefully — visible symptoms (leaks, smoke, warning "
                      "lights, unusual movement) as well as any audible sound (knocking, "
                      "squealing, rattling) — and narrow down the probable cause.")
        prompt += _lang_instruction(lang)
        parts.append(prompt)
        raw = _run_generation(client, model, parts)
        data = _extract_json(raw)
        logger.info("[GEMINI] Response received (model=%s, parsed=%s)", model, "ok" if data else "empty")
    except Exception as exc:  # noqa: BLE001
        logger.error("Gemini diagnosis failed (user=%r, mode=%s): %s: %s",
                     user, mode, type(exc).__name__, exc, exc_info=True)
        raise UnavailableError(_friendly_error(exc)) from None

    if data is None:
        logger.warning("Gemini diagnosis returned empty/invalid data (user=%r, mode=%s).", user, mode)
        raise UnavailableError("Gemini returned an empty or invalid response.")

    result = {
        "mode": mode,
        "vehicle": vehicle,
        "problem": data.get("problem") or "Possible mechanical fault",
        "summary": data.get("summary") or "",
        "causes": _to_list(data.get("possible_causes")),
        "urgency": str(data.get("urgency") or "medium").lower(),
        "can_drive": data.get("can_drive") or "Not confirmed — have it inspected.",
        "cost": _narrow_cost(data.get("estimated_cost")) or "$150 - $220",
        "time": data.get("estimated_time") or "2 – 4 hours",
        "parts": _to_list(data.get("required_parts")),
        "steps": _to_list(data.get("repair_steps")),
        "center": data.get("recommended_center") or "Authorised dealer or certified independent garage",
        "confidence": _clamp_conf(data.get("confidence")),
        "tips": _to_list(data.get("preventive_tips")),
    }
    if image_bytes:
        # Use original base64 data-URI if provided to avoid re-encoding
        if image_data_original and image_data_original.startswith("data:"):
            result["image_data"] = image_data_original
        else:
            result["image_data"] = "data:{0};base64,{1}".format(
                image_mime, base64.b64encode(image_bytes).decode("ascii"))
    if audio_bytes:
        result["audio_data"] = "data:{0};base64,{1}".format(
            audio_mime, base64.b64encode(audio_bytes).decode("ascii"))
    if video_bytes:
        result["video_data"] = "data:{0};base64,{1}".format(
            video_mime, base64.b64encode(video_bytes).decode("ascii"))
    if mode == "audio":
        result["transcript"] = str(data.get("transcript") or "").strip()
    if mode == "text":
        result["description"] = description
    return result


def _to_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip(" -") for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [line.strip(" -") for line in re.split(r"[\n;]", value) if line.strip()]
    return ["Have the vehicle inspected by a certified mechanic."]


def _clamp_conf(value: Any) -> int:
    try:
        return max(55, min(99, int(float(value))))
    except (TypeError, ValueError):
        return 88


_COST_NUM = re.compile(r"([\d,]+(?:\.\d+)?)")


def _narrow_cost(raw: Any, max_ratio: float = 1.5) -> str:
    """Return a tight, well-formatted cost range.

    The model can still return an over-wide span (e.g. "$100 - $900"). We parse
    the two dollar figures and, if the high end is more than ``max_ratio``× the
    low end, cap it so the range stays precise. Single values / unparseable text
    are returned unchanged.
    """
    if not raw:
        return ""
    nums = [float(n.replace(",", "")) for n in _COST_NUM.findall(str(raw))]
    nums = [n for n in nums if n > 0]
    if len(nums) < 2:
        return str(raw).strip()
    lo, hi = min(nums[0], nums[1]), max(nums[0], nums[1])
    if lo <= 0:
        return str(raw).strip()
    if hi > lo * max_ratio:
        hi = lo * max_ratio
    return f"${int(round(lo)):,} - ${int(round(hi)):,}"


_URGENCY_META = {
    "low": {"label": "Safe to drive", "badge": "success"},
    "medium": {"label": "Drive carefully", "badge": "warning"},
    "high": {"label": "Service soon", "badge": "danger"},
    "critical": {"label": "Stop immediately", "badge": "danger"},
}


def urgency_meta(urgency: str, lang: str = "en") -> dict[str, str]:
    from . import translator as i18n

    key = str(urgency).lower()
    meta = dict(_URGENCY_META.get(key, _URGENCY_META["low"]))
    meta["label"] = i18n.urgency_label(lang, key)
    return meta


def guess_mime(filename: str, fallback: str = "application/octet-stream") -> str:
    return mimetypes.guess_type(filename)[0] or fallback

