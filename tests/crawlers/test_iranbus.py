import pytest
from unittest.mock import AsyncMock


def _json_response(payload):
    """A mocked client response carrying one JSON body."""
    response = AsyncMock()
    response.json.return_value = payload
    return response


# The provider keys a search by numeric city code, so a search test has to
# answer the directory lookup as well as the search itself.
CITY_DIRECTORY = {
    "status": True,
    "data": [
        {"code": 11320000, "persian_title": "تهران", "lat": "35.70", "long": "51.41"},
        {"code": 31310000, "persian_title": "مشهد", "lat": "36.26", "long": "59.61"},
    ],
}


def _routed_client(search_payload, search_failure=None):
    """
    A client that answers the city directory and defers to the search payload.

    ``search_failure`` stands in for a failing search call - an HTTP rejection
    or an unreachable host - while the directory still answers normally, so a
    failure test exercises the search path rather than the lookup before it.
    """
    client = AsyncMock()

    async def post(url, **kwargs):
        if url.endswith("/api/cities"):
            return _json_response(CITY_DIRECTORY)
        if search_failure is not None:
            raise search_failure
        return _json_response(search_payload)

    client.post.side_effect = post
    return client


def _search_crawler(search_payload, search_failure=None):
    """A crawler whose client serves the given search envelope."""
    from app.crawlers.iranbus.crawler import IranBusCrawler

    crawler = IranBusCrawler()
    client = _routed_client(search_payload, search_failure=search_failure)
    crawler.client = client
    crawler.cities._client = client
    return crawler


def _bus_query():
    from app.schemas.transport import TransportSearchQuery

    return TransportSearchQuery(
        origin="Tehran",
        destination="Mashhad",
        depart_date="2026-10-30",
        transport_type="bus",
    )


from app.crawlers.iranbus.signing import (
    SECRET_KEY,
    SITE_KEY,
    auth_headers,
    make_token,
)


class TestRequestSigning:
    def test_token_has_nonce_dot_and_hash(self):
        token = make_token("/api/cities")
        nonce, _, digest = token.partition(".")
        assert nonce, "token must carry a nonce before the separator"
        assert len(nonce) == 64
        assert len(digest) == 32

    def test_token_is_unique_per_request(self):
        assert make_token("/api/cities") != make_token("/api/cities")

    def test_token_depends_on_the_path_it_signs(self):
        assert make_token("/api/cities") != make_token("/api/services")

    def test_digest_is_hex_with_a_mixed_case_transform(self):
        digest = make_token("/api/services").partition(".")[2]
        assert all(char in "0123456789abcdefABCDEFX" for char in digest)
        # The transform upper-cases every third character, so a 32-character
        # digest must contain at least one upper-case letter.
        assert any(char.isupper() for char in digest)

    def test_digest_is_padded_to_the_provider_width(self):
        # A single "X" filler is only ever added to short digests.
        assert len(make_token("/api/companies").partition(".")[2]) == 32

    def test_auth_headers_carry_both_constants(self):
        headers = auth_headers("/api/services")
        assert headers["site-key"] == SITE_KEY
        assert headers["token"].count(".") == 1
        assert SECRET_KEY  # the digest depends on it

    def test_auth_headers_change_with_the_path(self):
        assert auth_headers("/api/cities")["token"] != auth_headers("/api/terminals")["token"]


class TestProviderDate:
    def test_gregorian_becomes_zero_padded_jalali_with_slashes(self):
        from app.crawlers.iranbus.crawler import to_provider_date

        assert to_provider_date("2026-10-30") == "1405/08/08"

    def test_jalali_input_is_kept_in_jalali(self):
        from app.crawlers.iranbus.crawler import to_provider_date

        assert to_provider_date("1405-08-08") == "1405/08/08"

    def test_single_digit_month_and_day_are_padded(self):
        from app.crawlers.iranbus.crawler import to_provider_date

        result = to_provider_date("1405-1-5")
        assert result == "1405/01/05"

    def test_unusable_date_is_rejected(self):
        from app.crawlers.iranbus.crawler import IranBusSearchError, to_provider_date

        with pytest.raises(IranBusSearchError):
            to_provider_date("not-a-date")

class TestCityResolution:
    @staticmethod
    def _directory():
        return [
            {"code": 11320000, "persian_title": "تهران", "lat": "35.70", "long": "51.41"},
            {"code": 31310000, "persian_title": "مشهد", "lat": "36.26", "long": "59.61"},
            {"code": 21310000, "persian_title": "اصفهان", "lat": "32.65", "long": "51.67"},
        ]

    @staticmethod
    def _directory_crawler():
        from unittest.mock import AsyncMock, patch
        from app.crawlers.iranbus.crawler import IranBusCrawler

        crawler = IranBusCrawler()
        response = AsyncMock()
        response.json.return_value = {"status": True, "data": TestCityResolution._directory()}
        patcher = patch.object(crawler.client, "post", return_value=response)
        return crawler, patcher

    @pytest.mark.asyncio
    async def test_english_name_resolves_to_the_provider_code(self):
        crawler, patcher = self._directory_crawler()
        with patcher:
            assert await crawler.cities.resolve("Tehran") == 11320000
            assert await crawler.cities.resolve("mashhad") == 31310000

    @pytest.mark.asyncio
    async def test_english_name_is_case_insensitive(self):
        crawler, patcher = self._directory_crawler()
        with patcher:
            assert await crawler.cities.resolve("  tEhRaN  ") == 11320000

    @pytest.mark.asyncio
    async def test_persian_name_resolves_directly(self):
        crawler, patcher = self._directory_crawler()
        with patcher:
            assert await crawler.cities.resolve("اصفهان") == 21310000

    @pytest.mark.asyncio
    async def test_provider_code_passes_through_without_a_lookup(self):
        crawler, patcher = self._directory_crawler()
        with patcher:
            assert await crawler.cities.resolve("31310000") == 31310000

    @pytest.mark.asyncio
    async def test_arabic_orthography_folds_onto_persian(self):
        from app.crawlers.iranbus.locations import normalize_city_name

        assert normalize_city_name("كيش") == normalize_city_name("کیش")

    @pytest.mark.asyncio
    async def test_unknown_city_raises_rather_than_returning_nothing(self):
        from app.crawlers.iranbus.locations import IranBusLocationError

        crawler, patcher = self._directory_crawler()
        with patcher:
            with pytest.raises(IranBusLocationError) as excinfo:
                await crawler.cities.resolve("Atlantis")
        assert "Atlantis" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_directory_is_fetched_once_and_then_reused(self):
        from unittest.mock import AsyncMock, patch
        from app.crawlers.iranbus.locations import CityDirectory

        response = AsyncMock()
        response.json.return_value = {"status": True, "data": self._directory()}

        client = AsyncMock()
        client.post.return_value = response
        directory = CityDirectory(client)

        await directory.resolve("Tehran")
        await directory.resolve("Mashhad")
        assert client.post.await_count == 1

    @pytest.mark.asyncio
    async def test_stale_directory_is_refetched(self):
        from unittest.mock import AsyncMock, patch
        from app.crawlers.iranbus.locations import CityDirectory

        response = AsyncMock()
        response.json.return_value = {"status": True, "data": self._directory()}

        client = AsyncMock()
        client.post.return_value = response
        directory = CityDirectory(client, ttl_seconds=0.0)

        await directory.resolve("Tehran")
        await directory.resolve("Tehran")
        assert client.post.await_count == 2


class TestTerminalsAndCompanies:
    @pytest.mark.asyncio
    async def test_terminals_expose_the_documented_fields(self):
        from app.crawlers.iranbus.locations import fetch_terminals

        payload = {
            "status": True,
            "data": [
                {
                    "city": "11320000",
                    "code": "113201",
                    "title": "پایانه غرب تهران (آزادی)",
                    "en_title": "tehran-west",
                    "phone": "021-44663954",
                    "lat": "35.70",
                    "long": "51.33",
                }
            ],
        }
        client = AsyncMock()
        client.post.return_value = _json_response(payload)

        terminals = await fetch_terminals(client)

        assert len(terminals) == 1
        assert terminals[0]["code"] == "113201"
        assert terminals[0]["city"] == "11320000"
        assert terminals[0]["title"].startswith("پایانه غرب")

    @pytest.mark.asyncio
    async def test_companies_expose_slug_source_and_token(self):
        from app.crawlers.iranbus.locations import fetch_companies

        payload = {
            "status": True,
            "data": [
                {
                    "token": "97721-1548",
                    "title": "شرکت آرتا سبلان",
                    "slug": "ARTA",
                    "source": "گرگان",
                    "source_code": "97310000",
                    "phone": "017-32686910",
                }
            ],
        }
        client = AsyncMock()
        client.post.return_value = _json_response(payload)

        companies = await fetch_companies(client)

        assert companies[0]["slug"] == "ARTA"
        assert companies[0]["source_code"] == "97310000"
        assert companies[0]["token"] == "97721-1548"

    @pytest.mark.asyncio
    async def test_directory_requests_are_signed_for_their_own_path(self):
        from app.crawlers.iranbus.locations import fetch_terminals

        client = AsyncMock()
        client.post.return_value = _json_response({"status": True, "data": []})

        await fetch_terminals(client)

        headers = client.post.await_args.kwargs["headers"]
        assert headers["site-key"]
        assert headers["token"].count(".") == 1

    @pytest.mark.asyncio
    async def test_rejected_directory_request_raises(self):
        from app.crawlers.iranbus.locations import IranBusError, fetch_cities

        client = AsyncMock()
        client.post.return_value = _json_response({"status": False, "message": "denied"})

        with pytest.raises(IranBusError):
            await fetch_cities(client)

    @pytest.mark.asyncio
    async def test_directory_envelope_without_a_record_list_raises(self):
        from app.crawlers.iranbus.locations import IranBusError, fetch_cities

        client = AsyncMock()
        client.post.return_value = _json_response({"status": True, "data": {"nope": 1}})

        with pytest.raises(IranBusError):
            await fetch_cities(client)

    @pytest.mark.asyncio
    async def test_transport_failure_names_the_endpoint(self):
        from app.crawlers.iranbus.locations import IranBusError, fetch_companies

        client = AsyncMock()
        client.post.side_effect = RuntimeError("Could not resolve host")

        with pytest.raises(IranBusError) as excinfo:
            await fetch_companies(client)
        assert "companies" in str(excinfo.value)


class TestResultMapping:
    @staticmethod
    def _fixture():
        import json
        from pathlib import Path

        path = Path(__file__).parent.parent / "fixtures" / "iranbus_services_response.json"
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    @pytest.mark.asyncio
    async def test_live_shape_maps_every_documented_field(self):
        from app.crawlers.iranbus.crawler import IranBusCrawler
        from app.schemas.transport import TransportSearchQuery
        from app.schemas.common import Currency

        crawler = _search_crawler(self._fixture())
        results = await crawler.search_transport(_bus_query())

        assert len(results) == 7
        first = results[0]
        assert first.provider.name == "iranbus"
        assert first.transport_type == "bus"
        assert first.company_name
        assert first.service_class
        assert first.origin_terminal
        assert first.destination_terminal
        assert first.departure_time
        assert first.available_seats is not None
        assert first.price.amount > 0
        # The provider quotes rials; the trains in this codebase quote toman.
        assert first.price.currency is Currency.IRR
        assert first.id.startswith("iranbus_")

    @pytest.mark.asyncio
    async def test_departure_date_is_normalized_to_gregorian(self):
        from app.crawlers.iranbus.crawler import IranBusCrawler
        from app.schemas.transport import TransportSearchQuery

        crawler = _search_crawler(self._fixture())
        results = await crawler.search_transport(_bus_query())
        assert results[0].departure_date == "2026-10-30"

    @pytest.mark.asyncio
    async def test_search_sends_codes_and_a_jalali_slash_date(self):
        from app.crawlers.iranbus.crawler import IranBusCrawler
        from app.schemas.transport import TransportSearchQuery

        crawler = _search_crawler(self._fixture())
        await crawler.search_transport(_bus_query())

        payload = crawler.client.post.await_args.kwargs["json_data"]
        assert payload["source"] == "11320000"
        assert payload["destination"] == "31310000"
        assert payload["date"] == "1405/08/08"

    @pytest.mark.asyncio
    async def test_seats_and_price_survive_the_string_encoding(self):
        from app.crawlers.iranbus.crawler import IranBusCrawler
        from app.schemas.transport import TransportSearchQuery

        payload = {
            "status": True,
            "data": {
                "services": [
                    {
                        "token": "1-2",
                        "coName": "Test",
                        "Service_No": "3-4",
                        "Bus_Type": "VIP",
                        "srcCityName": "A",
                        "desCityName": "B",
                        "Depart_Date": "08/08/1405",
                        "Depart_Time": "07:00",
                        "cnt": "16",
                        "Price": "13150000",
                    }
                ]
            },
        }
        crawler = _search_crawler(payload)
        result = (await crawler.search_transport(_bus_query()))[0]
        assert result.available_seats == 16
        assert result.price.amount == 13150000.0

    @pytest.mark.asyncio
    async def test_unparseable_counts_degrade_to_none_not_zero(self):
        from app.crawlers.iranbus.crawler import _to_float, _to_int

        assert _to_int("") is None
        assert _to_int("n/a") is None
        assert _to_float("") is None
        assert _to_float("n/a") is None

    @pytest.mark.asyncio
    async def test_deep_link_points_at_the_provider_service_page(self):
        from app.crawlers.iranbus.crawler import IranBusCrawler
        from app.schemas.transport import TransportSearchQuery

        crawler = _search_crawler(self._fixture())
        result = (await crawler.search_transport(_bus_query()))[0]
        assert result.provider.deep_link.startswith("https://iranbus.ir/bus/show/")

    @pytest.mark.asyncio
    async def test_train_search_is_refused_rather_than_returning_trains(self):
        from app.crawlers.iranbus.crawler import IranBusCrawler
        from app.schemas.transport import TransportSearchQuery

        crawler = IranBusCrawler()
        query = TransportSearchQuery(
            origin="Tehran", destination="Mashhad",
            depart_date="2026-10-30", transport_type="train",
        )
        with pytest.raises(NotImplementedError):
            await crawler.search_transport(query)


class TestFailureSemantics:
    @pytest.mark.asyncio
    async def test_successful_empty_service_list_is_an_empty_answer(self):
        crawler = _search_crawler({"status": True, "data": {"services": []}})
        assert await crawler.search_transport(_bus_query()) == []

    @pytest.mark.asyncio
    async def test_validation_rejection_surfaces_the_provider_messages(self):
        from app.crawlers.iranbus.crawler import IranBusSearchError

        class Rejected(Exception):
            class response:
                status_code = 422

                @staticmethod
                def json():
                    return {"status": False, "messages": {"date": ["تاریخ شمسی معتبر نیست."]}}

        crawler = _search_crawler(
            {"status": True, "data": {"services": []}}, search_failure=Rejected()
        )

        with pytest.raises(IranBusSearchError) as excinfo:
            await crawler.search_transport(_bus_query())
        assert "422" in str(excinfo.value)
        assert "تاریخ" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_unreachable_host_raises_naming_the_endpoint(self):
        from app.crawlers.iranbus.crawler import IranBusSearchError

        crawler = _search_crawler(
            {"status": True, "data": {"services": []}},
            search_failure=RuntimeError("Could not resolve host"),
        )

        with pytest.raises(IranBusSearchError) as excinfo:
            await crawler.search_transport(_bus_query())
        assert "services" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_unsuccessful_envelope_raises_instead_of_returning_nothing(self):
        from app.crawlers.iranbus.crawler import IranBusSearchError

        crawler = _search_crawler({"status": False, "message": "blocked"})
        with pytest.raises(IranBusSearchError) as excinfo:
            await crawler.search_transport(_bus_query())
        assert "blocked" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_envelope_without_a_data_object_raises(self):
        from app.crawlers.iranbus.crawler import IranBusSearchError

        crawler = _search_crawler({"status": True})
        with pytest.raises(IranBusSearchError):
            await crawler.search_transport(_bus_query())

    @pytest.mark.asyncio
    async def test_envelope_without_a_service_list_raises(self):
        from app.crawlers.iranbus.crawler import IranBusSearchError

        crawler = _search_crawler({"status": True, "data": {"count": 0}})
        with pytest.raises(IranBusSearchError):
            await crawler.search_transport(_bus_query())

    @pytest.mark.asyncio
    async def test_search_body_that_is_not_an_object_raises(self):
        from app.crawlers.iranbus.crawler import IranBusSearchError

        # A body that decodes to a list, or to nothing, is a broken exchange
        # rather than an empty route.
        crawler = _search_crawler([])

        with pytest.raises(IranBusSearchError):
            await crawler.search_transport(_bus_query())

    @pytest.mark.asyncio
    async def test_malformed_service_entries_are_skipped_not_fatal(self):
        crawler = _search_crawler(
            {
                "status": True,
                "data": {
                    "services": [
                        "not-an-object",
                        {
                            "token": "1-2",
                            "Service_No": "3-4",
                            "coName": "Test",
                            "Bus_Type": "VIP",
                            "srcCityName": "A",
                            "desCityName": "B",
                            "Depart_Time": "07:00",
                            "cnt": "5",
                            "Price": "100",
                        },
                    ]
                },
            }
        )
        results = await crawler.search_transport(_bus_query())
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_unknown_city_fails_the_search_loudly(self):
        from app.crawlers.iranbus.locations import IranBusLocationError
        from app.schemas.transport import TransportSearchQuery

        crawler = _search_crawler({"status": True, "data": {"services": []}})
        query = TransportSearchQuery(
            origin="Atlantis",
            destination="Mashhad",
            depart_date="2026-10-30",
            transport_type="bus",
        )
        with pytest.raises(IranBusLocationError):
            await crawler.search_transport(query)


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy_when_the_directory_answers(self):
        from app.crawlers.iranbus.crawler import IranBusCrawler

        crawler = IranBusCrawler()
        client = AsyncMock()
        client.post.return_value = _json_response(CITY_DIRECTORY)
        crawler.client = client
        crawler.cities._client = client

        assert await crawler.health_check() is True

    @pytest.mark.asyncio
    async def test_unhealthy_when_the_provider_cannot_be_reached(self):
        from app.crawlers.iranbus.crawler import IranBusCrawler

        crawler = IranBusCrawler()
        client = AsyncMock()
        client.post.side_effect = RuntimeError("Could not resolve host")
        crawler.client = client
        crawler.cities._client = client

        assert await crawler.health_check() is False

    @pytest.mark.asyncio
    async def test_unhealthy_when_the_directory_comes_back_empty(self):
        from app.crawlers.iranbus.crawler import IranBusCrawler

        crawler = IranBusCrawler()
        client = AsyncMock()
        client.post.return_value = _json_response({"status": True, "data": []})
        crawler.client = client
        crawler.cities._client = client

        assert await crawler.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_refetches_rather_than_trusting_a_warm_cache(self):
        from app.crawlers.iranbus.crawler import IranBusCrawler

        crawler = IranBusCrawler()
        client = AsyncMock()
        client.post.return_value = _json_response(CITY_DIRECTORY)
        crawler.client = client
        crawler.cities._client = client

        assert await crawler.health_check() is True
        assert await crawler.health_check() is True
        assert client.post.await_count == 2


class TestProviderRegistration:
    def test_registered_under_the_bus_subtype_not_transport(self):
        from app.crawlers.registry import crawler_registry
        from app.crawlers.iranbus.crawler import IranBusCrawler

        assert IranBusCrawler.supported_services == {"bus"}
        crawler = crawler_registry.get_crawler("iranbus")
        assert crawler is not None
        assert crawler.supports_service("bus")
        # The orchestrator dispatches on the subtype, so declaring "transport"
        # would leave this provider unreachable - the defect Safarchin has.
        assert not crawler.supports_service("transport")

    def test_cacheable_under_the_default_ttl_policy(self):
        from app.crawlers.iranbus.crawler import IranBusCrawler

        assert IranBusCrawler.is_cacheable is True
