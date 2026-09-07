"""OpenAI (ChatGPT) provider for Car Service AI.

Mirrors the Gemini ``stream_sse`` interface so the chat route can switch
between providers transparently.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Generator

from dotenv import load_dotenv

from ... import config
from ..store import store
from .translator import ai_unavailable as _ai_unavailable

logger = logging.getLogger("car_ai.openai")

_NO_KEY_MESSAGE = (
    "No OpenAI API key is configured. Add your OpenAI API key in Settings "
    "to use ChatGPT."
)

# Supported ChatGPT models shown in the UI.
SUPPORTED_MODELS = (
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
)

DEFAULT_MODEL = "gpt-4o-mini"

# ---------------------------------------------------------------------------
# Client helpers
# ---------------------------------------------------------------------------

_CLIENT_CACHE: dict[str, Any] = {}


def _api_key(user: str | None) -> str:
    env_key = os.getenv("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key
    if user:
        key = (store.settings(user).get("openai_key") or "").strip()
        if key:
            return key
    return ""


def load_api_key(user: str | None = None) -> str:
    load_dotenv(config.BASE_DIR / ".env", override=True)
    return _api_key(user)


def _model_for(user: str | None, model: str | None = None) -> str:
    m = (model or "").strip() or (store.settings(user or "x").get("openai_model") or "").strip() or DEFAULT_MODEL
    if m not in SUPPORTED_MODELS:
        return DEFAULT_MODEL
    return m


def _client_for(user: str | None) -> Any | None:
    key = _api_key(user)
    if not key:
        return None
    cache_key = f"{user}|{key}"
    if cache_key in _CLIENT_CACHE:
        return _CLIENT_CACHE[cache_key]
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        _CLIENT_CACHE[cache_key] = client
        return client
    except Exception as exc:
        logger.error("OpenAI client init failed (user=%s): %s", user, exc, exc_info=True)
        return None


def is_demo(user: str | None = None) -> bool:
    return _client_for(user) is None


# ---------------------------------------------------------------------------
# System prompt — shared with Gemini for consistency
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


def _vehicle_context(user: str | None) -> str:
    from . import gemini as _g
    return _g._vehicle_context(user)


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------

class UnavailableError(Exception):
    def __init__(self, detail: str = ""):
        super().__init__(detail)
        self.detail = detail or ""


def chat_stream(user: str | None, messages: list[dict[str, str]],
                lang: str = "en", msg_lang: str | None = None,
                **_kwargs) -> Generator[str, None, None]:
    """Yield incremental text chunks for the chat UI (OpenAI only)."""
    client = _client_for(user)
    if client is None:
        raise UnavailableError(_ai_unavailable(lang))

    model = _model_for(user)
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

    oai_messages = [{"role": "system", "content": system}]
    for m in messages:
        oai_messages.append({"role": m["role"], "content": m["content"]})

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=oai_messages,
            stream=True,
            max_tokens=4096,
            temperature=0.7,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as exc:
        logger.error("OpenAI chat failed (user=%r, model=%s): %s",
                     user, model, exc, exc_info=True)
        raise UnavailableError(str(exc)) from None


async def stream_sse(user: str | None, messages: list[dict[str, str]],
                     lang: str = "en", msg_lang: str | None = None,
                     delay: float = 0.02, **_kwargs):
    """Async wrapper that yields SSE events from the sync generator."""
    try:
        loop = asyncio.get_running_loop()
        gen = chat_stream(user, messages, lang=lang, msg_lang=msg_lang)
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
    try:
        return next(gen)
    except StopIteration:
        return None
