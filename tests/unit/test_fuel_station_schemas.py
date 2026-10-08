"""Schema tests for the fuel station capability.

These assert contract-level properties, not implementation details.
"""
import pytest
from app.schemas.fuel_station import (
    FuelType,
    FuelStationSearchQuery,
    FuelStationResult,
    FuelStationSearchResponse,
)
from app.schemas.common import ProviderInfo


def test_result_has_no_price_field():
    """Spec: returned stations carry no price amount and no currency."""
    fields = FuelStationResult.model_fields
    assert "price" not in fields
    assert "amount" not in fields
    assert "currency" not in fields
    # Nothing price-shaped anywhere in the model's field set.
    assert not [f for f in fields if "price" in f.lower()]


def test_response_has_no_price_field():
    fields = FuelStationSearchResponse.model_fields
    assert not [f for f in fields if "price" in f.lower()]


def test_result_required_fields():
    """Identity, position and both route-relative distances are mandatory."""
    res = FuelStationResult(
        id="osm:node:12345",
        provider=ProviderInfo(name="openstreetmap"),
        latitude=35.1,
        longitude=51.1,
        km_into_trip=12.5,
        distance_off_route_m=120.0,
    )
    assert res.fuel_type == FuelType.UNKNOWN
    assert res.id == "osm:node:12345"
    assert res.km_into_trip == 12.5


def test_query_defaults():
    q = FuelStationSearchQuery(origin="Tehran", destination="Isfahan")
    assert q.radius_m == 1000
    assert q.fuel_types is None


def test_query_accepts_coordinate_pairs():
    q = FuelStationSearchQuery(
        origin="35.6892,51.3890",
        destination="32.6539,51.6660",
    )
    assert q.origin == "35.6892,51.3890"


@pytest.mark.parametrize("bad_radius", [0, 49, 10001])
def test_query_rejects_out_of_range_radius(bad_radius):
    with pytest.raises(Exception):
        FuelStationSearchQuery(
            origin="Tehran", destination="Isfahan", radius_m=bad_radius
        )


def test_fuel_types_filter_parses_values():
    q = FuelStationSearchQuery(
        origin="Tehran", destination="Isfahan", fuel_types=["petrol", "diesel"]
    )
    assert q.fuel_types == [FuelType.PETROL, FuelType.DIESEL]


def test_fuel_type_values():
    assert {t.value for t in FuelType} == {"petrol", "diesel", "cng", "lpg", "unknown"}