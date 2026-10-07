"""
Reference data for the iranbus.ir provider: cities, terminals and companies.

The provider keys a search by numeric city code, so a caller who asks for
``Tehran -> Mashhad`` needs those names translated into the provider's own
codes. The directory is fetched once and cached for a TTL, because it is large
(roughly 690 cities) but changes rarely, and it is the single source of truth
for which codes are valid.

City names arrive in both languages. The provider publishes Persian titles,
callers in this codebase pass English names, so an alias table bridges the two
and the directory itself settles the rest.
"""

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional

from app.crawlers.iranbus.signing import auth_headers

logger = logging.getLogger(__name__)

CITIES_PATH = "/api/cities"
TERMINALS_PATH = "/api/terminals"
COMPANIES_PATH = "/api/companies"

# Cache the directory rather than refetching it on every search: it is a whole
# country-wide list, and one search may need two lookups from it.
DIRECTORY_TTL_SECONDS = 86400.0

# Persian names differ from English ones, and callers may use either the
# transliterated city name or a common English variant.
CITY_ALIASES: Dict[str, str] = {
    "tehran": "تهران",
    "teheran": "تهران",
    "mashhad": "مشهد",
    "mashad": "مشهد",
    "meshad": "مشهد",
    "isfahan": "اصفهان",
    "esfahan": "اصفهان",
    "isphan": "اصفهان",
    "shiraz": "شیراز",
    "tabriz": "تبریز",
    "karaj": "کرج",
    "qom": "قم",
    "rasht": "رشت",
    "ahvaz": "اهواز",
    "kermanshah": "کرمانشاه",
    "keramanshah": "کرمانشاه",
    "urmia": "ارومیه",
    "orumia": "ارومیه",
    "urumia": "ارومیه",
    "zahedan": "زاهدان",
    "yazd": "یزد",
    "ardabil": "اردبیل",
    "bushehr": "بوشهر",
    "kerman": "کرمان",
    "arak": "اراک",
    "sari": "ساری",
    "gorgan": "گرگان",
    "sanandaj": "سنندج",
    "qazvin": "قزوین",
    "hamadan": "همدان",
    "hamedan": "همدان",
    "birjand": "بیرجند",
    "bojnord": "بجنورد",
    "bojnurd": "بجنورد",
    "ilam": "ایلام",
    "yasuj": "یاسوج",
    "semnan": "سمنان",
    "zanjan": "زنجان",
    "abadan": "آبادان",
    "bandar abbas": "بندرعباس",
    "bandare abbas": "بندرعباس",
    "bandar-abbas": "بندرعباس",
    "babol": "بابل",
    "amol": "آمل",
    "chalus": "چالوس",
    "ramsar": "رامسر",
    "behshahr": "بهشهر",
    "shahrekord": "شهرکرد",
    "khorramabad": "خرم آباد",
    "qaemshahr": "قائم شهر",
    "gomishan": "گومیشان",
    "sirjan": "سیرجان",
    "rafsanjan": "رفسنجان",
    "borujerd": "بروجرد",
    "malayer": "ملایر",
    "neyriz": "نی ریز",
    "kasr shirin": "قصر شیرین",
    "shush": "شوش",
    "dehloran": "دهلران",
    "andimeshk": "اندیمشک",
    "saveh": "ساوه",
    "kashmar": "کاشمر",
    "neyshabur": "نیشابور",
    "bam": "بم",
    "jask": "جاسک",
    "minab": "میناب",
    "chabahar": "چابهار",
    "iranshahr": "ایرانشهر",
    "bandar lengeh": "بندر لنگه",
    "kish": "کیش",
    "qeshm": "قشم",
    "zabol": "زابل",
    "saravan": "ساروان",
}

# Arabic and Persian orthography share letters that differ only in code point,
# and city names may carry a zero-width non-joiner. Normalizing both makes
# "کیش" and "کيش" - and "قائم‌شهر" and "قائم شهر" - compare equal.
_TRANSLITERATION_MAP = str.maketrans({
    "ي": "ی",
    "ى": "ی",
    "ك": "ک",
    "‌": " ",
})
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class IranBusError(RuntimeError):
    """Base error for anything that goes wrong talking to iranbus.ir."""


class IranBusLocationError(IranBusError):
    """Raised when a requested city cannot be resolved to a provider code."""


def normalize_city_name(name: str) -> str:
    """Fold orthography and case so equivalent spellings compare equal."""
    folded = str(name).translate(_TRANSLITERATION_MAP).translate(_DIGIT_MAP)
    return re.sub(r"\s+", " ", folded).strip().lower()


async def _as_dict(response: Any) -> Dict[str, Any]:
    """Decode a JSON object body, tolerating a client that returns a coroutine."""
    data = response.json() if hasattr(response, "json") else response
    if asyncio.iscoroutine(data):
        data = await data
    return data if isinstance(data, dict) else {}


def describe_http_error(exc: Exception) -> str:
    """
    Turn an HTTP failure into a message that names the status and, when the
    provider supplied one, its own explanation of what was wrong.
    """
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None) or getattr(exc, "status_code", None)
    detail = getattr(exc, "detail", None) or str(exc)

    if response is not None:
        body = None
        try:
            body = response.json()
        except Exception:
            text = getattr(response, "text", None)
            body = text if isinstance(text, str) else None

        if isinstance(body, dict):
            messages = body.get("messages")
            if isinstance(messages, dict):
                detail = "; ".join(f"{field}: {value}" for field, value in messages.items())
            elif body.get("message"):
                detail = str(body["message"])

    return f"HTTP {status}: {detail}" if status else str(detail)


async def post_api(client, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    POST a signed request to the iranbus.ir API and return the decoded envelope.

    A non-JSON or failed response raises :class:`IranBusError` rather than
    returning an empty envelope, so callers cannot mistake a broken request for
    an empty answer.
    """
    url = f"https://iranbus.ir{path}"
    try:
        response = await client.post(
            url=url,
            json_data=payload if payload is not None else {},
            headers=auth_headers(path),
        )
    except Exception as exc:
        raise IranBusError(f"iranbus.ir request to {path} failed: {describe_http_error(exc)}") from exc

    body = await _as_dict(response)
    if not body:
        raise IranBusError(f"iranbus.ir returned an undecodable response for {path}")
    return body


def _extract_records(body: Dict[str, Any], path: str) -> List[Dict[str, Any]]:
    """Pull the record list out of a directory envelope, rejecting malformed ones."""
    if body.get("status") is not True:
        raise IranBusError(
            f"iranbus.ir rejected the {path} request: {describe_http_error(RuntimeError(body.get('message')))}"
        )
    records = body.get("data")
    if not isinstance(records, list):
        raise IranBusError(f"iranbus.ir returned no record list for {path}")
    return records


async def fetch_cities(client) -> List[Dict[str, Any]]:
    """Fetch the provider's city directory."""
    return _extract_records(await post_api(client, CITIES_PATH), CITIES_PATH)


async def fetch_terminals(client) -> List[Dict[str, Any]]:
    """Fetch the provider's terminal directory."""
    return _extract_records(await post_api(client, TERMINALS_PATH), TERMINALS_PATH)


async def fetch_companies(client) -> List[Dict[str, Any]]:
    """Fetch the provider's bus company directory."""
    return _extract_records(await post_api(client, COMPANIES_PATH), COMPANIES_PATH)


class CityDirectory:
    """
    TTL-cached view over the provider's city directory.

    Resolution accepts a numeric code, a Persian name, or an English name from
    the alias table, and raises :class:`IranBusLocationError` for anything it
    cannot map, so an unresolvable city fails loudly instead of searching for
    nothing and reporting an empty result.
    """

    def __init__(self, client, ttl_seconds: float = DIRECTORY_TTL_SECONDS):
        self._client = client
        self._ttl_seconds = ttl_seconds
        self._cities: List[Dict[str, Any]] = []
        self._loaded_at: float = 0.0

    def _is_fresh(self) -> bool:
        return bool(self._cities) and (time.monotonic() - self._loaded_at) < self._ttl_seconds

    async def load(self, force: bool = False) -> List[Dict[str, Any]]:
        """Return the city records, fetching them if the cache is cold or stale."""
        if force or not self._is_fresh():
            self._cities = await fetch_cities(self._client)
            self._loaded_at = time.monotonic()
            logger.info("Loaded %d cities from the iranbus.ir directory", len(self._cities))
        return self._cities

    async def resolve(self, name: str) -> int:
        """
        Resolve a city name to the provider's numeric code.

        Raises :class:`IranBusLocationError` when the city is not in the
        directory, listing a few valid names to make the failure actionable.
        """
        cities = await self.load()
        requested = normalize_city_name(name)

        if not requested:
            raise IranBusLocationError("City name is required")

        # A caller who already knows the code should not have to look it up.
        if requested.isdigit():
            for city in cities:
                if str(city.get("code")) == requested:
                    return int(city["code"])

        candidate = normalize_city_name(CITY_ALIASES.get(requested, requested))

        for city in cities:
            if normalize_city_name(city.get("persian_title") or "") == candidate:
                return int(city["code"])

        raise IranBusLocationError(
            f"Unknown city for the iranbus.ir provider: {name!r}. "
            f"Use the provider's city name, or one of: "
            f"{', '.join(sorted(CITY_ALIASES)[:8])}"
        )