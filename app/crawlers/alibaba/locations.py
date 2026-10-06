"""
City resolution for the Alibaba provider.

Alibaba accepts only an exact IATA code in the ``origin``/``destination`` fields.
Every other form is rejected with HTTP 400 - English names in any casing,
mixed code-and-name values, and Persian names alike. Meanwhile this API's
transport and flight endpoints are documented in terms of city names
(``origin=Tehran``), and the Flytoday adapter passes names straight through.

This module bridges the two: it accepts whatever the caller supplies and returns
the code Alibaba accepts.

Resolution order:

1. An Alibaba-specific override table, for names the shared airport data
   resolves to a code Alibaba rejects.
2. A value that already looks like an IATA code, passed through untouched so an
   explicit code is never second-guessed.
3. The shared airport lookup in :mod:`app.crawlers.safarchin.airports`, by
   English name, slug, or Persian name.
4. Otherwise a ``ValueError`` naming the value, rather than sending a string
   Alibaba will reject and reporting the result as "no availability".
"""

from typing import Dict, Optional

from app.crawlers.safarchin.airports import find_airport

# Names the shared airport data resolves to a code Alibaba rejects.
#
# ``airports.py`` indexes English names by slug, and two of its entries share the
# slug ``Tehran``. The later one (``IKA``, Imam Khomaini) overwrites the earlier
# (``THR``), so the plain city name "Tehran" resolves to IKA. Alibaba uses THR
# for the city of Tehran and rejects IKA, so the city name is mapped explicitly.
#
# Someone who genuinely wants Imam Khomaini can still pass ``IKA`` and it is
# passed through untouched by rule 2.
_ALIBABA_CITY_OVERRIDES: Dict[str, str] = {
    "tehran": "THR",
}


def _looks_like_iata(value: str) -> bool:
    """True for a bare three-letter code such as THR or MHD."""
    return len(value) == 3 and value.isalpha() and value.isupper()


def to_alibaba_city_code(value: Optional[str], *, field: str = "city") -> str:
    """
    Resolve a city name or code to the identifier Alibaba accepts.

    Raises ``ValueError`` when the value cannot be resolved, so an unusable city
    is reported as an error instead of silently returning no availability.
    """
    if value is None:
        raise ValueError(f"Alibaba requires a {field} but none was supplied")

    token = str(value).strip()
    if not token:
        raise ValueError(f"Alibaba requires a {field} but an empty value was supplied")

    override = _ALIBABA_CITY_OVERRIDES.get(token.lower())
    if override:
        return override

    if _looks_like_iata(token):
        return token

    airport = find_airport(token)
    if airport and airport.iata and airport.iata != "همه":
        return airport.iata

    raise ValueError(
        f"Alibaba could not resolve {field} {value!r} to a city code. "
        f"Pass a three-letter IATA code such as 'THR', or an English or Persian "
        f"city name known to the airport lookup."
    )