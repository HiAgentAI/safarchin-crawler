"""
Tests for Alibaba city resolution.

Alibaba rejects anything that is not an exact IATA code, so these cover the
translation from the city names this API accepts into the codes the provider
requires.
"""

import pytest

from app.crawlers.alibaba.locations import to_alibaba_city_code


@pytest.mark.parametrize(
    "supplied,expected",
    [
        # Already a code: passed through untouched
        ("THR", "THR"),
        ("MHD", "MHD"),
        ("IKA", "IKA"),
        # The documented city names
        ("Mashhad", "MHD"),
        ("Isfahan", "IFN"),
        ("Shiraz", "SYZ"),
        ("Tabriz", "TBZ"),
        ("Kish", "KIH"),
        ("Gorgan", "GBT"),
        ("Yazd", "AZD"),
        # Persian names
        ("مشهد", "MHD"),
        ("اصفهان", "IFN"),
        # Tehran is the interesting case: see below
        ("Tehran", "THR"),
        ("tehran", "THR"),
        ("THR ", "THR"),
    ],
)
def test_city_names_resolve_to_codes_alibaba_accepts(supplied, expected):
    assert to_alibaba_city_code(supplied) == expected


def test_tehran_maps_to_thr_not_ika():
    """
    The shared airport data resolves "Tehran" to IKA, which Alibaba rejects.

    ``airports.py`` indexes English names by slug and two of its entries share
    the slug ``Tehran``; the later (IKA) overwrites the earlier (THR). Alibaba
    uses THR for the city, so the name is mapped explicitly.
    """
    from app.crawlers.safarchin.airports import find_airport

    # The underlying data really does resolve to IKA ...
    assert find_airport("Tehran").iata == "IKA"
    # ... but the Alibaba resolver must not use that
    assert to_alibaba_city_code("Tehran") == "THR"


def test_an_explicit_ika_request_is_not_rewritten_to_thr():
    """Someone asking for Imam Khomaini by code still gets IKA."""
    assert to_alibaba_city_code("IKA") == "IKA"
    assert to_alibaba_city_code("Imam Khomaini") == "IKA"


def test_lowercase_codes_resolve_to_uppercase():
    """A lowercase code is accepted and normalised, via the IATA lookup."""
    assert to_alibaba_city_code("mhd") == "MHD"
    assert to_alibaba_city_code("thr") == "THR"


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_missing_city_is_reported_clearly(bad):
    with pytest.raises(ValueError):
        to_alibaba_city_code(bad)


def test_unknown_city_raises_with_an_actionable_message():
    with pytest.raises(ValueError) as exc:
        to_alibaba_city_code("Nowherevilletta", field="origin")

    message = str(exc.value)
    assert "origin" in message
    assert "Nowherevilletta" in message
    # The message should tell the caller what to do instead
    assert "IATA" in message


def test_unknown_city_is_not_silently_sent_to_the_provider():
    """
    An unresolvable city must fail loudly.

    Sending it through produces HTTP 400 from Alibaba, which the orchestrator
    reports as an empty result list - indistinguishable from no availability.
    """
    with pytest.raises(ValueError):
        to_alibaba_city_code("Atlantis")