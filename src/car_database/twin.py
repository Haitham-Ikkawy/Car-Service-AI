"""Digital-twin helpers: AI vehicle health analysis and AI auto-detection.

Both degrade gracefully: when no API key is configured (demo mode) they return
a fallback payload marked ``unavailable`` so the UI can show a friendly hint.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.shared.store import store
from src.shared.utils import gemini

logger = logging.getLogger(__name__)

_COMPONENT_KEYS = ("engine", "battery", "cooling", "brakes", "tires",
                   "suspension", "transmission", "electrical")

_TWIN_PROMPT = """You are an automotive engineer. Based on the vehicle profile below,
produce a strict JSON object (no markdown) with this exact schema:
{{
  "health": 0..100 overall condition score,
  "summary": "one paragraph plain-text assessment",
  "components": [
    {{"key": "engine|battery|cooling|brakes|tires|suspension|transmission|electrical",
     "status": "ok|warn|critical", "note": "short reason"}}
  ],
  "recommendations": ["list of 2-4 actionable plain-text recommendations"],
  "estimated_cost": "one plain-text maintenance cost estimate"
}}
Vehicle profile: {profile}
Base the statuses on typical condition for the given year, mileage and fuel type,
using sound engineering judgment. Use field names exactly as above."""

_FALLBACK_TWIN: dict[str, Any] = {
    "health": None,
    "summary": None,
    "components": [],
    "recommendations": [],
    "estimated_cost": None,
    "unavailable": True,
}


def _profile_text(user: str) -> str:
    v = store.vehicle(user) or {}
    return json.dumps(v, ensure_ascii=False)


def analyze_twin(user: str) -> dict[str, Any]:
    """Run (or return the cached) AI health analysis for the user's vehicle."""
    if not store.vehicle(user):
        return dict(_FALLBACK_TWIN)
    cached = store.twin(user)
    if cached:
        return cached
    try:
        raw = gemini.ask_gemini(_TWIN_PROMPT.format(profile=_profile_text(user)), user)
    except gemini.UnavailableError as exc:  # noqa: PERF203
        logger.info("twin unavailable for user=%r: %s", user, exc)
        result = dict(_FALLBACK_TWIN)
        store.set_twin(user, result)
        return result
    data = gemini._extract_json(raw)
    if not data:
        data = dict(_FALLBACK_TWIN)
        data["unavailable"] = False
    health = data.get("health")
    if isinstance(health, (int, float)):
        data["health"] = max(0, min(100, int(round(health))))
    comps = []
    for c in data.get("components") or []:
        if not isinstance(c, dict):
            continue
        key = str(c.get("key") or "").lower()
        if key not in _COMPONENT_KEYS:
            continue
        status = str(c.get("status") or "ok").lower()
        if status not in ("ok", "warn", "critical"):
            status = "ok"
        comps.append({"key": key, "status": status, "note": str(c.get("note") or "")})
    if comps:
        data["components"] = comps
    data["unavailable"] = False
    store.set_twin(user, data)
    return data


_DETECT_PROMPT = """You are an automotive expert. Read the user's free-text car
description and return a strict JSON object (no markdown) with ONLY these fields:
{{
  "manufacturer": "matched brand or null",
  "model": "matched model or null",
  "year": integer or null,
  "fuel": "Petrol|Diesel|Electric|Hybrid|LPG/CNG" or null,
  "transmission": "Automatic|Manual|CVT|Dual-Clutch" or null,
  "mileage": integer km or null,
  "chassis": "VIN / chassis code if mentioned, else null",
  "confidence": 0..1
}}
Match against the user's words only; do not invent values. Use null for anything
not mentioned. Description: "{text}"""

_DETECT_FALLBACK = {
    "manufacturer": None, "model": None, "year": None,
    "fuel": None, "transmission": None, "mileage": None,
    "chassis": None, "confidence": 0.0, "unavailable": True,
}


def detect_vehicle(text: str, user: str | None = None) -> dict[str, Any]:
    """Best-effort AI extraction of vehicle fields from a free-text description."""
    if not text.strip():
        return dict(_DETECT_FALLBACK)
    try:
        raw = gemini.ask_gemini(_DETECT_PROMPT.format(text=text.strip()[:400]), user)
    except gemini.UnavailableError as exc:  # noqa: PERF203
        logger.info("detect unavailable for user=%r: %s", user, exc)
        return dict(_DETECT_FALLBACK)
    data = gemini._extract_json(raw)
    if not data:
        return dict(_DETECT_FALLBACK)
    result = {k: data.get(k) for k in _DETECT_FALLBACK if k != "unavailable"}
    result["unavailable"] = False
    return result


_IDENTIFY_PROMPT = """You are an automotive expert with strong visual vehicle-recognition
skills. Look at the attached photo of a car and identify it as precisely as you can.
Return a strict JSON object (no markdown) with ONLY these fields:
{
  "manufacturer": "best-guess brand, else null",
  "model": "best-guess model, else null",
  "year": "best-guess model year or a range like '2019-2022', else null",
  "body_style": "sedan|suv|hatchback|coupe|pickup|van|wagon|convertible or null",
  "color": "dominant exterior color, else null",
  "confidence": 0..1 (how confident you are in the manufacturer/model guess),
  "notes": "one short sentence on visual cues used (badges, headlight shape, grille, etc.), or null"
}
If the image does not clearly show a car, set manufacturer/model to null and confidence to 0."""

_IDENTIFY_FALLBACK: dict[str, Any] = {
    "manufacturer": None, "model": None, "year": None,
    "body_style": None, "color": None, "confidence": 0.0,
    "notes": None, "unavailable": True,
}


def identify_vehicle_image(image_bytes: bytes, image_mime: str, user: str | None = None) -> dict[str, Any]:
    """Best-effort AI identification of a vehicle's make/model from a photo."""
    try:
        raw = gemini.ask_gemini_image(_IDENTIFY_PROMPT, image_bytes, image_mime, user)
    except gemini.UnavailableError as exc:  # noqa: PERF203
        logger.info("identify_vehicle_image unavailable for user=%r: %s", user, exc)
        return dict(_IDENTIFY_FALLBACK)
    data = gemini._extract_json(raw)
    if not data:
        return dict(_IDENTIFY_FALLBACK)
    result = {k: data.get(k) for k in _IDENTIFY_FALLBACK if k != "unavailable"}
    try:
        result["confidence"] = max(0.0, min(1.0, float(result.get("confidence") or 0)))
    except (TypeError, ValueError):
        result["confidence"] = 0.0
    result["unavailable"] = False
    return result


def part_report(user: str, key: str, vehicle_label: str) -> dict[str, Any]:
    """Static part specs merged with an optional short AI insight."""
    from src.car_database.parts import part

    info = part(key)
    if not info:
        return {"error": "part_not_found"}
    payload: dict[str, Any] = {"key": key, "name": info["name"], "spec": info["spec"],
                               "issues": info["issues"], "tip": info["tip"],
                               "lifespan": info["lifespan"]}
    try:
        prompt = (f"Give a 3-4 sentence plain-text condition insight about the {info['name']} "
                  f"for a {vehicle_label}. Keep it practical and honest.")
        payload["ai_report"] = gemini.ask_gemini(prompt, user).strip()
    except gemini.UnavailableError:
        payload["ai_report"] = None
    return payload
