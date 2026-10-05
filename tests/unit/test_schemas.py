import pytest
from pydantic import ValidationError
from app.schemas.common import PriceInfo, Currency, ProviderInfo
from app.schemas.flight import FlightSearchQuery, FlightResult, FlightSegment
from app.schemas.hotel import HotelSearchQuery, HotelResult, RoomOffer
from app.schemas.accommodation import AccommodationSearchQuery, AccommodationResult
from app.schemas.transport import TransportSearchQuery, TransportResult

def test_flight_schemas():
    query = FlightSearchQuery(
        origin="THR",
        destination="MHD",
        depart_date="2026-10-15",
        adults=2,
    )
    assert query.origin == "THR"
    assert query.adults == 2
    assert query.cabin_class == "economy"

    segment = FlightSegment(
        airline_name="Mahan Air",
        flight_number="W5-1032",
        origin_code="THR",
        destination_code="MHD",
        departure_time="08:30",
        arrival_time="10:00",
        departure_date="2026-10-15",
    )
    result = FlightResult(
        id="alibaba_w5_1032",
        provider=ProviderInfo(name="alibaba"),
        is_charter=False,
        price=PriceInfo(amount=18500000, currency=Currency.IRR),
        available_seats=5,
        outbound=[segment],
    )
    assert result.provider.name == "alibaba"
    assert result.price.amount == 18500000
    assert len(result.outbound) == 1

def test_hotel_schemas():
    query = HotelSearchQuery(
        city="Kish",
        checkin_date="2026-10-15",
        checkout_date="2026-10-18",
        rooms=1,
        adults=2,
    )
    room = RoomOffer(
        room_name="Double Room Sea View",
        has_breakfast=True,
        price_per_night=PriceInfo(amount=45000000, currency=Currency.IRR),
    )
    hotel = HotelResult(
        id="flytoday_hotel_102",
        provider=ProviderInfo(name="flytoday"),
        hotel_name="Toranj Marine Hotel",
        stars=5,
        user_rating=4.7,
        min_price_per_night=PriceInfo(amount=45000000, currency=Currency.IRR),
        rooms=[room],
    )
    assert hotel.hotel_name == "Toranj Marine Hotel"
    assert hotel.stars == 5
    assert len(hotel.rooms) == 1

def test_accommodation_schemas():
    query = AccommodationSearchQuery(
        city="Ramsar",
        checkin_date="2026-10-15",
        checkout_date="2026-10-18",
        guests=4,
    )
    residence = AccommodationResult(
        id="karnaval_villa_55",
        provider=ProviderInfo(name="karnaval"),
        title="Forest Luxury Villa",
        city="Ramsar",
        capacity_standard=4,
        capacity_max=8,
        bedrooms=2,
        price_per_night=PriceInfo(amount=3500000, currency=Currency.IRT),
    )
    assert residence.city == "Ramsar"
    assert residence.price_per_night.amount == 3500000

def test_transport_schemas():
    bus_query = TransportSearchQuery(
        origin="Tehran",
        destination="Isfahan",
        depart_date="2026-10-15",
        transport_type="bus",
    )
    bus_result = TransportResult(
        id="flytoday_bus_10",
        provider=ProviderInfo(name="flytoday"),
        transport_type="bus",
        company_name="Hamsafar",
        service_class="VIP 25-Seat Maral",
        origin_terminal="Beyhaghi",
        destination_terminal="Kaveh",
        departure_date="2026-10-15",
        departure_time="14:00",
        price=PriceInfo(amount=280000, currency=Currency.IRT),
        available_seats=12,
    )
    assert bus_result.transport_type == "bus"
    assert bus_result.company_name == "Hamsafar"
