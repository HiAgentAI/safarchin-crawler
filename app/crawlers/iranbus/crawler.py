"""
Crawler adapter for iranbus.ir, the national bus cooperatives union.

The provider exposes a small JSON API rather than a page to scrape: a search
needs numeric city codes and a Jalali date, and it answers with the operator's
own service list - company, bus class, departure time, terminal, remaining
seats and price.

Two things differ from the rest of the providers here and drive the shape of
this module. The date is Jalali and must be zero-padded with slashes
(``1405/08/08``); dash-separated and Gregorian values are rejected. And every
request must be signed, which :mod:`app.crawlers.iranbus.signing` handles.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.crawlers.base import BaseCrawler
from app.crawlers.iranbus.locations import (
    CityDirectory,
    IranBusError,
    describe_http_error,
)
from app.crawlers.iranbus.signing import auth_headers
from app.crawlers.registry import register_crawler
from app.schemas.common import Currency, PriceInfo, ProviderInfo
from app.schemas.transport import TransportResult, TransportSearchQuery
from app.utils.calendar import to_gregorian, to_jalali
from app.utils.http_client import ResilientHttpClient

logger = logging.getLogger(__name__)

BASE_URL = "https://iranbus.ir"
SERVICES_PATH = "/api/services"


class IranBusSearchError(IranBusError):
    """Raised when an iranbus.ir search cannot be completed."""


def to_provider_date(depart_date: str) -> str:
    """
    Convert a caller date into the form the provider accepts.

    The provider validates the Jalali calendar itself and answers
    ``تاریخ شمسی معتبر نیست`` for anything else, so the conversion has to
    happen here rather than being left to the provider to guess. Callers pass
    either a Gregorian or a Jalali date; ``to_jalali`` accepts both and
    zero-pads the result, after which only the separator changes.
    """
    try:
        jalali = to_jalali(depart_date)
    except Exception as exc:
        raise IranBusSearchError(f"Unusable departure date {depart_date!r}: {exc}") from exc
    return jalali.replace("-", "/")


def _to_int(value: Any) -> Optional[int]:
    """Read a count that the provider sends as a string."""
    if value is None or value == "":
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> Optional[float]:
    """Read an amount that the provider sends as a string."""
    if value is None or value == "":
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


@register_crawler(name="iranbus", services={"bus"})
class IranBusCrawler(BaseCrawler):
    """
    Intercity bus departures from iranbus.ir.

    Registered under ``bus`` rather than ``transport`` because the orchestrator
    dispatches ground transport on the requested subtype, so a provider is only
    reached for a bus search if it declares the ``bus`` service itself.
    """

    provider_name = "iranbus"
    supported_services = {"bus"}

    def __init__(self, client: Optional[ResilientHttpClient] = None):
        self.client = client or ResilientHttpClient(
            impersonate="chrome120",
            timeout=15.0,
            retries=2,
        )
        self.cities = CityDirectory(self.client)

    async def search_transport(self, query: TransportSearchQuery) -> List[TransportResult]:
        """
        Search intercity bus services for one route and date.

        A search that cannot be completed raises. The orchestrator isolates
        per-provider failures, so an unreachable provider costs the caller its
        own rows and nothing else - whereas an empty list here would be
        reported to the caller as "there are no buses on that date", which is
        the one answer this provider must never invent.
        """
        transport_type = query.transport_type.lower()
        if transport_type != "bus":
            raise NotImplementedError(
                f"iranbus.ir does not provide {transport_type} search; only bus is integrated"
            )

        source_code = await self.cities.resolve(query.origin)
        destination_code = await self.cities.resolve(query.destination)
        payload = {
            "source": str(source_code),
            "destination": str(destination_code),
            "date": to_provider_date(query.depart_date),
        }

        body = await self._post_search(payload)
        return self._parse_services(body)

    async def _post_search(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send one signed search request and return the decoded envelope."""
        url = f"{BASE_URL}{SERVICES_PATH}"
        try:
            response = await self.client.post(
                url=url,
                json_data=payload,
                headers=auth_headers(SERVICES_PATH),
            )
        except Exception as exc:
            # The client raises on a non-2xx response, which is how a rejected
            # search arrives here; its body carries the provider's explanation.
            raise IranBusSearchError(
                f"iranbus.ir rejected the search for {payload['source']}->"
                f"{payload['destination']} on {SERVICES_PATH}: {describe_http_error(exc)}"
            ) from exc

        body = await _as_dict(response)
        if not body:
            raise IranBusSearchError("iranbus.ir returned an undecodable search response")

        if body.get("status") is not True:
            message = body.get("message") or body.get("messages") or "no reason given"
            raise IranBusSearchError(f"iranbus.ir reported the search as unsuccessful: {message}")

        return body

    def _parse_services(self, body: Dict[str, Any]) -> List[TransportResult]:
        """
        Map the service list onto transport results.

        An empty list is a legitimate answer: the route exists on that date but
        has nothing left to sell. A missing or non-list service collection is
        not - that means the envelope is not what it claims to be.
        """
        data = body.get("data")
        if not isinstance(data, dict):
            raise IranBusSearchError("iranbus.ir search response carried no data object")

        services = data.get("services")
        if not isinstance(services, list):
            raise IranBusSearchError("iranbus.ir search response carried no service list")

        scraped_at = datetime.utcnow().isoformat()
        results: List[TransportResult] = []
        for service in services:
            if not isinstance(service, dict):
                logger.warning("Skipping malformed iranbus.ir service entry: %r", service)
                continue
            results.append(self._to_result(service, scraped_at))
        return results

    def _to_result(self, service: Dict[str, Any], scraped_at: str) -> TransportResult:
        """Build one result from a provider service record."""
        token = str(service.get("token") or "")
        service_no = str(service.get("Service_No") or "")
        amount = _to_float(service.get("Price"))

        # The provider quotes rials, unlike the trains and hotels in this
        # codebase that quote toman; the two differ by ten.
        price = PriceInfo(
            amount=amount if amount is not None else 0.0,
            currency=Currency.IRR,
            formatted=f"{int(amount or 0):,} ریال",
        )

        # The provider reports the Jalali date it was asked about, so the result
        # is normalized back to the Gregorian form the other providers use.
        departure_date = query_safe_gregorian(service.get("Depart_Date"))

        return TransportResult(
            id=f"iranbus_{token}_{service_no}".strip("_"),
            provider=ProviderInfo(
                name=self.provider_name,
                deep_link=_deep_link(service_no, token),
                scraped_at=scraped_at,
            ),
            transport_type="bus",
            company_name=service.get("coName") or "Unknown",
            service_class=service.get("Bus_Type") or "Standard",
            origin_terminal=service.get("srcCityName") or "",
            destination_terminal=service.get("desCityName") or "",
            departure_date=departure_date,
            departure_time=service.get("Depart_Time") or "",
            # The provider does not report an arrival time for intercity buses.
            arrival_time=None,
            price=price,
            available_seats=_to_int(service.get("cnt")),
        )

    async def get_terminals(self) -> List[Dict[str, Any]]:
        """List the provider's terminals."""
        from app.crawlers.iranbus.locations import fetch_terminals

        return await fetch_terminals(self.client)

    async def get_companies(self) -> List[Dict[str, Any]]:
        """List the bus companies the provider sells for."""
        from app.crawlers.iranbus.locations import fetch_companies

        return await fetch_companies(self.client)

    async def get_cities(self, province_id: Optional[str] = None) -> list:
        """List the provider's cities, optionally filtered by province code."""
        cities = await self.cities.load()
        if province_id is None:
            return cities
        return [city for city in cities if str(city.get("code", "")).startswith(str(province_id))]

    async def health_check(self) -> bool:
        """
        Report whether the provider is reachable.

        The city directory is the cheapest call that still proves both that
        the host answers and that the signing still works - a rotated key or a
        changed envelope shows up here rather than as an empty search.
        """
        try:
            cities = await self.cities.load(force=True)
            return bool(cities)
        except Exception as exc:
            logger.warning("iranbus.ir health check failed: %s", exc)
            return False

    async def close(self):
        """Release the underlying HTTP session."""
        if self.client:
            await self.client.close()


async def _as_dict(response: Any) -> Dict[str, Any]:
    """Decode a JSON object body, tolerating a client that returns a coroutine."""
    import asyncio

    data = response.json() if hasattr(response, "json") else response
    if asyncio.iscoroutine(data):
        data = await data
    return data if isinstance(data, dict) else {}


def query_safe_gregorian(jalali_date: Any) -> str:
    """
    Convert a provider date to Gregorian, passing an unusable value through.

    The provider answers with ``MM/DD/YYYY`` in Jalali. A record that arrives
    without one is still worth returning, so an unusable value is reported as
    the string the provider sent rather than dropped.
    """
    if not jalali_date:
        return ""
    text = str(jalali_date)
    parts = [part for part in text.replace("-", "/").split("/") if part]
    if len(parts) != 3:
        return text
    month, day, year = parts
    try:
        return to_gregorian(f"{year}-{month}-{day}")
    except Exception:
        return text


def _deep_link(service_no: str, token: str) -> Optional[str]:
    """Build the provider's own page for a service, when its parts are present."""
    if service_no and token:
        return f"{BASE_URL}/bus/show/{service_no}/{token}"
    return f"{BASE_URL}/bus"