"""Environment / settings loader for Car Service AI.

Reads configuration from the project ``.env`` file and exposes simple constants.
Values can also be overridden at runtime through the Settings page (stored in memory).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent


def _strip_bom(path: Path) -> None:
    """Remove a UTF-8 BOM so python-dotenv can parse the first key."""
    if path.exists():
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            path.write_bytes(raw[3:])


# Load .env if present (missing file is fine — demo mode kicks in).
# Strip any BOM first; otherwise GEMINI_API_KEY (the first line) would not load.
_strip_bom(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env")


def save_api_key(key: str) -> str:
    """Persist ``GEMINI_API_KEY`` to the project ``.env`` and reload it.

    The new value is written to ``.env`` and pushed into ``os.environ`` so the
    running app picks it up immediately — no restart or code change needed.
    """
    key = (key or "").strip()
    env_path = BASE_DIR / ".env"
    lines = env_path.read_text(encoding="utf-8-sig").splitlines() if env_path.exists() else []
    if lines:
        lines[0] = lines[0].lstrip("\ufeff")
    out: list[str] = []
    written = False
    for line in lines:
        if line.strip().startswith("GEMINI_API_KEY="):
            if not written:
                out.append(f"GEMINI_API_KEY={key}")
                written = True
            continue
        out.append(line)
    if not written:
        out.append(f"GEMINI_API_KEY={key}")
    env_path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    os.environ["GEMINI_API_KEY"] = key
    load_dotenv(env_path, override=True)
    return key


def save_chatgpt_key(key: str) -> str:
    """Persist ``CHATGPT_API_KEY`` to the project ``.env`` and reload it."""
    key = (key or "").strip()
    env_path = BASE_DIR / ".env"
    lines = env_path.read_text(encoding="utf-8-sig").splitlines() if env_path.exists() else []
    if lines:
        lines[0] = lines[0].lstrip("\ufeff")
    out: list[str] = []
    written = False
    for line in lines:
        if line.strip().startswith("CHATGPT_API_KEY="):
            if not written:
                out.append(f"CHATGPT_API_KEY={key}")
                written = True
            continue
        out.append(line)
    if not written:
        out.append(f"CHATGPT_API_KEY={key}")
    env_path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    os.environ["CHATGPT_API_KEY"] = key
    load_dotenv(env_path, override=True)
    return key

# Default Gemini model + a fallback chain tried in order when the configured
# model is unavailable.
# Newest supported Flash model (GA since July 2026) — the default for every
# Gemini request (Chat / Image / Audio). Deprecated 2.x Flash models are NOT
# used anywhere in the codebase.
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"

# All currently supported Gemini models (no deprecated names here).
SUPPORTED_GEMINI_MODELS = (
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
)

# Fallback chain tried in order when the selected model is unavailable.
MODEL_FALLBACKS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]

# Optional deployment override via the GEMINI_MODEL env var (.env). When the
# override is empty or is a deprecated/unsupported model, it is replaced by
# DEFAULT_GEMINI_MODEL so a stale .env value can never break the app.
_env_model = os.getenv("GEMINI_MODEL", "").strip()
DEFAULT_MODEL = _env_model if _env_model in SUPPORTED_GEMINI_MODELS else DEFAULT_GEMINI_MODEL

# Gemini API key — read from .env via python-dotenv. Empty value => demo mode.
DEFAULT_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# ChatGPT API key — optional, user-provided via Settings page.
CHATGPT_API_KEY = os.getenv("CHATGPT_API_KEY", "").strip()

# OpenAI API key — optional, user-provided via Settings page.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# Session cookie signing secret.
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me-car-service-ai-secret")

# OAuth sign-in — Google.
# Create credentials at https://console.cloud.google.com/apis/credentials (OAuth
# client ID, type "Web application"). Add the redirect URI below to the app's
# authorized redirect URIs. Empty client id => the Google button is inactive.
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/auth/google/callback").strip()

# OAuth sign-in — Apple (Sign in with Apple).
# Configure a Service ID at https://developer.apple.com/account/resources
# (enable "Sign in with Apple") and set its Return URL to the redirect URI below.
# Sign-in works via the validated id_token, so only the Service ID is required.
APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", "").strip()
APPLE_REDIRECT_URI = os.getenv(
    "APPLE_REDIRECT_URI", "http://127.0.0.1:8000/auth/apple/callback").strip()

# Language / i18n labels used by the UI (Arabic + English).
SUPPORTED_LANGUAGES = {
    "en": "English",
    "ar": "العربية",
}

VEHICLE_YEARS = list(range(2026, 1984, -1))

FUEL_TYPES = ["Petrol", "Diesel", "Electric", "Hybrid", "LPG/CNG"]
TRANSMISSIONS = ["Automatic", "Manual", "CVT", "Dual-Clutch"]

MANUFACTURERS = {
    "Audi": ["A3", "A4", "A6", "Q3", "Q5", "Q7", "e-tron"],
    "BMW": ["1 Series", "3 Series", "5 Series", "X1", "X3", "X5", "i4"],
    "Mercedes-Benz": ["A-Class", "C-Class", "E-Class", "GLC", "GLE", "EQC"],
    "Toyota": ["Corolla", "Camry", "RAV4", "Land Cruiser", "Yaris", "Prius", "Hilux"],
    "Honda": ["Civic", "Accord", "CR-V", "HR-V", "City", "Fit"],
    "Ford": ["Fiesta", "Focus", "Mustang", "Ranger", "Escape", "Explorer"],
    "Volkswagen": ["Golf", "Passat", "Tiguan", "Polo", "Touareg", "Arteon"],
    "Hyundai": ["i20", "i30", "Tucson", "Santa Fe", "Elantra", "Kona"],
    "Kia": ["Rio", "Ceed", "Sportage", "Sorento", "Picanto", "EV6"],
    "Nissan": ["Micra", "Qashqai", "X-Trail", "Leaf", "Altima"],
    "Renault": ["Clio", "Megane", "Captur", "Duster", "Arkana"],
    "Peugeot": ["208", "308", "3008", "5008", "2008"],
    "Chevrolet": ["Spark", "Cruze", "Malibu", "Trailblazer", "Equinox"],
    "Tesla": ["Model 3", "Model Y", "Model S", "Model X"],
    "Škoda": ["Fabia", "Octavia", "Superb", "Karoq", "Kodiaq"],
    "Mazda": ["2", "3", "6", "CX-3", "CX-5", "MX-5"],
    "Suzuki": ["Swift", "Baleno", "Vitara", "Jimny", "Ertiga"],
    "Volvo": ["S60", "S90", "XC40", "XC60", "XC90"],
    "Jaguar": ["XE", "XF", "F-PACE", "E-PACE", "I-PACE"],
    "Land Rover": ["Range Rover", "Discovery", "Defender", "Evoque"],
    "Fiat": ["500", "Panda", "Punto", "Tipo"],
    "Opel": ["Corsa", "Astra", "Insignia", "Mokka", "Grandland"],
    "Dacia": ["Sandero", "Duster", "Logan", "Jogger"],
    "Mini": ["Cooper", "Clubman", "Countryman"],
    "Lexus": ["UX", "NX", "RX", "ES", "LS"],
    "Seat": ["Ibiza", "Leon", "Arona", "Ateca", "Tarraco"],
    "Skoda": ["Fabia", "Octavia", "Superb", "Kodiaq", "Enyaq"],
}
