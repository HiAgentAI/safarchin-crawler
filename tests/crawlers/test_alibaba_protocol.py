"""
Tests for the Alibaba two-phase search protocol.

These use the captured payloads in tests/fixtures/ so that a change in the real
provider shape fails here rather than silently yielding empty results.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.crawlers.alibaba.protocol import (
    AlibabaSearchError,
    extract_encoded_handle,
    extract_request_id,
    provider_error_message,
    two_phase_search,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES_DIR / name) as fh:
        return json.load(fh)


@pytest.fixture
def flight_criteria():
    return _load("alibaba_flight_criteria_response.json")


@pytest.fixture
def flight_results():
    return _load("alibaba_flight_response.json")


@pytest.fixture
def train_criteria():
    return _load("alibaba_train_criteria_response.json")


@pytest.fixture
def train_results():
    return _load("alibaba_train_response.json")


def _response(body):
    resp = AsyncMock()
    resp.json.return_value = body
    return resp


class StubClient:
    """Records verb order and returns queued responses."""

    def __init__(self, post_body, get_body):
        self._post_body = post_body
        self._get_body = get_body
        self.calls = []

    async def post(self, url, json_data=None, **kwargs):
        self.calls.append(("POST", url, json_data))
        return _response(self._post_body)

    async def get(self, url, params=None, headers=None, **kwargs):
        self.calls.append(("GET", url, None))
        return _response(self._get_body)


@pytest.mark.asyncio
async def test_two_phase_search_uses_post_then_get(flight_criteria, flight_results):
    client = StubClient(flight_criteria, flight_results)

    body = await two_phase_search(client, "https://ws.alibaba.ir/api/v1/flights/domestic/available", {"origin": "THR"})

    assert [c[0] for c in client.calls] == ["POST", "GET"], (
        "Alibaba requires POST for criteria and GET for the handle; "
        "a GET-first client gets 405 Method Not Allowed"
    )
    assert body is flight_results
    assert len(body["result"]["departing"]) > 0


@pytest.mark.asyncio
async def test_two_phase_search_fetches_the_handle_from_the_criteria_response(flight_criteria, flight_results):
    client = StubClient(flight_criteria, flight_results)
    handle = flight_criteria["result"]["requestId"]

    await two_phase_search(client, "https://ws.alibaba.ir/api/v1/flights/domestic/available", {"origin": "THR"})

    get_url = client.calls[1][1]
    assert get_url.endswith(f"/{handle}")
    assert handle in get_url


@pytest.mark.asyncio
async def test_two_phase_search_never_treats_criteria_response_as_results(flight_criteria, flight_results):
    """
    The criteria response carries a handle, not flights.

    Reading it as a result set is the original defect: it looks successful and
    yields zero flights.
    """
    assert "departing" not in flight_criteria["result"]
    assert "departing" in flight_results["result"]

    client = StubClient(flight_criteria, flight_results)
    body = await two_phase_search(client, "https://x/api/v1/flights/domestic/available", {})

    assert len(body["result"]["departing"]) > 0


@pytest.mark.asyncio
async def test_two_phase_search_uses_encoded_handle_for_trains(train_criteria, train_results):
    client = StubClient(train_criteria, train_results)

    body = await two_phase_search(
        client,
        "https://ws.alibaba.ir/api/v1/train/available",
        {"origin": "THR"},
        extract_handle=extract_encoded_handle,
    )

    assert [c[0] for c in client.calls] == ["POST", "GET"]
    assert train_criteria["result"] in client.calls[1][1]
    assert len(body["departing"]) > 0


@pytest.mark.asyncio
async def test_two_phase_search_sends_the_criteria_payload(flight_criteria, flight_results):
    client = StubClient(flight_criteria, flight_results)
    payload = {"origin": "THR", "destination": "MHD", "departureDate": "2026-10-23"}

    await two_phase_search(client, "https://x/api/v1/flights/domestic/available", payload)

    assert client.calls[0][2] == payload


@pytest.mark.asyncio
async def test_missing_handle_raises_instead_of_returning_empty(flight_results):
    """A criteria response with no handle must not become an empty result set."""
    criteria = {"success": True, "result": {"bannerId": "General"}}
    client = StubClient(criteria, flight_results)

    with pytest.raises(AlibabaSearchError, match="no search handle"):
        await two_phase_search(client, "https://x/api/v1/flights/domestic/available", {})


@pytest.mark.asyncio
async def test_result_retrieval_failure_raises(flight_criteria):
    class FailingGet(StubClient):
        async def get(self, url, params=None, headers=None, **kwargs):
            raise RuntimeError("connection reset")

    client = FailingGet(flight_criteria, {})

    with pytest.raises(AlibabaSearchError, match="result retrieval failed"):
        await two_phase_search(client, "https://x/api/v1/flights/domestic/available", {})


@pytest.mark.asyncio
async def test_criteria_post_failure_raises():
    class FailingPost(StubClient):
        async def post(self, url, json_data=None, **kwargs):
            raise RuntimeError("boom")

    client = FailingPost({}, {})

    with pytest.raises(AlibabaSearchError, match="criteria request failed"):
        await two_phase_search(client, "https://x/api/v1/flights/domestic/available", {})


def test_provider_rejects_aspnet_style_error():
    """Flights and trains answer with an ASP.NET envelope on failure."""
    body = {
        "result": None,
        "success": False,
        "error": {
            "errorCode": 1,
            "message": "تاریخ رفت خالی است.",
            "details": "DepartureDate",
            "validationErrors": [],
        },
    }
    msg = provider_error_message(body)
    assert msg is not None
    assert "DepartureDate" in msg


def test_provider_rejects_go_style_error():
    """Hotels answer with a Go-style envelope; both shapes must be recognised."""
    body = {"status": "error", "message": "city id is not valid probably", "error": True}
    assert "city id is not valid" in provider_error_message(body)


def test_provider_flags_unauthorized_request():
    assert provider_error_message({"unauthorizedRequest": True}) is not None


def test_provider_accepts_good_responses(flight_criteria, train_criteria, flight_results):
    assert provider_error_message(flight_criteria) is None
    assert provider_error_message(train_criteria) is None
    assert provider_error_message(flight_results) is None


def test_handle_extractors_are_service_specific(flight_criteria, train_criteria):
    flight_handle = extract_request_id(flight_criteria)
    train_handle = extract_encoded_handle(train_criteria)

    assert flight_handle and flight_handle == flight_criteria["result"]["requestId"]
    # A flight criteria response has no plain-string result for the train extractor
    assert extract_encoded_handle(flight_criteria) is None
    # ...and vice versa
    assert extract_request_id(train_criteria) is None
    assert train_handle and train_handle == train_criteria["result"]


# The field names the parsers depend on. If Alibaba renames one of these, these
# tests fail loudly instead of the crawler silently returning nothing.
FLIGHT_MAPPING_FIELDS = [
    "uniqueKey",
    "airlineCode",
    "airlineName",
    "flightNumber",
    "aircraft",
    "classType",
    "leaveDateTime",
    "arrivalDateTime",
    "priceAdult",
    "isCharter",
    "seat",
    "status",
    "statusName",
    "origin",
    "destination",
]

TRAIN_MAPPING_FIELDS = [
    "proposalId",
    "trainNumber",
    "wagonClass",
    "wagonName",
    "companyName",
    "originCode",
    "destinationCode",
    "departureDateTime",
    "arrivalDateTime",
    "cost",
    "maxPassengerCount",
    "minPassengerCount",
]


@pytest.mark.parametrize("field", FLIGHT_MAPPING_FIELDS)
def test_captured_flight_payload_exposes_every_mapped_field(flight_results, field):
    """Each mapped field exists on every captured flight."""
    departing = flight_results["result"]["departing"]
    assert departing, "captured flight payload has no departing flights"
    missing = [i.get("uniqueKey") for i in departing if field not in i]
    assert not missing, f"Alibaba flight field {field!r} missing from {len(missing)} flights: {missing[:3]}"


@pytest.mark.parametrize("field", TRAIN_MAPPING_FIELDS)
def test_captured_train_payload_exposes_every_mapped_field(train_results, field):
    """Each mapped field exists on every captured departure."""
    departing = train_results["departing"]
    assert departing, "captured train payload has no departing services"
    missing = [i.get("proposalId") for i in departing if field not in i]
    assert not missing, f"Alibaba train field {field!r} missing from {len(missing)} departures: {missing[:3]}"


def test_captured_flight_fixture_is_not_self_invented(flight_results):
    """
    Guard against a hand-authored fixture that can never disagree with the code.

    The original fixture used "alibaba_fl_101" as both the payload value and the
    test's expected value, so no assertion could ever fail. These checks confirm
    the fixture carries real provider-shaped data.
    """
    departing = flight_results["result"]["departing"]
    keys = [i["uniqueKey"] for i in departing]

    assert not any(k.startswith("alibaba_fl_") for k in keys), (
        "fixture uniqueKey values look invented rather than captured"
    )
    # Real keys embed the route, date, carrier and fare.
    assert all(k.startswith("MHDTHR") for k in keys), f"unexpected uniqueKey shape: {keys[:2]}"
    assert len(set(keys)) == len(keys), "uniqueKey values must be distinct per flight"


def test_captured_fixtures_cover_the_vocabulary_the_parsers_normalize(flight_results, train_results):
    """
    The captures must exercise the normalisation and filtering paths.

    Without these the parser tests would pass vacuously on a single-format sample.
    """
    departing = flight_results["result"]["departing"]

    assert len({i["aircraft"] for i in departing}) > 1, "expected varied aircraft designations"
    assert {i["classType"] for i in departing} >= {"E"}, "expected economy cabin codes"
    assert any(i["statusName"] for i in departing), "expected at least one populated statusName"
    assert any(
        i["leaveDateTime"][:10] != i["arrivalDateTime"][:10] for i in departing
    ), "expected at least one overnight arrival"

    trains = train_results["departing"]
    assert len({i["wagonClass"] for i in trains}) > 1, "expected varied wagon classes"
    assert any((i["maxPassengerCount"] or 0) == 0 for i in trains), "expected a zero-capacity departure"
    assert any((i["maxPassengerCount"] or 0) > 0 for i in trains), "expected a bookable departure"
    assert any(
        i["departureDateTime"][:10] != i["arrivalDateTime"][:10] for i in trains
    ), "expected at least one overnight train"