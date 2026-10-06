"""
Alibaba flight result mapping.

Field names here come from captured live payloads, not from documentation:
Alibaba publishes no OpenAPI document, so every mapping is pinned by a test
against a capture in ``tests/fixtures/``.

Two provider quirks drive most of this module:

- Aircraft designations arrive in a dozen inconsistent formats within a single
  response (``319``, ``737``, ``MD8``, ``BOEING 737``, ``Airbus A320``, ...).
- ``statusName`` carries the authoritative availability text in Persian, while
  ``isAllowedToBuy`` is ``true`` even for cancelled flights and so cannot be used
  as a filter.
"""

from typing import Any, Dict, List, Optional

# "Capacity complete" - the flight exists but has no remaining seats.
STATUS_FULL_CAPACITY = "تکمیل ظرفیت"
# "Cancelled"
STATUS_CANCELLED = "کنسل شده"

# Alibaba emits single-character cabin codes rather than words.
CABIN_CLASS_BY_CODE: Dict[str, str] = {
    "E": "economy",
    "B": "business",
    "F": "first",
    "Y": "economy",
    "C": "business",
    "J": "business",
}

# Observed across live responses: bare numeric codes, ICAO-ish numbers,
# manufacturer names, and mixed case. Only families whose meaning is
# unambiguous are listed; anything else passes through rather than being guessed.
_AIRCRAFT_CANONICAL = {
    "100": "Fokker 100",
    "717": "Boeing 717",
    "727": "Boeing 727",
    "737": "Boeing 737",
    "747": "Boeing 747",
    "757": "Boeing 757",
    "767": "Boeing 767",
    "777": "Boeing 777",
    "a300": "Airbus A300",
    "a310": "Airbus A310",
    "a320": "Airbus A320",
    "a321": "Airbus A321",
    "a330": "Airbus A330",
    "b1900": "Beechcraft 1900",
}

_MANUFACTURERS = ("boeing", "airbus", "fokker", "embraer")


def normalize_aircraft(raw: Any) -> Optional[str]:
    """
    Present an aircraft designation consistently.

    Alibaba mixes bare numeric codes with spelled-out manufacturer names, so one
    family can appear as ``737``, ``Boeing 737`` and ``BOEING 737`` within a
    single result set. Collapse those onto one spelling. Unrecognised values are
    returned trimmed rather than dropped, since an unfamiliar code is still
    information.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    key = text.lower()
    if key in _AIRCRAFT_CANONICAL:
        return _AIRCRAFT_CANONICAL[key]

    # Manufacturer-prefixed forms unify on a single capitalisation, so
    # "Boeing 737" and "BOEING 737" cannot become separate labels.
    for manufacturer in _MANUFACTURERS:
        prefix = manufacturer.lower() + " "
        if key.startswith(prefix):
            model = text[len(prefix):].strip().upper()
            if model:
                return f"{manufacturer.capitalize()} {model}"

    # Bare three-digit family code: "319" is an Airbus, "737" a Boeing.
    if text.isdigit() and len(text) == 3:
        manufacturer = "Airbus" if text[0] == "3" else "Boeing"
        return f"{manufacturer} {text}"

    return text


def normalize_cabin_class(raw: Any) -> str:
    """
    Translate Alibaba's cabin code into the project vocabulary.

    Unmapped codes pass through unchanged so an unfamiliar code is visible rather
    than silently reported as economy.
    """
    if raw is None:
        return "economy"
    code = str(raw).strip()
    if not code:
        return "economy"
    return CABIN_CLASS_BY_CODE.get(code.upper(), code)


def is_bookable(item: Dict[str, Any]) -> bool:
    """
    Decide whether a flight can actually be booked.

    ``statusName`` is the authoritative signal: cancelled and capacity-complete
    flights both still report ``isAllowedToBuy: true``, so that flag is unusable.
    A flight with no explicit status is retained.
    """
    status_name = item.get("statusName")
    if status_name:
        normalized = str(status_name).strip()
        if normalized in (STATUS_CANCELLED, STATUS_FULL_CAPACITY):
            return False
    return True


def split_timestamp(raw: Any) -> tuple[Optional[str], str]:
    """
    Split an ISO timestamp into (date, time-of-day).

    Alibaba sends full ``YYYY-MM-DDTHH:MM:SS`` values, so the calendar date is
    available and an overnight arrival can be reported on the correct day.
    """
    if not raw:
        return None, ""
    text = str(raw).strip()
    if "T" in text:
        date_part, _, time_part = text.partition("T")
        return date_part, time_part[:5]
    if " " in text:
        date_part, _, time_part = text.partition(" ")
        return date_part, time_part[:5]
    return None, text[:5]


def collect_departing(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Pull the departing flight list out of a phase-two response.

    Flights nest it under ``result``; trains return it at the top level.
    """
    result = payload.get("result")
    if isinstance(result, dict):
        departing = result.get("departing")
    else:
        departing = payload.get("departing")

    if not isinstance(departing, list):
        return []
    return [i for i in departing if isinstance(i, dict)]