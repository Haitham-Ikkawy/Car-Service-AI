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
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger("car_ai.vehicle_api")

# --- Upstream endpoints ------------------------------------------------------
_VPIC = "https://vpic.nhtsa.dot.gov/api/vehicles"
_CARQUERY = "https://www.carqueryapi.com/api/0.3/"

# Vehicle images: we prefer REAL PHOTOS of the actual car (Wikipedia / Wikimedia
# Commons lead image for the model page) and deliberately AVOID CGI blueprint /
# schematic-style renders. Wikipedia is free, keyless and returns genuine
# photographs; SVG results (logos / line-art) are filtered out.
_WIKI_API = "https://en.wikipedia.org/w/api.php"

# imagin.studio (CGI renders) is kept ONLY as an opt-in last resort behind a
# licensed key — the public demo key produces watermarked, schematic-looking
# images, which the product explicitly excludes, so it is off by default.
_IMAGIN_CDN = "https://cdn.imagin.studio/getimage"
_IMAGIN_CUSTOMER = os.getenv("IMAGIN_CUSTOMER", "").strip()  # empty => don't use imagin

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
    """All passenger-vehicle makes (vPIC), enriched with a local logo when we have one.

    Unions the ``car``, ``mpv`` (SUV/crossover) and ``truck`` (pickup) vehicle
    types so SUV/EV-only brands (e.g. Rivian) are included — a single type misses
    them. Motorcycle/trailer/etc. types are intentionally excluded.
    """

    async def _type(vtype: str) -> list[dict]:
        try:
            data = await _get_json(f"{_VPIC}/GetMakesForVehicleType/{vtype}", {"format": "json"})
            return data.get("Results") or []
        except Exception:  # noqa: BLE001
            return []

    async def _load() -> list[dict]:
        try:
            groups = await asyncio.gather(_type("car"), _type("mpv"), _type("truck"))
            rows = [r for g in groups for r in g]
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


# ---------------------------------------------------------------------------
# VIN decode — look up a vehicle from its 17-character VIN (NHTSA vPIC)
# ---------------------------------------------------------------------------

# A VIN is 17 characters, letters + digits, excluding I, O and Q (to avoid
# confusion with 1 and 0).
_VIN_RE = None  # compiled lazily to keep import light


def _valid_vin(vin: str) -> bool:
    import re
    global _VIN_RE
    if _VIN_RE is None:
        _VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
    return bool(_VIN_RE.match((vin or "").strip().upper()))


async def decode_vin(vin: str) -> dict[str, Any]:
    """Decode a VIN into structured vehicle fields via NHTSA vPIC.

    Returns ``{ok, vin, make, model, year, fuel, engine, body, ...}``. ``ok`` is
    False (with a ``message``) for an invalid VIN or when the lookup finds no
    make/model — the caller shows a friendly message and lets the user pick
    manually instead.
    """
    vin = (vin or "").strip().upper()
    if not _valid_vin(vin):
        return {"ok": False, "message": "That doesn't look like a valid 17-character VIN."}

    async def _load() -> dict[str, Any]:
        try:
            data = await _get_json(f"{_VPIC}/DecodeVinValues/{quote(vin, safe='')}",
                                   {"format": "json"})
            rows = data.get("Results") or []
            row = rows[0] if rows else {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("vPIC VIN decode failed (%s): %s: %s", vin, type(exc).__name__, exc)
            return {"ok": False, "message": "The VIN lookup service is unavailable right now. Please try again or pick your car manually."}

        make = _title(row.get("Make") or "")
        model = (row.get("Model") or "").strip()
        year = (row.get("ModelYear") or "").strip()
        fuel = (row.get("FuelTypePrimary") or "").strip()
        disp = (row.get("DisplacementL") or "").strip()
        cyl = (row.get("EngineCylinders") or "").strip()
        body = (row.get("BodyClass") or "").strip()
        trans = (row.get("TransmissionStyle") or "").strip()

        if not make and not model:
            return {"ok": False, "message": "We couldn't find a car for that VIN. Please pick your vehicle manually."}

        # Build a friendly engine descriptor from displacement + cylinders + fuel.
        parts = []
        if disp:
            try:
                parts.append(f"{float(disp):.1f}L")
            except ValueError:
                pass
        if fuel and fuel.lower() not in ("", "not applicable"):
            parts.append(fuel)
        if cyl:
            parts.append(f"{cyl}-cyl")
        engine = " ".join(parts).strip()

        return {
            "ok": True,
            "vin": vin,
            "make": make,
            "model": model,
            "year": year,
            "fuel": fuel,
            "engine": engine,
            "transmission": trans,
            "body": body,
            "logo": _logo_for(make),
            "image": _image_for(make, model) or image_url(make, model, year),
        }

    return await _cached(f"vin:{vin}", _load)


# ---------------------------------------------------------------------------
# Dynamic vehicle image — per make/model/year, from an external CDN
# ---------------------------------------------------------------------------

def local_image(make: str, model: str) -> str:
    """A shipped local image for this make/model, or empty string."""
    return _image_for(make, model) or ""


def _imagin_url(make: str, model: str, year: str | int = "") -> str:
    """Last-resort CGI render URL — only when a licensed imagin key is set."""
    if not _IMAGIN_CUSTOMER:
        return ""
    make = (make or "").strip().lower()
    if not make:
        return ""
    params = {
        "customer": _IMAGIN_CUSTOMER, "make": make,
        "modelFamily": (model or "").strip().lower(),
        "zoomType": "fullscreen", "angle": "23",
    }
    year = str(year or "").strip()
    if year:
        params["modelYear"] = year
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items() if v)
    return f"{_IMAGIN_CDN}?{query}"


async def _wiki_photo(title: str) -> str | None:
    """Return the lead-image (real photo) URL of a Wikipedia page, or None.

    SVG results (logos / schematics) are rejected so only photographs are used.
    """
    try:
        data = await _get_json(_WIKI_API, {
            "action": "query", "format": "json", "redirects": "1",
            "prop": "pageimages", "piprop": "thumbnail|original", "pithumbsize": "800",
            "titles": title,
        })
    except Exception:  # noqa: BLE001
        return None
    pages = ((data or {}).get("query") or {}).get("pages") or {}
    for pid, page in pages.items():
        if str(pid) == "-1":
            continue
        src = ((page.get("thumbnail") or {}).get("source")
               or (page.get("original") or {}).get("source"))
        if src and not src.lower().split("?")[0].endswith(".svg"):
            return src
    return None


async def photo_url(make: str, model: str, year: str | int = "") -> str:
    """Resolve a realistic PHOTO of the given vehicle (make/model[/year]).

    Priority: a real photo from Wikipedia → a shipped local image → an optional
    licensed CGI render → empty (the UI then shows an icon). Blueprint/schematic
    (SVG) images are never returned. Cached per make/model/year.
    """
    make = (make or "").strip()
    model = (model or "").strip()
    if not make and not model:
        return ""
    year = str(year or "").strip()

    async def _load() -> str:
        # Try the most specific Wikipedia titles first, then broaden.
        titles: list[str] = []
        if make and model:
            if year:
                titles.append(f"{make} {model} ({year})")
            titles += [f"{make} {model}", f"{make} {model} (car)"]
        elif make:
            titles.append(make)
        for title in titles:
            src = await _wiki_photo(title)
            if src:
                return src
        # Fallbacks: shipped local image, then an optional licensed CGI render.
        return local_image(make, model) or _imagin_url(make, model, year)

    return await _cached(f"photo:{make.lower()}:{model.lower()}:{year}", _load)
