"""Vehicle helpers: attribute and size-class derivation for search results.

The MSI API exposes no size class (small/medium/van) — ``vehicle_types``
entries carry no populated metadata — so :func:`size_class` applies a small
documented keyword heuristic over ``make_model`` plus seat count from the
``peeps_NN`` amenity. Van models are explicit; everything else falls back to
seats (``<=5`` → small, otherwise medium). Override as needed downstream.
"""

from __future__ import annotations

from typing import Any

#: Model-name fragments identifying vans in the Enterprise fleet.
VAN_KEYWORDS = (
    "transit",
    "trafic",
    "vivaro",
    "combo",
    "sprinter",
    "crafter",
    "boxer",
    "jumper",
    "ducato",
    "movano",
    "proace",
    "nv200",
    "nv300",
    "primastar",
    "interstar",
    "dispatch",
    "expert",
    "jumpy",
)


def amenities_of(vehicle_stack: dict[str, Any]) -> list[str]:
    """Return amenity names (e.g. ``peeps_05``, ``electric_vehicle``)."""
    details = vehicle_stack.get("vehicle_details")
    if not isinstance(details, dict):
        return []
    features = details.get("features")
    if not isinstance(features, dict):
        return []
    amenities = features.get("amenities")
    if not isinstance(amenities, list):
        return []
    return [a["name"] for a in amenities if isinstance(a, dict) and isinstance(a.get("name"), str)]


def seats_of(vehicle_stack: dict[str, Any]) -> int | None:
    """Seat count from the ``peeps_NN`` amenity, if present."""
    for name in amenities_of(vehicle_stack):
        if name.startswith("peeps_"):
            try:
                return int(name.split("_", 1)[1])
            except ValueError:
                continue
    return None


def fuel_of(vehicle_stack: dict[str, Any]) -> str:
    """Fuel type derived from amenity flags (defaults to petrol)."""
    amenities = set(amenities_of(vehicle_stack))
    if "electric_vehicle" in amenities:
        return "electric"
    if "hybrid" in amenities:
        return "hybrid"
    if "diesel" in amenities:
        return "diesel"
    return "petrol"


def transmission_of(vehicle_stack: dict[str, Any]) -> str | None:
    """Transmission derived from amenity flags."""
    amenities = set(amenities_of(vehicle_stack))
    if "automatic" in amenities:
        return "automatic"
    if "stick" in amenities:
        return "manual"
    return None


def size_class(make_model: str | None, seats: int | None) -> str:
    """Best-effort size class: ``van`` by model keyword, else by seats."""
    model = (make_model or "").lower()
    if any(keyword in model for keyword in VAN_KEYWORDS):
        return "van"
    if seats is not None and seats > 5:
        return "medium"
    return "small"


def summarize_stack(entry: dict[str, Any]) -> dict[str, Any]:
    """Flatten one ``vehicle_stack_availability`` entry for entity attributes."""
    stack = entry.get("vehicle_stack")
    stack_dict = stack if isinstance(stack, dict) else {}
    make_model = stack_dict.get("make_model")
    make_model_str = make_model if isinstance(make_model, str) else None
    seats = seats_of(stack_dict)
    slots = entry.get("timeslots")
    slot_list = [s for s in slots if isinstance(s, dict)] if isinstance(slots, list) else []
    next_free: int | None = None
    for slot in slot_list:
        if slot.get("available") is True and isinstance(slot.get("time"), int):
            next_free = slot["time"]
            break
    details = stack_dict.get("vehicle_details")
    details_dict = details if isinstance(details, dict) else {}
    return {
        "stack_id": stack_dict.get("id"),
        "description": stack_dict.get("description"),
        "distance_m": entry.get("distance"),
        "latitude": stack_dict.get("latitude"),
        "longitude": stack_dict.get("longitude"),
        "make_model": make_model_str,
        "plate": details_dict.get("plate"),
        "year": details_dict.get("year"),
        "seats": seats,
        "fuel": fuel_of(stack_dict),
        "transmission": transmission_of(stack_dict),
        "size_class": size_class(make_model_str, seats),
        "availability": entry.get("availability"),
        "battery_level": details_dict.get("battery_level"),
        "range": details_dict.get("range"),
        "next_free_time": next_free,
        "timeslots": slot_list,
    }
