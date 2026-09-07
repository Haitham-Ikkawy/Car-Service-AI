"""Public Gemini service facade used by routes, scripts and tests.

Wraps :mod:`src.shared.utils.gemini` behind a small, stable, fully **async** API.

The key is always read from the project ``.env`` file (see
:func:`load_api_key`) and never hardcoded. Every blocking SDK call runs in a
worker thread so the FastAPI event loop is never blocked.

Public functions:
    * ``load_api_key(user=None)``          — effective API key.
    * ``test_connection(user=None, key=None)`` — verify a key with a real request.
    * ``chat(user, message, lang, ...)``   — complete (non-streaming) chat reply.
    * ``stream_chat(user, messages, ...)`` — async SSE generator for the chat UI.
    * ``analyze_image(image_file, description, user)``  — image diagnosis report.
    * ``analyze_audio(audio_file, description, user)``  — audio diagnosis report.
    * ``repair_report(user, mode, ...)``   — full structured repair report (text/image/audio).
    * ``detect_vehicle(user, message)``    — auto-detect vehicle info.

Every failure is logged and re-raised as :class:`GeminiServiceError` carrying the
exact provider error message. There are **no demo / fake responses** — when no
API key is configured a clear error is raised instead.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, AsyncIterator

from src.shared.utils import gemini
from src.shared.utils.gemini import UnavailableError

logger = logging.getLogger("car_ai.gemini_service")


class GeminiServiceError(RuntimeError):
    """Raised when a Gemini call fails.

    ``detail`` holds the exact error returned by the provider when available;
    ``missing_key`` is True when no API key is configured.
    """

    def __init__(self, detail: str = "", *, missing_key: bool = False):
        super().__init__(detail or "Gemini service unavailable.")
        self.detail = detail or ""
        self.missing_key = missing_key


def _to_error(exc: BaseException) -> GeminiServiceError:
    detail = getattr(exc, "detail", None)
    return GeminiServiceError(detail if isinstance(detail, str) and detail else str(exc),
                              missing_key=not bool(detail))


# ---------------------------------------------------------------------------
# Key handling
# ---------------------------------------------------------------------------

def load_api_key(user: str | None = None) -> str:
    """Return the effective Gemini API key (re-read from ``.env``).

    Precedence: environment ``GEMINI_API_KEY``, then the per-user key saved via
    the Settings page. Returns ``""`` when no key is configured.
    """
    return gemini.load_api_key(user)


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

async def test_connection(user: str | None = None, key: str | None = None,
                          timeout: float = 30.0) -> dict[str, str]:
    """Verify the API key with a minimal real request (runs in a thread).

    Returns a dict: ``{"state": "ok"|"invalid"|"missing"|"error", ...}``.
    """
    return await asyncio.to_thread(gemini.test_gemini_connection, user, key, timeout)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

def _normalize_messages(message: str | list[dict[str, str]]) -> list[dict[str, str]]:
    if isinstance(message, str):
        return [{"role": "user", "content": message}]
    return [
        {"role": str(item.get("role", "user")), "content": str(item.get("content", ""))}
        for item in message
    ]


async def chat(user: str | None, message: str | list[dict[str, str]],
               lang: str = "en", msg_lang: str | None = None) -> str:
    """Send a message to Gemini Chat and return the **complete** reply.

    ``message`` may be a plain string or a list of ``{"role", "content"}``
    history entries. Raises :class:`GeminiServiceError` on any failure.
    """
    messages = _normalize_messages(message)

    def _run() -> str:
        chunks = gemini.chat_stream(user, messages, lang=lang, msg_lang=msg_lang)
        return "".join(chunk for chunk in chunks)

    try:
        return await asyncio.to_thread(_run)
    except UnavailableError as exc:
        logger.error("chat failed (user=%r): %s", user, exc.detail or exc, exc_info=True)
        raise _to_error(exc) from None
    except Exception as exc:  # noqa: BLE001
        logger.error("chat unexpected error (user=%r): %s: %s",
                     user, type(exc).__name__, exc, exc_info=True)
        raise GeminiServiceError(str(exc)) from None


async def stream_chat(user: str | None, messages: list[dict[str, str]],
                      lang: str = "en", msg_lang: str | None = None) -> AsyncIterator[str]:
    """Yield raw SSE strings (``data: {...}\\n\\n``) for the chat UI.

    An ``error`` event is emitted when the AI service cannot be used.
    """
    async for event in gemini.stream_sse(user, messages, lang=lang, msg_lang=msg_lang):
        yield event


# ---------------------------------------------------------------------------
# Uploads → report
# ---------------------------------------------------------------------------

def _read_upload(upload: Any) -> tuple[bytes, str]:
    """Normalize an upload (bytes, file-like object or path) to (bytes, mime)."""
    if upload is None:
        raise GeminiServiceError("No file was provided.")
    if isinstance(upload, bytes):
        return upload, "application/octet-stream"
    if isinstance(upload, (str, Path)):
        path = Path(upload)
        return path.read_bytes(), gemini.guess_mime(path.name)
    name = getattr(upload, "name", "") or ""
    data = upload.read()
    if isinstance(data, str):
        data = data.encode("utf-8")
    return data, gemini.guess_mime(name)


async def _run_diagnose(user: str | None, mode: str, *, description: str,
                        image_bytes: bytes | None, image_mime: str,
                        audio_bytes: bytes | None, audio_mime: str) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            gemini.diagnose, user, mode, description=description,
            image_bytes=image_bytes, image_mime=image_mime,
            audio_bytes=audio_bytes, audio_mime=audio_mime,
        )
    except UnavailableError as exc:
        logger.error("repair_report failed (user=%r, mode=%s): %s",
                     user, mode, exc.detail or exc, exc_info=True)
        raise _to_error(exc) from None
    except Exception as exc:  # noqa: BLE001
        logger.error("repair_report unexpected error (user=%r, mode=%s): %s: %s",
                     user, mode, type(exc).__name__, exc, exc_info=True)
        raise GeminiServiceError(str(exc)) from None


async def repair_report(user: str | None, mode: str, description: str = "",
                        image_file: Any = None, audio_file: Any = None) -> dict[str, Any]:
    """Full structured AI repair report (``text`` / ``image`` / ``audio``).

    ``image_file`` / ``audio_file`` accept bytes, a file-like object or a path.
    Returns the report dict used by the diagnosis / reports pages.
    """
    image_bytes = image_mime = audio_bytes = audio_mime = None
    if mode == "image":
        image_bytes, image_mime = _read_upload(image_file)
    elif mode == "audio":
        audio_bytes, audio_mime = _read_upload(audio_file)
    return await _run_diagnose(user, mode, description=description.strip(),
                               image_bytes=image_bytes, image_mime=image_mime or "image/jpeg",
                               audio_bytes=audio_bytes, audio_mime=audio_mime or "audio/mpeg")


async def analyze_image(image_file: Any, description: str = "",
                        user: str | None = None) -> dict[str, Any]:
    """Analyze a vehicle image and return the diagnosis report dict."""
    return await repair_report(user, "image", description=description, image_file=image_file)


async def analyze_audio(audio_file: Any, description: str = "",
                        user: str | None = None) -> dict[str, Any]:
    """Analyze a vehicle audio recording and return the diagnosis report dict."""
    return await repair_report(user, "audio", description=description, audio_file=audio_file)


# ---------------------------------------------------------------------------
# Vehicle auto-detection
# ---------------------------------------------------------------------------

async def detect_vehicle(user: str | None, message: str) -> dict[str, Any] | None:
    """Detect vehicle info from a free-text message.

    Returns ``None`` when nothing can be detected (no key or no match) — callers
    surface a friendly error. Runs in a thread so the loop is not blocked.
    """
    return await asyncio.to_thread(gemini.detect_vehicle, user, message)


# ---------------------------------------------------------------------------
# Backwards-compatible aliases
# ---------------------------------------------------------------------------

chat_with_gemini = chat
