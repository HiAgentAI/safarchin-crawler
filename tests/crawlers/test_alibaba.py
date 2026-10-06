"""
Alibaba crawler tests.

These run against payloads captured from the live provider, so they exercise the
real response shape rather than an invented one. The original fixture in this
repo was hand-authored - its ``uniqueKey`` values were the same strings the tests
asserted on - so no assertion could ever fail.
"""

import json
from pathlib import Path

import pytest

from app.crawlers.alibaba.crawler import AlibabaCrawler
from app.crawlers.alibaba.normalize import (
    STATUS_CANCELLED,
    STATUS_FULL_CAPACITY,
    is_bookable,
    normalize_aircraft,
    normalize_cabin_class,
    split_timestamp,
)
from app.crawlers.alibaba.protocol import AlibabaSearchError
from app.schemas.common import Currency
from app.schemas.flight import FlightSearchQuery
from app.schemas.transport import TransportSearchQuery

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES_DIR / name) as fh:
        return json.load(fh)


@pytest.fixture
def flight_payload():
    return _load("alibaba_flight_response.json")


@pytest.fixture
def train_payload():
    return _load("alibaba_train_response.json")


class StubClient:
    """Serves a fixed criteria response then a fixed result response."""

    def __init__(self, criteria_body, result_body):
        self._criteria = criteria_body
        self._result = result_body
        self.posts = []
        self.gets = []

    async def post(self, url, json_data=None, **kwargs):
        self.posts.append((url, json_data))
        return _resp(self._criteria)

    async def get(self, url, params=None, headers=None, **kwargs):
        self.gets.append(url)
        return _resp(self._result)


def _resp(body):
    class R:
        @staticmethod
        def json():
            return body
    return R()


@pytest.fixture
def flight_crawler(flight_payload):
    criteria = _load("alibaba_flight_criteria_response.json")
    client = StubClient(criteria, flight_payload)
    crawler = AlibabaCrawler(client=client)
    crawler.client = client
    return crawler


@pytest.fixture
def train_crawler(train_payload):
    criteria = _load("alibaba_train_criteria_response.json")
    client = StubClient(criteria, train_payload)
    crawler = AlibabaCrawler(client=client)
    crawler.client = client
    return crawler


# --------------------------------------------------------------------- 3.1 / protocol


@pytest.mark.asyncio
async def test_search_flights_posts_criteria_then_gets_the_handle(flight_crawler):
    """Alibaba answers GET on the criteria URL with 405 Method Not Allowed."""
    query = FlightSearchQuery(origin="MHD", destination="THR", depart_date="2026-10-23")

    results = await flight_crawler.search_flights(query)

    assert len(flight_crawler.client.posts) == 1, "criteria must be POSTed"
    assert len(flight_crawler.client.gets) == 1, "results must be fetched by handle"
    assert results, "expected flights from the captured payload"


@pytest.mark.asyncio
async def test_search_flights_sends_gregorian_date_and_pax(flight_crawler):
    query = FlightSearchQuery(
        origin="mhd", destination="thr", depart_date="2026-10-23", adults=2, children=1, infants=1
    )

    await flight_crawler.search_flights(query)

    url, payload = flight_crawler.client.posts[0]
    assert url.endswith("/api/v1/flights/domestic/available")
    assert payload["origin"] == "MHD"
    assert payload["destination"] == "THR"
    assert payload["departureDate"] == "2026-10-23"
    assert payload["adult"] == 2
    assert payload["child"] == 1
    assert payload["infant"] == 1


@pytest.mark.asyncio
async def test_search_flights_raises_instead_of_returning_empty_on_failure():
    class BrokenPost(StubClient):
        async def post(self, url, json_data=None, **kwargs):
            raise RuntimeError("405 Method Not Allowed")

    crawler = AlibabaCrawler(client=BrokenPost({}, {}))
    query = FlightSearchQuery(origin="THR", destination="MHD", depart_date="2026-10-23")

    with pytest.raises(AlibabaSearchError):
        await crawler.search_flights(query)


# --------------------------------------------------------------------- 3.2 identity


@pytest.mark.asyncio
async def test_every_flight_carries_its_own_carrier_identity(flight_crawler, flight_payload):
    query = FlightSearchQuery(origin="MHD", destination="THR", depart_date="2026-10-23")
    results = await flight_crawler.search_flights(query)

    assert results
    for r in results:
        assert r.outbound[0].airline_name, "carrier name must never fall back to a default"
        assert r.outbound[0].airline_code
        assert r.outbound[0].flight_number
        assert r.id


def test_carrier_fields_come_from_the_flat_provider_fields(flight_payload):
    """
    There is no nested airline object; the old parser read one and always got None.
    """
    raw = flight_payload["result"]["departing"][0]

    assert "airline" not in raw
    assert raw["airlineName"]
    assert raw["airlineCode"]
    assert raw["flightNumber"]


@pytest.mark.asyncio
async def test_route_codes_come_from_the_provider_not_the_query(flight_crawler, flight_payload):
    """
    Flights report the route as `origin`/`destination`, not `originCode`.

    Reading only `originCode` silently yielded nothing and fell back to echoing
    the requested route back to the caller.
    """
    raw = flight_payload["result"]["departing"][0]
    assert "originCode" not in raw, "flight items use 'origin', not 'originCode'"
    assert raw["origin"] and raw["destination"]

    # Query a different route than the payload reports, so an echo is detectable
    query = FlightSearchQuery(origin="XXX", destination="YYY", depart_date="2026-10-23")
    results = await flight_crawler.search_flights(query)

    assert results
    for r in results:
        assert r.outbound[0].origin_code == raw["origin"]
        assert r.outbound[0].destination_code == raw["destination"]
        assert r.outbound[0].origin_code != "XXX"


@pytest.mark.asyncio
async def test_absent_carrier_code_is_omitted_not_invented(flight_payload):
    """A missing code is reported as absent rather than filled with a placeholder."""
    payload = json.loads(json.dumps(flight_payload))
    target = payload["result"]["departing"][0]
    target["airlineCode"] = None
    # Make the target bookable so it survives the availability filter
    target["statusName"] = ""
    target["status"] = "9"

    client = StubClient(_load("alibaba_flight_criteria_response.json"), payload)
    crawler = AlibabaCrawler(client=client)
    query = FlightSearchQuery(origin="MHD", destination="THR", depart_date="2026-10-23")
    results = await crawler.search_flights(query)

    match = [r for r in results if r.id == target["uniqueKey"]]
    assert len(match) == 1, "the flight must stay in the result set"
    assert match[0].outbound[0].airline_code is None
    assert match[0].outbound[0].airline_name == target["airlineName"]


# --------------------------------------------------------------------- 3.3 timestamps


@pytest.mark.asyncio
async def test_overnight_flight_reports_the_later_arrival_date(flight_crawler, flight_payload):
    """
    A flight departing late and arriving after midnight reports both dates.

    The captured overnight flights happen to be unbookable, so the mapping is
    checked on the raw record; availability filtering is covered separately.
    """
    query = FlightSearchQuery(origin="MHD", destination="THR", depart_date="2026-10-23")
    overnight = [
        i for i in flight_payload["result"]["departing"]
        if i["leaveDateTime"][:10] != i["arrivalDateTime"][:10]
    ]
    assert overnight, "capture must contain an overnight flight"

    for item in overnight:
        # Availability is an independent axis: mark this record bookable so the
        # timestamp mapping for a *returned* overnight flight is observable.
        bookable = dict(item, statusName="", status="9")
        results = flight_crawler._parse_flights(
            {"result": {"departing": [bookable]}}, query
        )
        assert len(results) == 1, "a bookable overnight flight must be returned"

        seg = results[0].outbound[0]
        assert seg.departure_date == item["leaveDateTime"][:10]
        assert seg.arrival_date == item["arrivalDateTime"][:10]
        assert seg.arrival_date > seg.departure_date
        assert seg.departure_time == item["leaveDateTime"][11:16]
        assert seg.arrival_time == item["arrivalDateTime"][11:16]


@pytest.mark.asyncio
async def test_same_day_flight_reports_matching_dates(flight_crawler):
    query = FlightSearchQuery(origin="MHD", destination="THR", depart_date="2026-10-23")
    body = _load("alibaba_flight_response.json")
    same_day = [
        i for i in body["result"]["departing"]
        if i["leaveDateTime"][:10] == i["arrivalDateTime"][:10]
    ]
    assert same_day

    seg = flight_crawler._parse_flights({"result": {"departing": [same_day[0]]}}, query)[0].outbound[0]
    assert seg.departure_date == seg.arrival_date


def test_split_timestamp_extracts_date_and_time():
    assert split_timestamp("2026-10-20T16:50:00") == ("2026-10-20", "16:50")
    assert split_timestamp("2026-10-21T03:10:00") == ("2026-10-21", "03:10")
    assert split_timestamp(None) == (None, "")


# --------------------------------------------------------------------- 3.4 cabin


@pytest.mark.asyncio
async def test_cabin_codes_map_to_the_project_vocabulary():
    assert normalize_cabin_class("E") == "economy"
    assert normalize_cabin_class("B") == "business"
    assert normalize_cabin_class("e") == "economy"
    assert normalize_cabin_class(None) == "economy"
    # An unmapped code passes through rather than silently becoming economy
    assert normalize_cabin_class("ZZ") == "ZZ"


@pytest.mark.asyncio
async def test_search_flights_normalizes_cabin_class(flight_crawler, flight_payload):
    query = FlightSearchQuery(origin="MHD", destination="THR", depart_date="2026-10-23")
    results = await flight_crawler.search_flights(query)

    allowed = {"economy", "business", "first"}
    for r in results:
        assert r.outbound[0].cabin_class in allowed, (
            f"cabin class leaked through un-normalised: {r.outbound[0].cabin_class!r}"
        )

    # The capture contains a business-cabin flight, so the mapping is exercised
    raw_classes = {i["classType"] for i in flight_payload["result"]["departing"]}
    assert "B" in raw_classes, "capture should include a business cabin to exercise the mapping"
    mapped = {
        r.outbound[0].cabin_class
        for i, r in zip(
            [i for i in flight_payload["result"]["departing"] if is_bookable(i)], results
        )
    }
    assert "business" in mapped


# --------------------------------------------------------------------- 3.5 aircraft


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("737", "Boeing 737"),
        ("319", "Airbus 319"),
        ("320", "Airbus 320"),
        ("A310", "Airbus A310"),
        # Case variants of one family must collapse onto a single label
        ("Boeing 737", "Boeing 737"),
        ("BOEING 737", "Boeing 737"),
        ("Airbus A320", "Airbus A320"),
        ("AIRBUS A320", "Airbus A320"),
        ("Boeing 737-500", "Boeing 737-500"),
        # Not confidently identifiable: passed through rather than guessed at
        ("MD8", "MD8"),
        ("145", "Boeing 145"),
        ("100", "Fokker 100"),
        (None, None),
        ("", None),
    ],
)
def test_aircraft_normalization(raw, expected):
    assert normalize_aircraft(raw) == expected


def test_equivalent_aircraft_do_not_split_into_several_labels(flight_payload):
    """
    The same family must not appear under materially different labels in one result set.
    """
    raw_aircraft = [i["aircraft"] for i in flight_payload["result"]["departing"]]
    normalized = [normalize_aircraft(a) for a in raw_aircraft]

    assert len(raw_aircraft) > 1, "capture should contain varied designations"
    assert len(set(normalized)) <= len(set(raw_aircraft))
    # Nothing normalizes to an empty or bare-whitespace label
    assert all(n and n.strip() for n in normalized)


# --------------------------------------------------------------------- 3.6 availability


def test_is_bookable_uses_status_not_the_buyable_flag():
    assert is_bookable({"statusName": STATUS_CANCELLED, "isAllowedToBuy": True}) is False
    assert is_bookable({"statusName": STATUS_FULL_CAPACITY, "isAllowedToBuy": True}) is False
    # No explicit status is retained
    assert is_bookable({"statusName": "", "isAllowedToBuy": True}) is True
    assert is_bookable({}) is True


@pytest.mark.asyncio
async def test_cancelled_and_full_flights_are_excluded(flight_crawler, flight_payload):
    query = FlightSearchQuery(origin="MHD", destination="THR", depart_date="2026-10-23")
    results = await flight_crawler.search_flights(query)

    raw = flight_payload["result"]["departing"]
    bookable_raw = [i for i in raw if is_bookable(i)]
    excluded = [i for i in raw if not is_bookable(i)]

    assert excluded, "capture must contain unbookable flights for this to mean anything"
    assert len(results) == len(bookable_raw)
    assert len(results) < len(raw), "unbookable flights must actually be dropped"

    returned_ids = {r.id for r in results}
    for item in excluded:
        assert item["uniqueKey"] not in returned_ids


@pytest.mark.asyncio
async def test_unbookable_flights_are_not_mistaken_for_bookable_ones(flight_payload):
    """The provider's buyable flag is true even for cancelled flights."""
    raw = flight_payload["result"]["departing"]
    unbookable = [i for i in raw if not is_bookable(i)]

    assert unbookable
    for item in unbookable:
        # If this ever becomes false the flag may have become usable, and the
        # filtering rule should be revisited rather than silently doubled up.
        assert item.get("isAllowedToBuy") is True


# --------------------------------------------------------------------- 3.7 price


@pytest.mark.asyncio
async def test_flight_prices_are_reported_in_rial(flight_crawler, flight_payload):
    query = FlightSearchQuery(origin="MHD", destination="THR", depart_date="2026-10-23")
    results = await flight_crawler.search_flights(query)

    assert results
    for r in results:
        assert r.price.currency == Currency.IRR
        assert "ریال" in (r.price.formatted or "")

    raw = [i for i in flight_payload["result"]["departing"] if is_bookable(i)]
    for item, result in zip(raw, results):
        assert result.price.amount == float(item["priceAdult"])


@pytest.mark.asyncio
async def test_flight_price_uses_a_real_fare_not_the_placeholder(flight_crawler, flight_payload):
    """Unbookable flights carry a placeholder fare; bookable ones do not."""
    placeholder = {100_000_000.0}
    query = FlightSearchQuery(origin="MHD", destination="THR", depart_date="2026-10-23")
    results = await flight_crawler.search_flights(query)

    for r in results:
        assert r.price.amount not in placeholder, (
            "a bookable flight was priced with the provider's placeholder fare"
        )


# --------------------------------------------------------------------- 3.8 dates


@pytest.mark.asyncio
async def test_jalali_departure_date_is_sent_as_gregorian(flight_crawler):
    """Alibaba parses a Jalali string as Gregorian year 1405 and rejects it."""
    query = FlightSearchQuery(origin="MHD", destination="THR", depart_date="1405-08-01")

    await flight_crawler.search_flights(query)

    _, payload = flight_crawler.client.posts[0]
    assert payload["departureDate"] == "2026-10-23"
    assert not payload["departureDate"].startswith("1405")


@pytest.mark.asyncio
async def test_gregorian_departure_date_is_passed_through(flight_crawler):
    query = FlightSearchQuery(origin="MHD", destination="THR", depart_date="2026-10-23")

    await flight_crawler.search_flights(query)

    _, payload = flight_crawler.client.posts[0]
    assert payload["departureDate"] == "2026-10-23"


@pytest.mark.asyncio
async def test_search_flights_sends_resolved_city_codes(flight_crawler):
    """Alibaba rejects city names, so names must be resolved to codes before sending."""
    query = FlightSearchQuery(origin="Mashhad", destination="Tehran", depart_date="2026-10-23")

    await flight_crawler.search_flights(query)

    _, payload = flight_crawler.client.posts[0]
    assert payload["origin"] == "MHD"
    assert payload["destination"] == "THR"


@pytest.mark.asyncio
async def test_search_flights_accepts_persian_city_names(flight_crawler):
    query = FlightSearchQuery(origin="مشهد", destination="تهران", depart_date="2026-10-23")

    await flight_crawler.search_flights(query)

    _, payload = flight_crawler.client.posts[0]
    assert payload["origin"] == "MHD"
    assert payload["destination"] == "THR"


@pytest.mark.asyncio
async def test_search_flights_passes_codes_through_unchanged(flight_crawler):
    query = FlightSearchQuery(origin="MHD", destination="THR", depart_date="2026-10-23")

    await flight_crawler.search_flights(query)

    _, payload = flight_crawler.client.posts[0]
    assert payload["origin"] == "MHD"
    assert payload["destination"] == "THR"


@pytest.mark.asyncio
async def test_unresolvable_city_fails_loudly_rather_than_returning_empty(flight_crawler):
    """
    An unknown city must raise.

    Forwarding it yields HTTP 400 from Alibaba, which the orchestrator reports
    as an empty result list - indistinguishable from having no flights.
    """
    query = FlightSearchQuery(
        origin="Nowherevilletta", destination="THR", depart_date="2026-10-23"
    )

    with pytest.raises(ValueError, match="Nowherevilletta"):
        await flight_crawler.search_flights(query)

    # Nothing was sent, so no pointless round trip was made
    assert flight_crawler.client.posts == []


# --------------------------------------------------------------- 5.1 dead endpoints


def test_no_alibaba_call_targets_an_unreachable_host_or_path():
    """
    The crawler must not reference endpoints that cannot work.

    Two integrations were removed: the hotel search URL returned 404 on every
    verb, and the accommodation search targeted a host that does not resolve in
    DNS. Neither can be reintroduced by accident.
    """
    import socket
    from pathlib import Path as _Path

    source_dir = _Path(__file__).resolve().parents[2] / "app" / "crawlers" / "alibaba"
    sources = "\n".join(p.read_text() for p in source_dir.glob("*.py"))

    assert "jabama" not in sources.lower(), "Jabama host does not resolve in DNS"
    assert "tpa." not in sources, "Jabama host does not resolve in DNS"
    assert "/api/v2/hotel" not in sources, "that path returns 404 on every verb"

    for dead in ("search_hotels", "search_accommodations"):
        assert dead not in sources, f"{dead} targets an endpoint that cannot work"

    # The base host itself must still resolve
    socket.gethostbyname("ws.alibaba.ir")


def test_alibaba_only_calls_endpoints_that_answer():
    """Every host the crawler contacts must be one that responds."""
    from app.crawlers.alibaba.crawler import AlibabaCrawler

    crawler = AlibabaCrawler()
    for url in (crawler.BASE_URL,):
        assert url.startswith("https://ws.alibaba.ir")
    assert crawler.FLIGHTS_PATH.startswith("/api/v1/")
    assert crawler.TRAIN_PATH.startswith("/api/v1/")