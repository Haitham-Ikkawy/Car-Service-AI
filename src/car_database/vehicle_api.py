"""Live vehicle reference data — makes / models / engines.

Backs the cascading autocomplete in the diagnosis wizard (brand -> model ->
engine). Data comes from **live open-source APIs** (per product decision):

* Makes & models  -> NHTSA vPIC (https://vpic.nhtsa.dot.gov/api/) — free, no
  API key, comprehensive.
* Engines / trims -> CarQuery (https://www.carqueryapi.com/) when reachable,
  otherwise a sensible synthesized fallback so the UI always has options.

Everything is proxied **server-side** (avoids browser CORS + hides the upstream
shape) and cached in-memory with a TTL so per-keystroke autocomplete never
hammers the upstream APIs. Results are enriched with the project's local brand
logos and vehicle images when a matching asset exists on disk.

The module degrades gracefully: any upstream failure returns an empty list (for
makes/models) or the synthesized fallback (for engines) instead of raising, so
the wizard keeps working offline.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger("car_ai.vehicle_api")

# --- Upstream endpoints ------------------------------------------------------
_VPIC = "https://vpic.nhtsa.dot.gov/api/vehicles"
_CARQUERY = "https://www.carqueryapi.com/api/0.3/"

# --- Local media (used to enrich upstream data with images we already ship) --
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_LOGO_DIR = _PROJECT_ROOT / "image" / "car_logos"
_VEHICLE_DIR = _PROJECT_ROOT / "image" / "vehicles"

# --- Cache -------------------------------------------------------------------
_CACHE_TTL = 60 * 60 * 12  # 12 hours; reference data barely changes
_cache: dict[str, tuple[float, Any]] = {}
_locks: dict[str, asyncio.Lock] = {}

# Common fuel / engine descriptors used to synthesize options when the upstream
# trim API is unavailable. Keeps the third cascade step useful offline.
_FALLBACK_ENGINES = [
    {"value": "1.0L Petrol", "label": "1.0L Petrol (3-cyl)", "fuel": "Petrol"},
    {"value": "1.6L Petrol", "label": "1.6L Petrol (4-cyl)", "fuel": "Petrol"},
    {"value": "2.0L Petrol", "label": "2.0L Petrol (4-cyl)", "fuel": "Petrol"},
    {"value": "2.0L Turbo Petrol", "label": "2.0L Turbo Petrol", "fuel": "Petrol"},
    {"value": "3.0L Petrol", "label": "3.0L Petrol (6-cyl)", "fuel": "Petrol"},
    {"value": "2.0L Diesel", "label": "2.0L Diesel (4-cyl)", "fuel": "Diesel"},
    {"value": "3.0L Diesel", "label": "3.0L Diesel (6-cyl)", "fuel": "Diesel"},
    {"value": "Hybrid", "label": "Hybrid (Petrol-Electric)", "fuel": "Hybrid"},
    {"value": "Plug-in Hybrid", "label": "Plug-in Hybrid", "fuel": "Hybrid"},
    {"value": "Electric", "label": "Electric (EV)", "fuel": "Electric"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug(name: str) -> str:
    """Slugify a make/model the way the repo's image folders are named."""
    return (
        (name or "")
        .strip()
        .lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace("_", "-")
    )


def _logo_for(make: str) -> str | None:
    slug = _slug(make)
    for ext in (".svg", ".png"):
        if (_LOGO_DIR / f"{slug}{ext}").exists():
            return f"/image/car_logos/{slug}{ext}"
    return None


def _image_for(make: str, model: str) -> str | None:
    b, m = _slug(make), _slug(model)
    for ext in (".webp", ".png", ".jpg"):
        if (_VEHICLE_DIR / b / f"{m}{ext}").exists():
            return f"/image/vehicles/{b}/{m}{ext}"
    return None


# Canonical display names for makes that title-casing would mangle (acronyms,
# hyphenation, mixed caps). Keyed by the lowercased upstream name.
_CANONICAL = {
    "bmw": "BMW", "gmc": "GMC", "mini": "MINI", "seat": "SEAT", "ram": "RAM",
    "kia": "Kia", "fiat": "Fiat", "audi": "Audi", "mercedes-benz": "Mercedes-Benz",
    "mercedes benz": "Mercedes-Benz", "alfa romeo": "Alfa Romeo",
    "rolls-royce": "Rolls-Royce", "rolls royce": "Rolls-Royce",
    "land rover": "Land Rover", "aston martin": "Aston Martin",
    "mclaren": "McLaren", "mazda": "Mazda", "byd": "BYD", "ds": "DS",
    "mg": "MG", "smart": "smart", "citroen": "Citroën", "skoda": "Škoda",
    "volkswagen": "Volkswagen", "vw": "Volkswagen", "abarth": "Abarth",
}


def _title(name: str) -> str:
    """vPIC returns UPPERCASE names; present them in a friendly, canonical form."""
    name = (name or "").strip()
    if not name:
        return name
    canon = _CANONICAL.get(name.lower())
    if canon:
        return canon
    # Keep already-mixed-case names untouched (they're likely correct).
    if name != name.upper() and name != name.lower():
        return name
    # Title-case each space- and hyphen-separated segment ("MERCEDES-BENZ" ->
    # "Mercedes-Benz"), leaving very short tokens that read as acronyms upper.
    small = {"of", "and"}

    def _seg(word: str) -> str:
        subs = word.split("-")
        out = []
        for s in subs:
            if not s:
                out.append(s)
            elif len(s) <= 3 and s.isalpha():
                out.append(s.upper())  # short token -> treat as acronym (BMW, GMC)
            elif s.lower() in small:
                out.append(s.lower())
            else:
                out.append(s.capitalize())
        return "-".join(out)

    return " ".join(_seg(w) for w in name.split())


def _filter(items: list[dict], q: str, key: str = "value", limit: int = 12) -> list[dict]:
    """Rank items for autocomplete: exact > prefix > contains."""
    q = (q or "").strip().lower()
    if not q:
        return items[:limit]
    exact, prefix, contains = [], [], []
    for it in items:
        text = str(it.get(key, "")).lower()
        if text == q:
            exact.append(it)
        elif text.startswith(q):
            prefix.append(it)
        elif q in text:
            contains.append(it)
    return (exact + prefix + contains)[:limit]


async def _cached(key: str, producer) -> Any:
    """Return a cached value or run ``producer`` (async) once, memoized by key."""
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        hit = _cache.get(key)  # re-check after acquiring the lock
        if hit and time.time() - hit[0] < _CACHE_TTL:
            return hit[1]
        value = await producer()
        _cache[key] = (time.time(), value)
        return value


async def _get_json(url: str, params: dict | None = None) -> Any:
    async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "CarServiceAI/1.0"}) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Public API — each returns a list of {value, label, image?/logo?, ...}
# ---------------------------------------------------------------------------

async def makes(q: str = "", limit: int = 12) -> list[dict]:
    """All car makes (vPIC), enriched with a local logo when we have one."""

    async def _load() -> list[dict]:
        try:
            data = await _get_json(f"{_VPIC}/GetMakesForVehicleType/car", {"format": "json"})
            rows = data.get("Results") or []
            seen: set[str] = set()
            out: list[dict] = []
            for r in rows:
                name = _title(r.get("MakeName") or "")
                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())
                out.append({"value": name, "label": name, "logo": _logo_for(name)})
            out.sort(key=lambda x: x["value"].lower())
            return out
        except Exception as exc:  # noqa: BLE001 — degrade gracefully
            logger.warning("vPIC makes lookup failed: %s: %s", type(exc).__name__, exc)
            return []

    return _filter(await _cached("makes", _load), q, "value", limit)


async def models(make: str, q: str = "", limit: int = 12) -> list[dict]:
    """Models for a given make (vPIC), enriched with a local image when present."""
    make = (make or "").strip()
    if not make:
        return []

    async def _load() -> list[dict]:
        # Union the passenger-vehicle types so SUVs/crossovers (vPIC "mpv") and
        # pickups ("truck") are included, while motorcycles/ATVs/trailers are
        # excluded. Fetched concurrently, then de-duplicated.
        enc = quote(make, safe="")

        async def _type(vtype: str) -> list[dict]:
            try:
                data = await _get_json(
                    f"{_VPIC}/GetModelsForMakeYear/make/{enc}/vehicleType/{vtype}",
                    {"format": "json"},
                )
                return data.get("Results") or []
            except Exception:  # noqa: BLE001
                return []

        try:
            groups = await asyncio.gather(_type("car"), _type("mpv"), _type("truck"))
            seen: set[str] = set()
            out: list[dict] = []
            for rows in groups:
                for r in rows:
                    name = (r.get("Model_Name") or "").strip()
                    if not name or "�" in name or name.lower() in seen:
                        continue
                    seen.add(name.lower())
                    out.append({
                        "value": name,
                        "label": name,
                        "image": _image_for(make, name),
                    })
            out.sort(key=lambda x: x["value"].lower())
            return out
        except Exception as exc:  # noqa: BLE001
            logger.warning("vPIC models lookup failed (make=%s): %s: %s", make, type(exc).__name__, exc)
            return []

    return _filter(await _cached(f"models:{make.lower()}", _load), q, "value", limit)


async def engines(make: str, model: str, q: str = "", limit: int = 12) -> list[dict]:
    """Engine / trim options for a make+model.

    Tries CarQuery trims first (real engine descriptors), then falls back to a
    synthesized list so the third cascade step is always usable.
    """
    make, model = (make or "").strip(), (model or "").strip()
    if not make or not model:
        return _filter(list(_FALLBACK_ENGINES), q, "value", limit)

    async def _load() -> list[dict]:
        try:
            raw = await _get_json(_CARQUERY, {"cmd": "getTrims", "make": make, "model": model})
            # CarQuery sometimes wraps JSON in a JSONP callback — tolerate both.
            if isinstance(raw, str):
                raw = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            trims = raw.get("Trims") or []
            seen: set[str] = set()
            out: list[dict] = []
            for t in trims:
                cc = t.get("model_engine_cc")
                fuel = (t.get("model_engine_fuel") or "").strip()
                cyl = t.get("model_engine_cyl")
                litres = f"{round(int(cc) / 1000, 1)}L" if str(cc).isdigit() else ""
                parts = [p for p in (litres, fuel, (f"{cyl}-cyl" if cyl else "")) if p]
                label = " ".join(parts).strip()
                if not label or label.lower() in seen:
                    continue
                seen.add(label.lower())
                out.append({"value": label, "label": label, "fuel": fuel})
            if out:
                out.sort(key=lambda x: x["value"].lower())
                return out
        except Exception as exc:  # noqa: BLE001
            logger.info("CarQuery engines lookup failed (make=%s model=%s): %s — using fallback",
                        make, model, type(exc).__name__)
        return list(_FALLBACK_ENGINES)

    return _filter(await _cached(f"engines:{make.lower()}:{model.lower()}", _load), q, "value", limit)
