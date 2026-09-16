"""Arabic dialect detection and automotive terminology mapping.

Automatically detects Arabic dialect from user input and maps local automotive
terminology to canonical technical concepts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class DialectResult:
    """Result of dialect detection."""
    language: str = "en"
    dialect: str = ""
    dialect_confidence: float = 0.0
    detected_terms: list[str] = field(default_factory=list)
    canonical_concepts: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Arabic dialect detection patterns
# ---------------------------------------------------------------------------

# Lebanese/Syrian markers (Levantine)
_LEVANTINE_MARKERS = [
    r"عم\s+ي(?:برد|يشتغل|يمشي|يسخن|يعمل|يطلع)",  # عم يبرد = is cooling
    r"ما\s+عم",  # ما عم = not currently
    r"مش\s+عم",  # مش عم = not currently
    r"ヘه",  # هه = particle
    r"هيك",  # هيك = like this
    r"هلا",  # هلا = now
    r"بكرا",  # بكرا = tomorrow
    r"صار",  # صار = became/happened
    r"عملي",  # عميلي = my customer
    r"خبط",  # خبط = hit/crash
    r"دقّ",  # دقّ = knock/tap
    r"طقّ",  # طقّ = click/knock
    r"رجّ",  # رجّ = vibrate
    r"طقطقة",  # طقطقة = clicking sound
    r" Scorpio",  # Scorpio = Lebanese expression
]

# Saudi/Gulf markers
_GULF_MARKERS = [
    r"الحين",  # الحين = now
    r"جنب",  # جنب = next to
    r"يمكن",  # يمكن = maybe
    r" Dummy",  # Dummy = Gulf expression
    r"عشان",  # عشان = because
    r"عشان كذا",  # عشان كذا = because of this
    r"_dependencies",  # dependencies = Gulf expression
    r"يمدي",  # يمدي = it's possible
    r"ما يمدي",  # ما يمدي = not possible
    r" MOS",  # MOS = Gulf expression
    r"قايل",  # قايل = said
    r"gae",  # gae = sitting (Gulf)
]

# Egyptian markers
_EGYPTIAN_MARKERS = [
    r" Memphis",  # Memphis = Egyptian expression
    r" maps",  # maps = Egyptian expression
    r"عملي",  # عميلي = my customer
    r"أوي",  # أوي = very
    r"جداً",  # جداً = very
    r"mps",  # mps = Egyptian expression
    r"يعني",  # يعني = means
    r"蜗",  #蜗 = particle
    r"淼",  # 淼 = particle
    r" fender",  # fender = Egyptian expression
]

# Iraqi markers
_IRAQI_MARKERS = [
    r"هسة",  # هسة = now
    r"_shaku maku",  # shaku maku = what's up
    r"پي",  # پي = particle
    r"منور",  # منور = lit up
    r"jin",  # jin = very
    r"eh",  # eh = what
]

# Moroccan/Algerian/Tunisian (Maghreb) markers
_MAGHREB_MARKERS = [
    r"شحال",  # شحال = how much
    r"واش",  # واش = what
    r"بزاف",  # بزاف = a lot
    r"دابا",  # دابا = now
    r"aze",  # aze = Maghreb expression
    r"taw",  # taw = now (Tunisian)
    r"hakka",  # hakka = like this (Tunisian)
]

# Yemeni markers
_YEMENI_MARKERS = [
    r"大战",  # 大战 = now
    r"شلونك",  # شلونك = how are you
    r" وش",  # وش = what
]


def _count_matches(text: str, patterns: list[str]) -> int:
    """Count how many patterns match in the text."""
    count = 0
    for pat in patterns:
        try:
            if re.search(pat, text, re.IGNORECASE):
                count += 1
        except re.error:
            continue
    return count


def detect_arabic_dialect(text: str) -> tuple[str, float]:
    """Detect the Arabic dialect from text.

    Returns (dialect, confidence) where confidence is 0.0-1.0.
    """
    if not text:
        return ("", 0.0)

    # Normalize text
    text_lower = text.lower().strip()

    # Count matches for each dialect
    scores = {
        "Lebanese": _count_matches(text_lower, _LEVANTINE_MARKERS),
        "Syrian": _count_matches(text_lower, _LEVANTINE_MARKERS) * 0.8,  # Shared with Lebanese
        "Saudi": _count_matches(text_lower, _GULF_MARKERS),
        "Emirati": _count_matches(text_lower, _GULF_MARKERS) * 0.7,  # Shared with Saudi
        "Kuwaiti": _count_matches(text_lower, _GULF_MARKERS) * 0.7,
        "Qatari": _count_matches(text_lower, _GULF_MARKERS) * 0.7,
        "Bahraini": _count_matches(text_lower, _GULF_MARKERS) * 0.7,
        "Omani": _count_matches(text_lower, _GULF_MARKERS) * 0.6,
        "Egyptian": _count_matches(text_lower, _EGYPTIAN_MARKERS),
        "Iraqi": _count_matches(text_lower, _IRAQI_MARKERS),
        "Moroccan": _count_matches(text_lower, _MAGHREB_MARKERS),
        "Algerian": _count_matches(text_lower, _MAGHREB_MARKERS) * 0.9,
        "Tunisian": _count_matches(text_lower, _MAGHREB_MARKERS) * 0.8,
        "Libyan": _count_matches(text_lower, _MAGHREB_MARKERS) * 0.6,
        "Sudanese": _count_matches(text_lower, _LEVANTINE_MARKERS) * 0.4,
        "Jordanian": _count_matches(text_lower, _LEVANTINE_MARKERS) * 0.9,
        "Palestinian": _count_matches(text_lower, _LEVANTINE_MARKERS) * 0.85,
        "Yemeni": _count_matches(text_lower, _YEMENI_MARKERS),
    }

    # Find the best match
    if not scores:
        return ("", 0.0)

    max_score = max(scores.values())
    if max_score == 0:
        # No dialect markers found - use neutral Arabic
        return ("Arabic", 0.3)

    best_dialect = max(scores, key=scores.get)

    # Calculate confidence based on match count
    # More matches = higher confidence, but cap at 0.95
    total_matches = sum(1 for v in scores.values() if v > 0)
    if total_matches > 1:
        # Multiple dialects detected - lower confidence
        confidence = min(0.6, max_score * 0.15)
    else:
        confidence = min(0.95, max_score * 0.2 + 0.4)

    return (best_dialect, confidence)


# ---------------------------------------------------------------------------
# Automotive terminology mapping
# ---------------------------------------------------------------------------

@dataclass
class AutomotiveTerm:
    """A local automotive term mapped to canonical concept."""
    local_term: str
    canonical_id: str
    canonical_en: str
    arabic_standard: str
    category: str
    regions: list[str] = field(default_factory=list)
    confidence: float = 1.0


# Comprehensive automotive terminology database
# Format: canonical_id -> list of local terms with dialect info
AUTOMOTIVE_TERMS_DB: dict[str, list[AutomotiveTerm]] = {
    # Steering
    "steering_wheel": [
        AutomotiveTerm("السكان", "steering_wheel", "Steering Wheel", "عجلة القيادة", "steering", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("الدركسون", "steering_wheel", "Steering Wheel", "عجلة القيادة", "steering", ["Lebanese", "Syrian", "Jordanian", "Palestinian", "Egyptian"]),
        AutomotiveTerm("الطارة", "steering_wheel", "Steering Wheel", "عجلة القيادة", "steering", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("المقود", "steering_wheel", "Steering Wheel", "عجلة القيادة", "steering", ["Saudi", "Gulf", "Egyptian"]),
        AutomotiveTerm("عجلة السواقة", "steering_wheel", "Steering Wheel", "عجلة القيادة", "steering", ["Iraqi"]),
    ],
    # Track Rod End / Tie Rod End
    "track_rod_end": [
        AutomotiveTerm("بيضة السيارة", "track_rod_end", "Track Rod End", "نهاية ذراع التوجيه", "steering", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("بيضة الدركسون", "track_rod_end", "Track Rod End", "نهاية ذراع التوجيه", "steering", ["Lebanese", "Syrian"]),
        AutomotiveTerm("نهاية الدركسون", "track_rod_end", "Track Rod End", "نهاية ذراع التوجيه", "steering", ["Lebanese", "Syrian", "Jordanian"]),
        AutomotiveTerm("كTableWidgetItem", "track_rod_end", "Track Rod End", "نهاية ذراع التوجيه", "steering", ["Gulf"]),
    ],
    # AC Compressor
    "ac_compressor": [
        AutomotiveTerm("كمبروسر", "ac_compressor", "AC Compressor", "ضاغط المكيف", "ac", ["Lebanese", "Syrian", "Jordanian", "Palestinian", "Egyptian"]),
        AutomotiveTerm("كمبريسور", "ac_compressor", "AC Compressor", "ضاغط المكيف", "ac", ["Saudi", "Gulf"]),
        AutomotiveTerm("ضاغط المكيف", "ac_compressor", "AC Compressor", "ضاغط المكيف", "ac", ["Saudi", "Gulf", "Egyptian"]),
    ],
    # AC Refrigerant
    "ac_refrigerant": [
        AutomotiveTerm("فريون", "ac_refrigerant", "AC Refrigerant", "غاز التبريد", "ac", ["Lebanese", "Syrian", "Jordanian", "Palestinian", "Egyptian", "Saudi", "Gulf"]),
        AutomotiveTerm("غاز المكيف", "ac_refrigerant", "AC Refrigerant", "غاز التبريد", "ac", ["Saudi", "Gulf"]),
        AutomotiveTerm(" coolant", "ac_refrigerant", "AC Refrigerant", "غاز التبريد", "ac", ["Iraqi"]),
    ],
    # Engine
    "engine": [
        AutomotiveTerm("الموتور", "engine", "Engine", "المحرك", "engine", ["Lebanese", "Syrian", "Jordanian", "Palestinian", "Egyptian"]),
        AutomotiveTerm("المحرك", "engine", "Engine", "المحرك", "engine", ["Saudi", "Gulf", "Iraqi"]),
        AutomotiveTerm("الماتور", "engine", "Engine", "المحرك", "engine", ["Lebanese", "Syrian", "Egyptian"]),
    ],
    # Battery
    "battery": [
        AutomotiveTerm("البطارية", "battery", "Battery", "البطارية", "battery", ["Lebanese", "Syrian", "Jordanian", "Palestinian", "Egyptian", "Saudi", "Gulf"]),
        AutomotiveTerm("البطاريه", "battery", "Battery", "البطارية", "battery", ["Lebanese", "Syrian"]),
        AutomotiveTerm("الكوشة", "battery", "Battery", "البطارية", "battery", ["Egyptian"]),
    ],
    # Brakes
    "brakes": [
        AutomotiveTerm("المكابح", "brakes", "Brakes", "المكابحات", "brakes", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("المكابحات", "brakes", "Brakes", "المكابحات", "brakes", ["Saudi", "Gulf", "Egyptian"]),
        AutomotiveTerm("الفحم", "brakes", "Brake Pads", "وسائد المكابح", "brakes", ["Lebanese", "Syrian", "Jordanian"]),
    ],
    # Brake pads
    "brake_pads": [
        AutomotiveTerm("فحم المكابح", "brake_pads", "Brake Pads", "وسائد المكابح", "brakes", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("فحمات", "brake_pads", "Brake Pads", "وسائد المكابح", "brakes", ["Saudi", "Gulf"]),
        AutomotiveTerm("الفلب", "brake_pads", "Brake Pads", "وسائد المكابح", "brakes", ["Egyptian"]),
    ],
    # Clutch
    "clutch": [
        AutomotiveTerm("القير", "clutch", "Clutch", "القابض", "transmission", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("القابض", "clutch", "Clutch", "القابض", "transmission", ["Saudi", "Gulf", "Egyptian"]),
        AutomotiveTerm("الكلاutch", "clutch", "Clutch", "القابض", "transmission", ["Lebanese", "Syrian"]),
    ],
    # Transmission / Gearbox
    "transmission": [
        AutomotiveTerm("القير", "transmission", "Transmission/Gearbox", "ناقل الحركة", "transmission", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("الجير", "transmission", "Transmission/Gearbox", "ناقل الحركة", "transmission", ["Saudi", "Gulf", "Egyptian"]),
        AutomotiveTerm("ناقل الحركة", "transmission", "Transmission/Gearbox", "ناقل الحركة", "transmission", ["Saudi", "Gulf"]),
    ],
    # Radiator
    "radiator": [
        AutomotiveTerm("الرادياتير", "radiator", "Radiator", "المبرد", "cooling", ["Lebanese", "Syrian", "Jordanian", "Palestinian", "Egyptian"]),
        AutomotiveTerm("المبرد", "radiator", "Radiator", "المبرد", "cooling", ["Saudi", "Gulf"]),
        AutomotiveTerm("الرادياتور", "radiator", "Radiator", "المبرد", "cooling", ["Iraqi"]),
    ],
    # Spark plugs
    "spark_plugs": [
        AutomotiveTerm("شمعات", "spark_plugs", "Spark Plugs", "شمعات الإشعال", "engine", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("الشمعات", "spark_plugs", "Spark Plugs", "شمعات الإشعال", "engine", ["Saudi", "Gulf", "Egyptian"]),
        AutomotiveTerm("كانشات", "spark_plugs", "Spark Plugs", "شمعات الإشعال", "engine", ["Egyptian"]),
    ],
    # Oil filter
    "oil_filter": [
        AutomotiveTerm("فلتر الزيت", "oil_filter", "Oil Filter", "مرشح الزيت", "engine", ["Lebanese", "Syrian", "Jordanian", "Palestinian", "Saudi", "Gulf"]),
        AutomotiveTerm("فلتة الزيت", "oil_filter", "Oil Filter", "مرشح الزيت", "engine", ["Egyptian"]),
    ],
    # Air filter
    "air_filter": [
        AutomotiveTerm("فلتر الهوا", "air_filter", "Air Filter", "مرشح الهواء", "engine", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("فلتر الهواء", "air_filter", "Air Filter", "مرشح الهواء", "engine", ["Saudi", "Gulf", "Egyptian"]),
    ],
    # Alternator
    "alternator": [
        AutomotiveTerm("الalternator", "alternator", "Alternator", "المولد", "electrical", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("المولد", "alternator", "Alternator", "المولد", "electrical", ["Saudi", "Gulf", "Egyptian"]),
        AutomotiveTerm("الدينمو", "alternator", "Alternator", "المولد", "electrical", ["Egyptian"]),
    ],
    # Starter motor
    "starter_motor": [
        AutomotiveTerm("الستاندر", "starter_motor", "Starter Motor", "محرك التشغيل", "starting", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("محرك التشغيل", "starter_motor", "Starter Motor", "محرك التشغيل", "starting", ["Saudi", "Gulf"]),
        AutomotiveTerm("الstarter", "starter_motor", "Starter Motor", "محرك التشغيل", "starting", ["Egyptian"]),
    ],
    # Shock absorbers
    "shock_absorbers": [
        AutomotiveTerm("الم mountings", "shock_absorbers", "Shock Absorbers", "ممتصات الصدمات", "suspension", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("ممتصات الصدمات", "shock_absorbers", "Shock Absorbers", "ممتصات الصدمات", "suspension", ["Saudi", "Gulf"]),
        AutomotiveTerm("الشوك", "shock_absorbers", "Shock Absorbers", "ممتصات الصدمات", "suspension", ["Egyptian"]),
    ],
    # Tires
    "tires": [
        AutomotiveTerm("الكاوتش", "tires", "Tires", "الإطارات", "wheels", ["Lebanese", "Syrian", "Jordanian", "Palestinian", "Egyptian"]),
        AutomotiveTerm("الإطارات", "tires", "Tires", "الإطارات", "wheels", ["Saudi", "Gulf"]),
        AutomotiveTerm("البلاك", "tires", "Tires", "الإطارات", "wheels", ["Iraqi"]),
    ],
    # Wheel alignment
    "wheel_alignment": [
        AutomotiveTerm("الباص", "wheel_alignment", "Wheel Alignment", "محاذاة العجلات", "wheels", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("المحاذاة", "wheel_alignment", "Wheel Alignment", "محاذاة العجلات", "wheels", ["Saudi", "Gulf"]),
        AutomotiveTerm("الفحص", "wheel_alignment", "Wheel Alignment", "محاذاة العجلات", "wheels", ["Egyptian"]),
    ],
    # Lights
    "lights": [
        AutomotiveTerm("الانوار", "lights", "Lights", "المصابيح", "electrical", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("المصابيح", "lights", "Lights", "المصابيح", "electrical", ["Saudi", "Gulf", "Egyptian"]),
    ],
    # Sensors
    "sensors": [
        AutomotiveTerm("ال senors", "sensors", "Sensors", "مستشعرات", "electrical", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("الحسّاسات", "sensors", "Sensors", "مستشعرات", "electrical", ["Saudi", "Gulf"]),
        AutomotiveTerm("السوندات", "sensors", "Sensors", "مستشعرات", "electrical", ["Egyptian"]),
    ],
    # Exhaust
    "exhaust": [
        AutomotiveTerm("العادم", "exhaust", "Exhaust", "نظام العادم", "exhaust", ["Lebanese", "Syrian", "Jordanian", "Palestinian", "Saudi", "Gulf"]),
        AutomotiveTerm("المuffled", "exhaust", "Exhaust", "نظام العادم", "exhaust", ["Egyptian"]),
    ],
    # Fuel pump
    "fuel_pump": [
        AutomotiveTerm("طرمبة البنزين", "fuel_pump", "Fuel Pump", "مضخة الوقود", "fuel", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("مضخة الوقود", "fuel_pump", "Fuel Pump", "مضخة الوقود", "fuel", ["Saudi", "Gulf"]),
        AutomotiveTerm("طرمبة البنزين", "fuel_pump", "Fuel Pump", "مضخة الوقود", "fuel", ["Egyptian"]),
    ],
    # Wipers
    "wipers": [
        AutomotiveTerm("المساحات", "wipers", "Wipers", "مساحات الزجاج", "body", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("مساحات الزجاج", "wipers", "Wipers", "مساحات الزجاج", "body", ["Saudi", "Gulf", "Egyptian"]),
    ],
    # Horn
    "horn": [
        AutomotiveTerm("البوق", "horn", "Horn", "البوق", "electrical", ["Lebanese", "Syrian", "Jordanian", "Palestinian", "Saudi", "Gulf"]),
        AutomotiveTerm("الز nhorn", "horn", "Horn", "البوق", "electrical", ["Egyptian"]),
    ],
    # Coolant
    "coolant": [
        AutomotiveTerm("المي", "coolant", "Coolant", "سائل التبريد", "cooling", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm(" مي المكينه", "coolant", "Coolant", "سائل التبريد", "cooling", ["Lebanese", "Syrian"]),
        AutomotiveTerm("سائل التبريد", "coolant", "Coolant", "سائل التبريد", "cooling", ["Saudi", "Gulf", "Egyptian"]),
    ],
    # AC
    "ac_system": [
        AutomotiveTerm("المكيف", "ac_system", "AC System", "نظام التكييف", "ac", ["Lebanese", "Syrian", "Jordanian", "Palestinian"]),
        AutomotiveTerm("التكييف", "ac_system", "AC System", "نظام التكييف", "ac", ["Saudi", "Gulf", "Egyptian"]),
        AutomotiveTerm("ال(spac)", "ac_system", "AC System", "نظام التكييف", "ac", ["Iraqi"]),
    ],
}


def normalize_arabic_text(text: str) -> str:
    """Normalize Arabic text for better matching."""
    if not text:
        return ""
    # Remove diacritics
    text = re.sub(r"[\u0617-\u061A\u064B-\u0652]", "", text)
    # Normalize alef variants
    text = re.sub(r"[إأآا]", "ا", text)
    # Normalize ta marbuta
    text = re.sub(r"ة", "ه", text)
    # Normalize ya
    text = re.sub(r"ى", "ي", text)
    return text.strip()


def find_automotive_terms(text: str, dialect: str = "") -> list[dict]:
    """Find automotive terms in text and return canonical mappings.

    Args:
        text: User input text (Arabic)
        dialect: Detected dialect for confidence boosting

    Returns:
        List of found terms with local and canonical info
    """
    if not text:
        return []

    normalized = normalize_arabic_text(text.lower())
    found_terms = []

    for canonical_id, term_list in AUTOMOTIVE_TERMS_DB.items():
        for term in term_list:
            term_normalized = normalize_arabic_text(term.local_term.lower())
            if term_normalized in normalized or normalized in term_normalized:
                confidence = term.confidence
                # Boost confidence if dialect matches
                if dialect and dialect in term.regions:
                    confidence = min(1.0, confidence + 0.1)

                found_terms.append({
                    "canonical_id": canonical_id,
                    "canonical_en": term.canonical_en,
                    "arabic_standard": term.arabic_standard,
                    "local_term": term.local_term,
                    "category": term.category,
                    "confidence": confidence,
                })
                break  # Found one match for this canonical_id

    return found_terms


def detect_language_and_dialect(text: str) -> DialectResult:
    """Full language and dialect detection pipeline.

    Args:
        text: User input text

    Returns:
        DialectResult with language, dialect, confidence, and found terms
    """
    if not text:
        return DialectResult(language="en")

    # Check if Arabic
    arabic_chars = len(re.findall(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]", text))
    total_chars = len(text.strip())

    if total_chars == 0:
        return DialectResult(language="en")

    arabic_ratio = arabic_chars / total_chars

    if arabic_ratio < 0.3:
        # Mostly non-Arabic
        return DialectResult(language="en")

    # Detect dialect
    dialect, confidence = detect_arabic_dialect(text)

    # Find automotive terms
    terms = find_automotive_terms(text, dialect)
    detected_terms = [t["local_term"] for t in terms]
    canonical_concepts = [
        {
            "id": t["canonical_id"],
            "en": t["canonical_en"],
            "ar": t["arabic_standard"],
            "local": t["local_term"],
            "category": t["category"],
        }
        for t in terms
    ]

    return DialectResult(
        language="ar",
        dialect=dialect or "Arabic",
        dialect_confidence=confidence,
        detected_terms=detected_terms,
        canonical_concepts=canonical_concepts,
    )
