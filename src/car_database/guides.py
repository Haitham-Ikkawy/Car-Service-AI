"""Static DIY repair-guide catalog powering the Repair Guide pages.

Each guide is fully self-contained (steps, tools, parts, tips) so the pages
render without an AI call; an optional AI summary can be added later.
"""
from __future__ import annotations

from typing import Any

Guide = dict[str, Any]

CATEGORIES: list[str] = ["Engine", "Brakes", "Battery & Electrical", "Tires", "Cooling"]

GUIDES: list[Guide] = [
    {
        "slug": "engine-oil-change",
        "title": "Engine Oil & Filter Change",
        "category": "Engine",
        "difficulty": "Easy",
        "time": 45,
        "summary": "The most important routine service — fresh oil keeps the engine protected.",
        "steps": [
            {"title": "Warm up and lift", "text": "Drive the car for 5 minutes so the oil drains easily, then park on level ground and raise the car safely with jack stands."},
            {"title": "Drain the old oil", "text": "Remove the oil filler cap and the drain plug. Let the oil drain completely into a pan, then replace the drain plug with a new crush washer."},
            {"title": "Swap the filter", "text": "Remove the old oil filter with a filter wrench. Lubricate the new filter's gasket with a little fresh oil and tighten it by hand, then 3/4 turn."},
            {"title": "Refill", "text": "Add the correct grade and amount of fresh oil. Run the engine briefly, check for leaks, then re-check the level after a minute."},
            {"title": "Reset and log", "text": "Reset the service reminder, record the mileage in your maintenance log and dispose of the old oil at a recycling point."},
        ],
        "tools": ["Oil filter wrench", "Socket set", "Jack and stands", "Drain pan", "Funnel"],
        "parts": ["Engine oil", "Oil filter", "Drain plug washer"],
        "tips": "Never over-tighten the drain plug or filter — the pan threads strip easily.",
    },
    {
        "slug": "battery-replacement",
        "title": "Battery Replacement",
        "category": "Battery & Electrical",
        "difficulty": "Easy",
        "time": 20,
        "summary": "Swap a failing battery safely and avoid losing any vehicle settings.",
        "steps": [
            {"title": "Safety first", "text": "Switch the ignition off, remove metal jewelry and disconnect the negative (-) terminal first, then the positive (+)."},
            {"title": "Release the clamp", "text": "Remove the battery hold-down clamp or bracket and lift the battery straight out using the handle."},
            {"title": "Clean and install", "text": "Clean the tray and terminals. Install the new battery, tighten the clamp, and connect positive (+) first, then negative (-)."},
            {"title": "Verify", "text": "Start the car and confirm the battery warning lamp goes out. Reset the clock and radio presets if needed."},
        ],
        "tools": ["10 mm socket or wrench", "Battery terminal cleaner", "Gloves"],
        "parts": ["New battery (correct group size)"],
        "tips": "Keep a memory-saver plugged into the OBD port if you want to preserve settings.",
    },
    {
        "slug": "brake-pad-replacement",
        "title": "Brake Pad Replacement",
        "category": "Brakes",
        "difficulty": "Medium",
        "time": 90,
        "summary": "Replace worn front brake pads when the wear indicator starts squealing.",
        "steps": [
            {"title": "Remove the wheel", "text": "Loosen the lug nuts while the car is on the ground, lift and support it on stands, then remove the wheel."},
            {"title": "Retract the piston", "text": "Remove the caliper pins and lift the caliper off the rotor. Use a clamp or tool to push the caliper piston back into its bore."},
            {"title": "Fit new pads", "text": "Install new pads in the caliper carrier, apply brake grease to the contact points and re-fit the caliper."},
            {"title": "Bed in", "text": "Refit the wheel, pump the pedal to seat the pads, then do 8–10 gentle stops to bed them in. Do not drive hard for the first 200 km."},
        ],
        "tools": ["Jack and stands", "Caliper tool or clamp", "Socket set", "Brake grease", "Lug wrench"],
        "parts": ["Brake pads", "Brake grease", "Optional: new caliper pins"],
        "tips": "If the rotor has a deep lip or the pedal pulses, machine or replace the rotors too.",
    },
    {
        "slug": "air-filter-replacement",
        "title": "Air Filter Replacement",
        "category": "Engine",
        "difficulty": "Easy",
        "time": 15,
        "summary": "A clean engine air filter improves response, economy and engine protection.",
        "steps": [
            {"title": "Locate the box", "text": "Find the rectangular air filter housing near the engine intake and open the clips or undo the screws."},
            {"title": "Inspect", "text": "Lift the old filter out and hold it to the light. If it is dirty or clogged, replace it; tap loose dust out if it is only lightly soiled."},
            {"title": "Install", "text": "Fit the new filter in the same orientation, re-seat the lid and close the clips until they click."},
        ],
        "tools": ["Phillips screwdriver (optional)"],
        "parts": ["Engine air filter"],
        "tips": "Replace it every 15,000–30,000 km, or sooner in dusty conditions.",
    },
    {
        "slug": "coolant-flush",
        "title": "Coolant Flush",
        "category": "Cooling",
        "difficulty": "Medium",
        "time": 60,
        "summary": "Fresh coolant prevents corrosion, overheating and winter freezing.",
        "steps": [
            {"title": "Cold engine only", "text": "Never open the coolant system when hot. Work on a cold engine and place a pan under the radiator drain."},
            {"title": "Drain", "text": "Open the drain valve or remove the lower hose clamp, drain the old coolant, then close the valve."},
            {"title": "Flush", "text": "Fill with clean water, run the engine to temperature, drain again, and repeat until the water runs clear."},
            {"title": "Refill", "text": "Refill with the correct coolant-to-water mix, run the engine with the heater on, and top up the reservoir once the thermostat opens."},
        ],
        "tools": ["Drain pan", "Hose", "Funnel", "Gloves", "Rags"],
        "parts": ["Coolant (correct spec)", "Distilled water"],
        "tips": "Always use the coolant spec in your owner's manual — mixing incompatible types can damage seals.",
    },
    {
        "slug": "tire-rotation",
        "title": "Tire Rotation",
        "category": "Tires",
        "difficulty": "Easy",
        "time": 45,
        "summary": "Rotating tires evens out wear and extends their life.",
        "steps": [
            {"title": "Check spec", "text": "Confirm the recommended rotation pattern in the owner's manual — directional tires must stay on the same side."},
            {"title": "Swap corners", "text": "Lift the car one corner at a time and move the tires according to the pattern (usually front-to-back, crossing on the drive axle)."},
            {"title": "Tighten and check", "text": "Torque the lug nuts to spec, lower the car, and re-check the pressure on all four tires."},
        ],
        "tools": ["Jack and stands", "Lug wrench", "Torque wrench", "Tire pressure gauge"],
        "parts": ["None"],
        "tips": "Rotate every 8,000–10,000 km and inspect the tread for uneven wear as you go.",
    },
    {
        "slug": "spark-plug-replacement",
        "title": "Spark Plug Replacement",
        "category": "Engine",
        "difficulty": "Medium",
        "time": 60,
        "summary": "Fresh spark plugs restore smooth idle, power and fuel economy.",
        "steps": [
            {"title": "Remove covers", "text": "Disconnect the ignition coils or leads one at a time so you don't mix them up."},
            {"title": "Clean the seat", "text": "Blow or brush any debris out of the plug wells before removing the plugs to stop dirt falling into the cylinder."},
            {"title": "Fit new plugs", "text": "Gap the new plugs if needed, thread them in by hand to avoid cross-threading, then torque to spec."},
            {"title": "Reconnect", "text": "Re-fit the coils or leads in order, start the engine and listen for a smooth idle."},
        ],
        "tools": ["Spark plug socket", "Torque wrench", "Gap tool", "Extension bar"],
        "parts": ["Spark plugs (correct type)", "Optional: dielectric grease"],
        "tips": "Replace them on the manufacturer's interval — many modern cars need 100,000 km plugs.",
    },
    {
        "slug": "headlight-bulb-replacement",
        "title": "Headlight Bulb Replacement",
        "category": "Battery & Electrical",
        "difficulty": "Easy",
        "time": 20,
        "summary": "Swap a burnt-out headlight bulb and restore visibility at night.",
        "steps": [
            {"title": "Access the unit", "text": "Open the bonnet and locate the back of the headlight housing. Some cars need the housing removed or the wheel arch liner opened."},
            {"title": "Remove the old bulb", "text": "Disconnect the plug, unclip the retainer, and pull the bulb out — do not touch the glass with bare fingers."},
            {"title": "Fit the new bulb", "text": "Install the new bulb without touching the glass, secure the retainer and reconnect the plug."},
            {"title": "Test", "text": "Switch the lights on and check the beam height before driving."},
        ],
        "tools": ["Phillips screwdriver (optional)", "Gloves"],
        "parts": ["Correct bulb type"],
        "tips": "Oil from your fingers shortens the life of halogen bulbs — use gloves or a cloth.",
    },
    {
        "slug": "alternator-health-check",
        "title": "Alternator Health Check",
        "category": "Battery & Electrical",
        "difficulty": "Hard",
        "time": 40,
        "summary": "Diagnose charging problems before the car leaves you stranded.",
        "steps": [
            {"title": "Static voltage", "text": "With the engine off, the battery should read about 12.4–12.6 V across the terminals."},
            {"title": "Running voltage", "text": "Start the car and measure again — it should climb to 13.8–14.5 V. If it stays at battery voltage, the alternator is not charging."},
            {"title": "Load test", "text": "Switch on headlights, heated screen and blower, then re-check. Voltage dropping well below 13 V under load points to a weak alternator."},
            {"title": "Belt and wiring", "text": "Inspect the serpentine belt for cracks or slack and check the alternator wiring and ground for corrosion."},
        ],
        "tools": ["Multimeter", "Flashlight"],
        "parts": ["None (inspection)"],
        "tips": "A battery warning lamp that flickers at idle and dims lights means charge, not battery.",
    },
]

BY_SLUG: dict[str, Guide] = {g["slug"]: g for g in GUIDES}


def guide(slug: str) -> Guide | None:
    return BY_SLUG.get(slug)


def guides_by_category(category: str) -> list[Guide]:
    return [g for g in GUIDES if g["category"] == category]


def related(slug: str, limit: int = 3) -> list[Guide]:
    current = BY_SLUG.get(slug)
    if not current:
        return []
    same = [g for g in GUIDES if g["slug"] != slug and g["category"] == current["category"]]
    others = [g for g in GUIDES if g["slug"] != slug and g not in same]
    return (same + others)[:limit]
