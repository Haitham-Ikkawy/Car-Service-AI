"""Vehicle component catalog used by the interactive parts map (My Garage).

Each entry powers the blueprint markers: static specifications shown instantly,
plus an optional AI-generated report fetched from the twin/parts endpoint.
"""
from __future__ import annotations

from typing import Any

# Component key -> { name, spec, issues, tip, lifespan, marker position (x,y in %) }
PARTS: dict[str, dict[str, Any]] = {
    "engine": {
        "name": "Engine",
        "spec": "Internal combustion unit — cylinders, pistons, valves, timing and lubrication system.",
        "issues": [
            "Rough idle or shaking when stationary",
            "Knocking / tapping noises under load",
            "Oil consumption between changes",
            "Overheating or coolant loss",
        ],
        "tip": "Change oil and filter on schedule and let the engine warm up before hard acceleration.",
        "lifespan": "300,000+ km with regular maintenance",
        "x": 23, "y": 52,
    },
    "battery": {
        "name": "Battery",
        "spec": "12V lead-acid or lithium battery supplying starting power and electronics.",
        "issues": [
            "Slow crank or no-start in cold weather",
            "Corroded terminals",
            "Voltage below 12.4 V at rest",
        ],
        "tip": "Clean terminals yearly and test the battery before winter.",
        "lifespan": "3–5 years",
        "x": 14, "y": 46,
    },
    "cooling": {
        "name": "Cooling System",
        "spec": "Radiator, water pump, thermostat, coolant and fans that keep the engine at temperature.",
        "issues": [
            "Engine temperature needle rising",
            "Coolant leaks under the car",
            "Weak or no cabin heat",
        ],
        "tip": "Flush coolant every 2 years and check the cap, hoses and radiator fins.",
        "lifespan": "Coolant: 2–4 years · Water pump: 100,000–160,000 km",
        "x": 6, "y": 74,
    },
    "brakes": {
        "name": "Brakes",
        "spec": "Discs, pads, calipers and fluid converting pedal pressure into stopping force.",
        "issues": [
            "Squealing or grinding when braking",
            "Soft or spongy pedal",
            "Car pulls to one side under braking",
        ],
        "tip": "Listen for a metallic squeal — the wear indicator is touching the disc.",
        "lifespan": "Pads: 30,000–60,000 km · Rotors: 2 pad sets",
        "x": 24, "y": 82,
    },
    "tires": {
        "name": "Tires",
        "spec": "Rubber contact patches with tread, sidewall and pressure rating for grip and comfort.",
        "issues": [
            "Uneven or rapid tread wear",
            "Vibration at highway speed",
            "Low pressure warning lamp",
        ],
        "tip": "Rotate tires every 10,000 km and check pressure monthly when cold.",
        "lifespan": "40,000–70,000 km (or 6 years max)",
        "x": 79, "y": 82,
    },
    "suspension": {
        "name": "Suspension",
        "spec": "Springs, shock absorbers, control arms and bushings isolating the body from the road.",
        "issues": [
            "Knocking over bumps",
            "Car sits low or nose dives",
            "Excessive bounce after a bump",
        ],
        "tip": "Push down on a corner — if it bounces more than twice, the shock may be worn.",
        "lifespan": "Shocks: 80,000–120,000 km",
        "x": 50, "y": 80,
    },
    "transmission": {
        "name": "Transmission",
        "spec": "Gearbox transferring engine power to the wheels — manual, automatic, CVT or dual-clutch.",
        "issues": [
            "Slipping or delayed engagement",
            "Gearbox whine or clunking",
            "Fluid leak / burnt smell",
        ],
        "tip": "Service automatic fluid on schedule; it is not 'lifetime' fluid in most cars.",
        "lifespan": "150,000–250,000 km with regular service",
        "x": 58, "y": 58,
    },
    "electrical": {
        "name": "Electrical",
        "spec": "Alternator, wiring harness, fuses, lights and body computers running every system.",
        "issues": [
            "Dimming lights or battery warning lamp",
            "Blown fuses or dead outlets",
            "Intermittent sensors / warning lamps",
        ],
        "tip": "A flickering interior light can point to a weak alternator or ground connection.",
        "lifespan": "Alternator: 150,000–250,000 km",
        "x": 72, "y": 44,
    },
}

MARKER_ORDER: list[str] = [
    "engine", "battery", "cooling", "brakes",
    "tires", "suspension", "transmission", "electrical",
]

DEFAULT_MARKER_STATE = {
    "engine": "ok", "battery": "ok", "cooling": "ok", "brakes": "warn",
    "tires": "ok", "suspension": "ok", "transmission": "ok", "electrical": "ok",
}


def part(key: str) -> dict[str, Any] | None:
    return PARTS.get(key)
