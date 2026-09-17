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
    "Acura": [
        "ILX",
        "TLX",
        "RDX",
        "MDX",
        "ZDX",
        "Integra",
        "NSX"
    ],
    "Alfa Romeo": [
        "Giulia",
        "Stelvio",
        "Tonale",
        "Giulietta",
        "Junior",
        "4C",
        "159",
        "Brera"
    ],
    "Aston Martin": [
        "Vantage",
        "DB12",
        "DBX",
        "DB11",
        "DBS",
        "Vanquish",
        "Valkyrie"
    ],
    "Audi": [
        "A3",
        "A4",
        "A6",
        "Q3",
        "Q5",
        "Q7",
        "e-tron",
        "A1",
        "A5",
        "A7",
        "A8",
        "Q2",
        "Q4 e-tron",
        "Q8",
        "Q8 e-tron",
        "Q6 e-tron",
        "TT",
        "R8",
        "e-tron GT"
    ],
    "Bentley": [
        "Continental GT",
        "Flying Spur",
        "Bentayga",
        "Mulsanne"
    ],
    "BMW": [
        "1 Series",
        "3 Series",
        "5 Series",
        "X1",
        "X3",
        "X5",
        "i4",
        "2 Series",
        "4 Series",
        "6 Series",
        "7 Series",
        "8 Series",
        "X2",
        "X4",
        "X6",
        "X7",
        "XM",
        "i3",
        "i8",
        "iX",
        "iX3",
        "M2",
        "M3",
        "M4",
        "M5",
        "M8",
        "i5",
        "i7",
        "iX1",
        "Z4"
    ],
    "Buick": [
        "Encore",
        "Envision",
        "LaCrosse",
        "Enclave",
        "Envista",
        "Regal",
        "Verano",
        "GL8"
    ],
    "Cadillac": [
        "CT4",
        "CT5",
        "XT4",
        "XT5",
        "Escalade",
        "XT6",
        "Lyriq",
        "Optiq",
        "Vistiq",
        "Celestiq",
        "CTS",
        "ATS"
    ],
    "Chevrolet": [
        "Spark",
        "Cruze",
        "Malibu",
        "Trailblazer",
        "Equinox",
        "Camaro",
        "Corvette",
        "Trax",
        "Blazer",
        "Traverse",
        "Tahoe",
        "Suburban",
        "Silverado",
        "Colorado",
        "Bolt",
        "Aveo",
        "Onix"
    ],
    "Chrysler": [
        "300",
        "Pacifica",
        "Voyager",
        "200"
    ],
    "Citroen": [
        "C1",
        "C3",
        "C4",
        "C5",
        "Berlingo",
        "C2",
        "C3 Aircross",
        "C4 Cactus",
        "C4 Picasso",
        "C5 Aircross",
        "C5 X",
        "C-Elysee",
        "Ami"
    ],
    "Dodge": [
        "Challenger",
        "Charger",
        "Durango",
        "Hornet",
        "Journey",
        "Dart",
        "Viper"
    ],
    "Ferrari": [
        "Roma",
        "SF90",
        "296",
        "812",
        "F8",
        "Purosangue",
        "12Cilindri",
        "Portofino",
        "488",
        "458 Italia"
    ],
    "Fiat": [
        "500",
        "Panda",
        "Punto",
        "Tipo",
        "600",
        "500X",
        "500L",
        "Doblo",
        "Ducato",
        "Fiorino",
        "Argo",
        "Cronos",
        "Pulse",
        "Fastback",
        "Topolino"
    ],
    "Ford": [
        "Fiesta",
        "Focus",
        "Mustang",
        "Ranger",
        "Escape",
        "Explorer",
        "Mustang Mach-E",
        "Fusion",
        "Taurus",
        "Edge",
        "Expedition",
        "Bronco",
        "Bronco Sport",
        "Maverick",
        "Everest",
        "Puma",
        "Kuga",
        "EcoSport",
        "F-150"
    ],
    "Genesis": [
        "G70",
        "G80",
        "G90",
        "GV70",
        "GV80",
        "GV60"
    ],
    "GMC": [
        "Terrain",
        "Acadia",
        "Yukon",
        "Sierra",
        "Hummer EV",
        "Canyon"
    ],
    "Honda": [
        "Civic",
        "Accord",
        "CR-V",
        "HR-V",
        "City",
        "Fit",
        "ZR-V",
        "Pilot",
        "Passport",
        "Ridgeline",
        "NSX",
        "Odyssey",
        "Amaze",
        "Brio",
        "WR-V",
        "BR-V",
        "Prologue"
    ],
    "Hyundai": [
        "i20",
        "i30",
        "Tucson",
        "Santa Fe",
        "Elantra",
        "Kona",
        "i10",
        "Sonata",
        "Accent",
        "Palisade",
        "Ioniq 5",
        "Ioniq 6",
        "Ioniq",
        "Venue",
        "Staria",
        "Santa Cruz",
        "Bayon",
        "Creta"
    ],
    "Infiniti": [
        "Q50",
        "Q60",
        "QX50",
        "QX60",
        "Q70",
        "QX30",
        "QX70",
        "QX80",
        "QX55"
    ],
    "Jaguar": [
        "XE",
        "XF",
        "F-PACE",
        "E-PACE",
        "I-PACE",
        "XJ",
        "F-Type"
    ],
    "Jeep": [
        "Renegade",
        "Compass",
        "Cherokee",
        "Wrangler",
        "Grand Cherokee",
        "Gladiator",
        "Wagoneer",
        "Grand Wagoneer",
        "Avenger",
        "Commander"
    ],
    "Kia": [
        "Rio",
        "Ceed",
        "Sportage",
        "Sorento",
        "Picanto",
        "EV6",
        "Forte",
        "K5",
        "Telluride",
        "Seltos",
        "EV9",
        "EV3",
        "EV5",
        "Soul",
        "Niro",
        "Carnival",
        "Stonic"
    ],
    "Lamborghini": [
        "Huracan",
        "Urus",
        "Revuelto",
        "Aventador",
        "Gallardo",
        "Temerario"
    ],
    "Land Rover": [
        "Range Rover",
        "Discovery",
        "Defender",
        "Evoque",
        "Discovery Sport",
        "Range Rover Sport",
        "Range Rover Velar"
    ],
    "Lexus": [
        "UX",
        "NX",
        "RX",
        "ES",
        "LS",
        "IS",
        "GS",
        "LC",
        "RC",
        "GX",
        "LX",
        "RZ",
        "LBX",
        "LM"
    ],
    "Lincoln": [
        "Corsair",
        "Aviator",
        "Navigator",
        "Continental",
        "Nautilus",
        "MKZ",
        "MKX"
    ],
    "Maserati": [
        "Ghibli",
        "Levante",
        "Grecale",
        "GranTurismo",
        "Quattroporte",
        "MC20",
        "GranCabrio"
    ],
    "Mazda": [
        "2",
        "3",
        "6",
        "CX-3",
        "CX-5",
        "MX-5",
        "CX-30",
        "CX-50",
        "CX-60",
        "CX-80",
        "CX-90",
        "CX-9",
        "BT-50",
        "RX-8",
        "CX-70"
    ],
    "McLaren": [
        "720S",
        "750S",
        "Artura",
        "GT",
        "570S",
        "P1",
        "Senna",
        "600LT",
        "765LT"
    ],
    "Mercedes-Benz": [
        "A-Class",
        "C-Class",
        "E-Class",
        "GLC",
        "GLE",
        "EQC",
        "B-Class",
        "S-Class",
        "CLA",
        "CLS",
        "CLE",
        "GLA",
        "GLB",
        "GLS",
        "G-Class",
        "EQA",
        "EQB",
        "EQE",
        "EQS",
        "V-Class"
    ],
    "Mitsubishi": [
        "Lancer",
        "Outlander",
        "ASX",
        "Pajero",
        "Eclipse Cross",
        "Triton",
        "Mirage",
        "Xpander",
        "Colt",
        "Montero Sport"
    ],
    "Nissan": [
        "Micra",
        "Qashqai",
        "X-Trail",
        "Leaf",
        "Altima",
        "Sentra",
        "Maxima",
        "GT-R",
        "Juke",
        "Pathfinder",
        "Patrol",
        "Ariya",
        "Navara",
        "Rogue",
        "Kicks",
        "Versa",
        "Armada",
        "Titan",
        "Z"
    ],
    "Opel": [
        "Corsa",
        "Astra",
        "Insignia",
        "Mokka",
        "Grandland",
        "Crossland",
        "Adam",
        "Zafira",
        "Combo",
        "Frontera"
    ],
    "Peugeot": [
        "208",
        "308",
        "3008",
        "5008",
        "2008",
        "108",
        "408",
        "508",
        "Rifter",
        "Partner",
        "Traveller"
    ],
    "Porsche": [
        "911",
        "Cayenne",
        "Macan",
        "Taycan",
        "Panamera",
        "718 Boxster",
        "718 Cayman",
        "Boxster",
        "Cayman"
    ],
    "Ram": [
        "1500",
        "2500",
        "3500",
        "Rampage",
        "ProMaster"
    ],
    "Renault": [
        "Clio",
        "Megane",
        "Captur",
        "Duster",
        "Arkana",
        "Twingo",
        "Austral",
        "Espace",
        "Scenic",
        "Koleos",
        "Kadjar",
        "Talisman",
        "Kangoo",
        "Kwid",
        "Triber",
        "Rafale"
    ],
    "Rolls-Royce": [
        "Ghost",
        "Phantom",
        "Cullinan",
        "Spectre"
    ],
    "Seat": [
        "Ibiza",
        "Leon",
        "Arona",
        "Ateca",
        "Tarraco",
        "Alhambra",
        "Toledo"
    ],
    "Skoda": [
        "Fabia",
        "Octavia",
        "Superb",
        "Karoq",
        "Kodiaq",
        "Enyaq",
        "Scala",
        "Kamiq",
        "Elroq",
        "Rapid"
    ],
    "Smart": [
        "ForTwo",
        "ForFour",
        "#1",
        "#3",
        "#5"
    ],
    "Subaru": [
        "Impreza",
        "Forester",
        "Outback",
        "XV",
        "WRX",
        "Legacy",
        "Ascent",
        "Crosstrek",
        "BRZ",
        "Solterra"
    ],
    "Suzuki": [
        "Swift",
        "Baleno",
        "Vitara",
        "Jimny",
        "Ertiga",
        "Celerio",
        "Ignis",
        "Alto",
        "Ciaz",
        "Fronx",
        "S-Cross",
        "XL7",
        "Grand Vitara"
    ],
    "Tesla": [
        "Model 3",
        "Model Y",
        "Model S",
        "Model X",
        "Cybertruck",
        "Roadster"
    ],
    "Toyota": [
        "Corolla",
        "Camry",
        "RAV4",
        "Land Cruiser",
        "Yaris",
        "Prius",
        "Hilux",
        "C-HR",
        "Highlander",
        "Land Cruiser Prado",
        "Fortuner",
        "Supra",
        "bZ4X",
        "Crown",
        "Sequoia",
        "Tacoma",
        "Tundra",
        "Sienna",
        "Alphard",
        "Avanza",
        "Innova",
        "Vitz",
        "GR Yaris",
        "GR86",
        "Rush"
    ],
    "Volkswagen": [
        "Golf",
        "Passat",
        "Tiguan",
        "Polo",
        "Touareg",
        "Arteon",
        "T-Roc",
        "T-Cross",
        "Taigo",
        "Jetta",
        "Atlas",
        "ID.3",
        "ID.4",
        "ID.7",
        "ID. Buzz",
        "Touran",
        "Sharan",
        "Amarok",
        "Caddy",
        "ID.5"
    ],
    "Volvo": [
        "S60",
        "S90",
        "XC40",
        "XC60",
        "XC90",
        "V60",
        "V90",
        "EX30",
        "EX90",
        "EX40",
        "EC40",
        "C40"
    ],
    "Dacia": [
        "Sandero",
        "Duster",
        "Logan",
        "Jogger",
        "Spring",
        "Bigster"
    ],
    "Mini": [
        "Cooper",
        "Clubman",
        "Countryman",
        "Aceman"
    ],
    "Isuzu": [
        "D-Max",
        "MU-X",
        "Trooper"
    ],
    "Daihatsu": [
        "Terios",
        "Sirion",
        "Mira",
        "Move",
        "Tanto",
        "Rocky",
        "Copen",
        "Ayla",
        "Sigra"
    ],
    "DS": [
        "DS 3",
        "DS 4",
        "DS 7",
        "DS 9"
    ],
    "Lancia": [
        "Ypsilon",
        "Delta",
        "Thema",
        "Musa"
    ],
    "Bugatti": [
        "Veyron",
        "Chiron",
        "Divo",
        "Tourbillon"
    ],
    "Lotus": [
        "Elise",
        "Exige",
        "Evora",
        "Emira",
        "Eletre",
        "Emeya",
        "Evija"
    ],
    "Polestar": [
        "1",
        "2",
        "3",
        "4"
    ],
    "Saab": [
        "9-3",
        "9-5",
        "900",
        "9000"
    ],
    "Rivian": [
        "R1T",
        "R1S",
        "R2"
    ],
    "Lucid": [
        "Air",
        "Gravity"
    ],
    "Daewoo": [
        "Lanos",
        "Nubira",
        "Leganza",
        "Lacetti",
        "Kalos",
        "Matiz"
    ],
    "BYD": [
        "Atto 3",
        "Dolphin",
        "Seal",
        "Seagull",
        "Han",
        "Tang",
        "Qin",
        "Song Plus",
        "Seal U",
        "Shark"
    ],
    "Geely": [
        "Emgrand",
        "Coolray",
        "Atlas",
        "Monjaro",
        "Okavango",
        "Tugella",
        "Geometry C"
    ],
    "Chery": [
        "Tiggo 7",
        "Tiggo 8",
        "Tiggo 9",
        "Arrizo 5",
        "Arrizo 8",
        "QQ",
        "Tiggo 4",
        "Arrizo 6"
    ],
    "Changan": [
        "CS35",
        "CS55",
        "CS75",
        "CS95",
        "UNI-T",
        "UNI-K",
        "UNI-V",
        "Alsvin",
        "Eado"
    ],
    "Great Wall": [
        "Wingle",
        "Voleex C30",
        "Voleex C50",
        "Poer"
    ],
    "Haval": [
        "H2",
        "H6",
        "H9",
        "Jolion",
        "H5",
        "Dargo"
    ],
    "Zeekr": [
        "001",
        "007",
        "009",
        "X",
        "7X"
    ],
    "NIO": [
        "ET5",
        "ET7",
        "ES6",
        "ES8",
        "EC6",
        "EC7"
    ],
    "XPeng": [
        "P7",
        "P5",
        "G6",
        "G9",
        "X9"
    ],
    "Hongqi": [
        "H5",
        "H9",
        "HS5",
        "HS7",
        "E-HS9"
    ],
    "Li Auto": [
        "L6",
        "L7",
        "L8",
        "L9",
        "Mega",
        "One"
    ],
    "Leapmotor": [
        "T03",
        "C10",
        "C11",
        "C16",
        "B10"
    ],
    "GAC": [
        "GS3",
        "GS4",
        "GS8",
        "Empow",
        "GN6",
        "GN8"
    ],
    "MG": [
        "3",
        "4",
        "5",
        "6",
        "7",
        "HS",
        "ZS",
        "Cyberster",
        "Marvel R"
    ],
    "JAC": [
        "J7",
        "JS4",
        "S3",
        "T6",
        "T8",
        "T9"
    ],
    "BAIC": [
        "BJ40",
        "BJ80",
        "X35",
        "X55"
    ],
    "FAW": [
        "Besturn B50",
        "Besturn B70",
        "Besturn X40",
        "Besturn X80"
    ],
    "Dongfeng": [
        "Aeolus A60",
        "Aeolus Yixuan",
        "Fengon 580",
        "Fengon 500"
    ],
    "Foton": [
        "Tunland",
        "Sauvana",
        "Toano"
    ],
    "Tata": [
        "Nexon",
        "Harrier",
        "Safari",
        "Punch",
        "Tiago",
        "Tigor",
        "Altroz",
        "Curvv",
        "Nano",
        "Indica"
    ],
    "Mahindra": [
        "Scorpio",
        "Thar",
        "XUV700",
        "XUV300",
        "XUV 3XO",
        "Bolero",
        "Marazzo",
        "BE 6",
        "XEV 9e",
        "XUV400"
    ],
    "Proton": [
        "Saga",
        "Persona",
        "Iriz",
        "X50",
        "X70",
        "S70",
        "Exora",
        "X90"
    ],
    "Perodua": [
        "Myvi",
        "Axia",
        "Bezza",
        "Alza",
        "Ativa",
        "Aruz"
    ],
    "VinFast": [
        "VF 3",
        "VF 5",
        "VF 6",
        "VF 7",
        "VF 8",
        "VF 9",
        "Lux A2.0",
        "Lux SA2.0"
    ],
    "Cupra": [
        "Formentor",
        "Born",
        "Tavascan",
        "Terramar",
        "Leon",
        "Ateca"
    ],
    "Abarth": [
        "595",
        "695",
        "124 Spider",
        "500e"
    ]
}
