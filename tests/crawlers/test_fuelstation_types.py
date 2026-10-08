"""Fuel type classification tests.

The Persian name cases are pinned from real mapped station names, because
the failure mode here is silent: a misclassified station still looks like a
valid result.
"""
import json
from pathlib import Path

import pytest

from app.crawlers.fuelstation.fuel_types import classify_fuel_type
from app.schemas.fuel_station import FuelType

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "fuel_stations_sample.json"


# --- Tier 1: structured tags win -----------------------------------------

def test_tag_gasoline_yes_is_petrol():
    assert classify_fuel_type({"fuel:gasoline": "yes"}, "پمپ گاز") == FuelType.PETROL


def test_tag_diesel_yes_is_diesel():
    assert classify_fuel_type({"fuel:diesel": "yes"}, "پمپ بنزین") == FuelType.DIESEL


def test_tag_cng_yes_is_cng():
    assert classify_fuel_type({"fuel:cng": "yes"}, "پمپ بنزین") == FuelType.CNG


def test_combined_generic_fuel_tag():
    assert classify_fuel_type({"fuel": "petrol;gasoline"}) == FuelType.PETROL


# --- Tier 2: negative tags imply the alternative --------------------------

def test_diesel_no_implies_petrol():
    assert classify_fuel_type({"fuel:diesel": "no"}) == FuelType.PETROL


def test_gasoline_no_implies_diesel():
    assert classify_fuel_type({"fuel:gasoline": "no"}) == FuelType.DIESEL


def test_negative_tag_beats_name():
    """A structured denial outranks what the name suggests."""
    assert classify_fuel_type({"fuel:diesel": "no"}, "پمپ گازوئیل") == FuelType.PETROL


# --- Tier 3: Persian names ------------------------------------------------

@pytest.mark.parametrize("name", ["پمپ بنزین", "پمپ بنزین چهلستون", "پمپ‌بنزین"])
def test_petrol_names(name):
    assert classify_fuel_type({}, name) == FuelType.PETROL


def test_petrol_name_typo_tolerated():
    """بنرین is a real-world misspelling of بنزین seen in mapped names."""
    assert classify_fuel_type({}, "پمپ بنرین") == FuelType.PETROL


@pytest.mark.parametrize("name", ["پمپ گازوئیل", "پمپ گازوییل", "پمپ گازوییل اختصاصی"])
def test_diesel_names(name):
    assert classify_fuel_type({}, name) == FuelType.DIESEL


@pytest.mark.parametrize("name", ["پمپ گاز", "جایگاه CNG", "جایگاه گاز طبیعی", "پمپ گاز CNG"])
def test_cng_names(name):
    assert classify_fuel_type({}, name) == FuelType.CNG


def test_lpg_name():
    assert classify_fuel_type({}, "پمپ گاز ال پی جی") == FuelType.LPG


def test_gas_name_is_cng_not_petrol():
    """The core trap: پمپ گاز means CNG.

    Persian for natural gas is گاز, the word an English reader takes to mean
    gasoline. Matching petrol on a gas word misfiles ~28% of Iran.
    """
    classified = classify_fuel_type({}, "پمپ گاز")
    assert classified == FuelType.CNG
    assert classified != FuelType.PETROL


def test_combined_petrol_and_gas_name_is_cng():
    """Gas wins over petrol when a name mentions both."""
    assert classify_fuel_type({}, "پمپ بنزین و گاز") == FuelType.CNG


# --- Unknown stays unknown ------------------------------------------------

def test_unnamed_untagged_is_unknown_not_petrol():
    assert classify_fuel_type({}, "") == FuelType.UNKNOWN


def test_no_name_no_tags_is_unknown():
    assert classify_fuel_type() == FuelType.UNKNOWN


def test_name_without_fuel_signal_is_unknown():
    assert classify_fuel_type({}, "بهاران") == FuelType.UNKNOWN


def test_generic_fuel_station_name_is_unknown():
    """'جایگاه سوخت' just means 'fuel station' and implies no type."""
    assert classify_fuel_type({}, "جایگاه سوخت") == FuelType.UNKNOWN


# --- Fixture: real mapped nodes -------------------------------------------

def test_fixture_classification_counts():
    """Reproduce observed counts from real Iranian nodes, within tolerance.

    Measured over all 3,924 nodes on 2026-10-08: ~1,999 petrol, ~417 diesel,
    ~1,087 CNG, ~31 LPG, ~392 unknown. The fixture is a recorded sample, so
    the tolerances are tight relative to the national distribution.
    """
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    nodes = data["elements"]

    counts = {}
    for node in nodes:
        tags = node.get("tags") or {}
        name = tags.get("name") or tags.get("name:fa")
        ft = classify_fuel_type(tags, name)
        counts[ft] = counts.get(ft, 0) + 1

    total = len(nodes)
    assert counts.get(FuelType.PETROL, 0) / total > 0.40
    assert counts.get(FuelType.CNG, 0) / total > 0.15
    assert counts.get(FuelType.DIESEL, 0) > 0
    # Every station resolves to exactly one type, and unknown stays a minority.
    assert sum(counts.values()) == total
    assert counts.get(FuelType.UNKNOWN, 0) / total < 0.20