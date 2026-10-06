"""
Alibaba train search tests.

Runs against a captured live payload. Alibaba uses the same two-phase protocol as
flights but a different handle encoding, a different result envelope, and - the
detail most likely to cause a silent ten-fold error - a different price unit.
"""

import json
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from app.crawlers.alibaba.crawler import AlibabaCrawler
from app.crawlers.alibaba.protocol import AlibabaSearchError
from app.schemas.common import Currency
from app.schemas.flight import FlightSearchQuery
from app.schemas.transport import TransportSearchQuery

from tests.crawlers.test_alibaba import StubClient, _load, _resp  # noqa: F401


@pytest.fixture
def train_payload():
    return _load("alibaba_train_response.json")


@pytest.fixture
def flight_payload():
    return _load("alibaba_flight_response.json")


def _crawler(result_body, criteria_body=None):
    criteria = criteria_body or _load("alibaba_train_criteria_response.json")
    return AlibabaCrawler(client=StubClient(criteria, result_body))


def _query(**overrides):
    base = dict(
        origin="THR",
        destination="MHD",
        depart_date="2026-10-20",
        transport_type="train",
        passengers=1,
    )
    base.update(overrides)
    return TransportSearchQuery(**base)


# --------------------------------------------------------------------- 4.1 protocol


@pytest.mark.asyncio
async def test_search_trains_posts_criteria_then_gets_the_encoded_handle(train_payload):
    crawler = _crawler(train_payload)

    results = await crawler.search_transport(_query())

    assert len(crawler.client.posts) == 1
    assert len(crawler.client.gets) == 1
    # Trains encode the handle as a base64 criteria echo appended to the URL
    assert crawler.client.gets[0].startswith(
        "https://ws.alibaba.ir/api/v1/train/available/"
    )
    assert results, "expected departures from the captured payload"


@pytest.mark.asyncio
async def test_train_criteria_use_the_endpoint_and_passenger_count():
    crawler = _crawler(_load("alibaba_train_response.json"))

    await crawler.search_transport(_query(passengers=3))

    url, payload = crawler.client.posts[0]
    assert url.endswith("/api/v1/train/available")
    # The provider rejects criteria without a passenger count
    assert payload["passengerCount"] == 3
    assert payload["origin"] == "THR"
    assert payload["destination"] == "MHD"
    assert payload["departureDate"] == "2026-10-20"


@pytest.mark.asyncio
async def test_train_criteria_response_is_not_read_as_departures():
    """The criteria response is a base64 echo, never a departure list."""
    criteria = _load("alibaba_train_criteria_response.json")
    assert "departing" not in criteria
    assert isinstance(criteria["result"], str)

    body = _load("alibaba_train_response.json")
    assert "departing" in body


@pytest.mark.asyncio
async def test_train_search_failure_raises_rather_than_returning_empty():
    class BrokenPost(StubClient):
        async def post(self, url, json_data=None, **kwargs):
            raise RuntimeError("400 Bad Request")

    crawler = AlibabaCrawler(client=BrokenPost({}, {}))

    with pytest.raises(AlibabaSearchError):
        await crawler.search_transport(_query())


@pytest.mark.asyncio
async def test_same_origin_and_destination_surfaces_the_rejection():
    """Alibaba rejects a journey whose origin equals its destination."""
    rejected = {
        "result": None,
        "success": False,
        "error": {
            "errorCode": 1,
            "message": "مبدا و مقصد یکی هستند",
            "details": "Origin",
            "validationErrors": [],
        },
    }
    crawler = _crawler(_load("alibaba_train_response.json"), criteria_body=rejected)

    with pytest.raises(AlibabaSearchError) as exc:
        await crawler.search_transport(_query(destination="THR"))

    assert "Origin" in str(exc.value)


@pytest.mark.asyncio
async def test_bus_is_not_claimed_by_the_train_implementation(train_payload):
    """Alibaba bus search is not integrated; it must not silently return trains."""
    crawler = _crawler(train_payload)

    with pytest.raises(NotImplementedError):
        await crawler.search_transport(_query(transport_type="bus"))


# --------------------------------------------------------------------- 4.2 mapping


@pytest.mark.asyncio
async def test_every_departure_carries_company_class_and_identity(train_payload):
    crawler = _crawler(train_payload)

    results = await crawler.search_transport(_query())

    assert results
    raw = [i for i in train_payload["departing"] if (i.get("maxPassengerCount") or 0) > 0]
    for r in results:
        assert r.id, "a provider-stable identifier is required"
        assert r.company_name, "operating company must be populated"
        assert r.service_class, "service class must be populated"
        assert r.origin_terminal
        assert r.destination_terminal
        assert r.transport_type == "train"

    assert len(results) == len(raw)


@pytest.mark.asyncio
async def test_departures_of_different_classes_are_not_collapsed(train_payload):
    crawler = _crawler(train_payload)

    results = await crawler.search_transport(_query())

    classes = {r.service_class for r in results}
    raw_classes = {
        (i.get("wagonName") or i.get("wagonClass"))
        for i in train_payload["departing"]
        if (i.get("maxPassengerCount") or 0) > 0
    }
    assert classes == raw_classes


@pytest.mark.asyncio
async def test_departure_identity_is_stable_across_retrievals(train_payload):
    """Two reads of one handle must yield matchable identifiers."""
    crawler = _crawler(train_payload)

    first = await crawler.search_transport(_query())
    second = await crawler.search_transport(_query())

    assert [r.id for r in first] == [r.id for r in second]
    assert len({r.id for r in first}) == len(first)


@pytest.mark.asyncio
async def test_departure_identity_uses_the_provider_proposal_id(train_payload):
    crawler = _crawler(train_payload)
    results = await crawler.search_transport(_query())

    raw_bookable = [i for i in train_payload["departing"] if (i.get("maxPassengerCount") or 0) > 0]
    assert {r.id for r in results} == {str(i["proposalId"]) for i in raw_bookable}


# --------------------------------------------------------------------- 4.3 dates


@pytest.mark.asyncio
async def test_overnight_train_is_not_shown_arriving_before_it_departs(train_payload):
    crawler = _crawler(train_payload)
    results = await crawler.search_transport(_query())

    overnight_raw = [
        i for i in train_payload["departing"]
        if i["departureDateTime"][:10] != i["arrivalDateTime"][:10]
        and (i.get("maxPassengerCount") or 0) > 0
    ]

    for item in overnight_raw:
        match = [r for r in results if r.id == str(item["proposalId"])]
        assert match, "overnight bookable departure must be returned"
        assert match[0].departure_date == item["departureDateTime"][:10]
        assert item["arrivalDateTime"][:10] in match[0].arrival_time
        assert match[0].arrival_time > match[0].departure_date

    # The capture must actually contain overnight journeys for this to mean anything
    any_overnight = [
        i for i in train_payload["departing"]
        if i["departureDateTime"][:10] != i["arrivalDateTime"][:10]
    ]
    assert any_overnight


@pytest.mark.asyncio
async def test_same_day_train_reports_a_bare_arrival_time(train_payload):
    crawler = _crawler(train_payload)
    results = await crawler.search_transport(_query())

    same_day = [
        i for i in train_payload["departing"]
        if i["departureDateTime"][:10] == i["arrivalDateTime"][:10]
        and (i.get("maxPassengerCount") or 0) > 0
    ]
    for item in same_day:
        match = [r for r in results if r.id == str(item["proposalId"])]
        assert match[0].arrival_time == item["arrivalDateTime"][11:16]
        assert len(match[0].arrival_time) == 5, "same-day arrival needs no date prefix"


# --------------------------------------------------------------------- 4.4 price


@pytest.mark.asyncio
async def test_train_prices_are_reported_in_toman(train_payload):
    """
    Alibaba quotes train fares in Toman while quoting flights in Rial.

    Toman is one tenth of a Rial, so mislabelling this is a ten-fold error
    rather than a rounding difference.
    """
    crawler = _crawler(train_payload)
    results = await crawler.search_transport(_query())

    assert results
    for r in results:
        assert r.price.currency == Currency.IRT, (
            f"train price must be Toman, got {r.price.currency}"
        )
        assert "تومان" in (r.price.formatted or "")


@pytest.mark.asyncio
async def test_train_fares_match_the_provider_amount_exactly(train_payload):
    """Pin a named expected value so the unit cannot drift unnoticed."""
    crawler = _crawler(train_payload)
    results = await crawler.search_transport(_query())

    by_id = {r.id: r for r in results}
    raw_bookable = {
        str(i["proposalId"]): i
        for i in train_payload["departing"]
        if (i.get("maxPassengerCount") or 0) > 0
    }

    checked = 0
    for key, item in raw_bookable.items():
        assert by_id[key].price.amount == float(item["cost"])
        checked += 1
    assert checked >= 1

    # Spot-check a literal so a fixture edit cannot silently move the fare
    fares = sorted({i["cost"] for i in raw_bookable.values()})
    assert 7_600_000.0 in fares, "capture should include the cheapest bookable fare"
    match = next(r for r in results if r.price.amount == 7_600_000.0)
    assert match.price.currency == Currency.IRT


@pytest.mark.asyncio
async def test_flight_and_train_prices_carry_different_units(train_payload, flight_payload):
    flight_crawler = AlibabaCrawler(
        client=StubClient(_load("alibaba_flight_criteria_response.json"), flight_payload)
    )
    train_crawler = _crawler(train_payload)

    flights = await flight_crawler.search_flights(
        FlightSearchQuery(origin="MHD", destination="THR", depart_date="2026-10-23")
    )
    trains = await train_crawler.search_transport(_query())

    assert flights and trains
    assert {f.price.currency for f in flights} == {Currency.IRR}
    assert {t.price.currency for t in trains} == {Currency.IRT}
    assert flights[0].price.currency != trains[0].price.currency


# --------------------------------------------------------------------- 4.5 availability


@pytest.mark.asyncio
async def test_zero_capacity_departures_are_excluded(train_payload):
    crawler = _crawler(train_payload)
    results = await crawler.search_transport(_query())

    raw = train_payload["departing"]
    zero = [i for i in raw if (i.get("maxPassengerCount") or 0) == 0]
    bookable = [i for i in raw if (i.get("maxPassengerCount") or 0) > 0]

    assert zero, "capture must contain zero-capacity departures"
    assert len(results) == len(bookable)
    assert len(results) < len(raw)

    returned = {r.id for r in results}
    for item in zero:
        assert str(item["proposalId"]) not in returned


@pytest.mark.asyncio
async def test_bookable_departure_reports_its_capacity(train_payload):
    crawler = _crawler(train_payload)
    results = await crawler.search_transport(_query())

    raw_bookable = {
        str(i["proposalId"]): i
        for i in train_payload["departing"]
        if (i.get("maxPassengerCount") or 0) > 0
    }
    for r in results:
        assert r.available_seats is not None
        assert r.available_seats > 0
        assert r.available_seats == raw_bookable[r.id]["maxPassengerCount"]


@pytest.mark.asyncio
async def test_predominantly_unavailable_search_is_not_an_error(train_payload):
    """A near date where most trains are full must still return the open ones."""
    crawler = _crawler(train_payload)
    results = await crawler.search_transport(_query())

    raw = train_payload["departing"]
    assert (raw.count and sum(1 for i in raw if (i.get("maxPassengerCount") or 0) == 0)) > len(raw) / 2
    assert results, "remaining capacity must still be returned"


@pytest.mark.asyncio
async def test_missing_capacity_field_does_not_drop_the_departure(train_payload):
    payload = json.loads(json.dumps(train_payload))
    for item in payload["departing"]:
        item["maxPassengerCount"] = None

    crawler = _crawler(payload)
    results = await crawler.search_transport(_query())

    assert len(results) == len(payload["departing"])
    for r in results:
        assert r.available_seats is None


# --------------------------------------------------------------------- 4.6 dates input


@pytest.mark.asyncio
async def test_jalali_train_date_is_sent_as_gregorian():
    crawler = _crawler(_load("alibaba_train_response.json"))

    await crawler.search_transport(_query(depart_date="1405-08-01"))

    _, payload = crawler.client.posts[0]
    assert payload["departureDate"] == "2026-10-23"
    assert not payload["departureDate"].startswith("1405")


# --------------------------------------------------------------------- 4.6 routing


def _patch_train_searchers(stack, called):
    """Patch every registered train provider's search_transport to record calls."""
    from app.crawlers.registry import crawler_registry

    for meta in crawler_registry.list_providers():
        name = meta["name"]
        if "train" not in meta["services"]:
            continue
        crawler_cls = crawler_registry._classes[name]

        async def _record(self, query, _name=name):
            called.setdefault(_name, 0)
            called[_name] += 1
            return []

        stack.enter_context(
            patch.object(crawler_cls, "search_transport", _record)
        )
    return called


@pytest.mark.asyncio
async def test_train_search_without_filter_reaches_alibaba(mock_redis):
    """With no provider filter, Alibaba must be queried alongside other train providers."""
    from app.crawlers.orchestrator import CrawlerOrchestrator
    from app.core.redis import CacheManager
    import app.crawlers  # noqa: F401 - registers providers

    called = {}
    with ExitStack() as stack:
        _patch_train_searchers(stack, called)
        orchestrator = CrawlerOrchestrator(cache_manager=CacheManager(client=mock_redis))
        await orchestrator.search_transport(_query(), use_cache=False)

    assert "alibaba" in called, (
        f"Alibaba was not queried for a train search; called: {sorted(called)}"
    )


@pytest.mark.asyncio
async def test_train_search_naming_alibaba_queries_nothing_else(mock_redis):
    from app.crawlers.orchestrator import CrawlerOrchestrator
    from app.core.redis import CacheManager
    import app.crawlers  # noqa: F401

    called = {}
    with ExitStack() as stack:
        _patch_train_searchers(stack, called)
        orchestrator = CrawlerOrchestrator(cache_manager=CacheManager(client=mock_redis))
        await orchestrator.search_transport(_query(providers=["alibaba"]), use_cache=False)

    assert list(called) == ["alibaba"], f"unexpected providers queried: {sorted(called)}"

@pytest.mark.asyncio
async def test_search_trains_sends_resolved_city_codes():
    """Alibaba rejects city names, so names must be resolved to codes before sending."""
    crawler = _crawler(_load("alibaba_train_response.json"))

    await crawler.search_transport(_query(origin="Tehran", destination="Mashhad"))

    _, payload = crawler.client.posts[0]
    assert payload["origin"] == "THR"
    assert payload["destination"] == "MHD"


@pytest.mark.asyncio
async def test_search_trains_accepts_persian_city_names():
    crawler = _crawler(_load("alibaba_train_response.json"))

    await crawler.search_transport(_query(origin="تهران", destination="مشهد"))

    _, payload = crawler.client.posts[0]
    assert payload["origin"] == "THR"
    assert payload["destination"] == "MHD"


@pytest.mark.asyncio
async def test_unresolvable_train_city_fails_loudly():
    """Forwarding an unknown city yields HTTP 400 and a misleading empty list."""
    crawler = _crawler(_load("alibaba_train_response.json"))

    with pytest.raises(ValueError, match="Atlantis"):
        await crawler.search_transport(_query(origin="Atlantis"))

    assert crawler.client.posts == []
