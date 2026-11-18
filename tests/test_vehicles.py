"""Vehicle helper tests (synthetic fixtures shaped like the live API)."""

from __future__ import annotations

from enterprise_carclub import (
    fuel_of,
    seats_of,
    size_class,
    summarize_stack,
    transmission_of,
)

PEUGEOT = {
    "id": "53237",
    "description": "#53237: MediaCityUK M50 2EQ - Peugeot 208",
    "latitude": 53.473362,
    "longitude": -2.298729,
    "make_model": "Peugeot 208",
    "vehicle_details": {
        "year": 2026,
        "color": "White",
        "plate": "FL26 PKZ",
        "make": "Peugeot",
        "model": "208",
        "features": {
            "amenities": [
                {"name": "peeps_05", "description": "5 People"},
                {"name": "stick", "description": "Manual"},
            ]
        },
    },
}

TRANSIT = {
    "id": "54978",
    "description": "#54978: Blossom Street - Ford Transit Custom EV",
    "latitude": 53.48491,
    "longitude": -2.227774,
    "make_model": "Ford Transit Custom EV",
    "image_url": "https://booking.citycarclub.co.uk//images/client_images/vehicle_type_1771252638.png",
    "thumb_url": "https://booking.citycarclub.co.uk//images/client_images/vehicle_thumb_1771252638.png",
    "vehicle_details": {
        "year": 0,
        "color": "White",
        "plate": "WO25 DUH",
        "make": "Ford",
        "model": "Transit EV",
        "battery_level": "82",
        "range": "121",
        "features": {
            "amenities": [
                {"name": "peeps_03", "description": "3 People"},
                {"name": "electric_vehicle", "description": "Electric vehicle"},
                {"name": "automatic", "description": "Automatic"},
            ]
        },
    },
}


def test_seats_and_transmission() -> None:
    assert seats_of(PEUGEOT) == 5
    assert transmission_of(PEUGEOT) == "manual"
    assert fuel_of(PEUGEOT) == "petrol"


def test_ev_van_detection() -> None:
    assert seats_of(TRANSIT) == 3
    assert fuel_of(TRANSIT) == "electric"
    assert size_class("Ford Transit Custom EV", 3) == "van"


def test_size_class_falls_back_to_seats() -> None:
    assert size_class("Peugeot 208", 5) == "small"
    assert size_class("Some Galaxy", 7) == "medium"
    assert size_class(None, None) == "small"


def test_summarize_stack() -> None:
    entry = {
        "availability": "good",
        "distance": 1221.6,
        "timeslots": [
            {"time": 1795026600, "available": False},
            {"time": 1795027500, "available": True},
        ],
        "vehicle_stack": TRANSIT,
    }
    summary = summarize_stack(entry)
    assert summary["stack_id"] == "54978"
    assert summary["thumb_url"] == TRANSIT.get("thumb_url")
    assert summary["size_class"] == "van"
    assert summary["fuel"] == "electric"
    assert summary["distance_m"] == 1221.6
    assert summary["next_free_time"] == 1795027500
    assert len(summary["timeslots"]) == 2


def test_summarize_stack_tolerates_missing_details() -> None:
    summary = summarize_stack({"availability": "good", "vehicle_stack": {"id": "1"}})
    assert summary["seats"] is None
    assert summary["size_class"] == "small"
    assert summary["next_free_time"] is None
