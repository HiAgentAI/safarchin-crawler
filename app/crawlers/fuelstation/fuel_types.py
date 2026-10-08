"""Fuel type classification from OpenStreetMap tags and Persian names.

Resolution order, most to least trustworthy:

1. A structured ``fuel:*`` tag. Unambiguous, so it always wins.
2. A negative structured tag: ``fuel:diesel=no`` means it sells no diesel,
   which for an Iranian station implies petrol. 190 nodes carry this tag.
3. The station name, parsed as Persian.

Step 3 is not a nicety. Only about 29% of Iranian ``amenity=fuel`` nodes
carry any ``fuel:*`` tag at all, so tag-only filtering recovers roughly a
third of the answer; name parsing roughly doubles the diesel count.

The CNG check runs *before* the petrol check, and this ordering is load
bearing rather than stylistic. ``پمپ گاز`` literally means "gas pump" and
denotes CNG, because Persian for natural gas is گاز — the same word an
English speaker's intuition reads as "gasoline". A rule matching on گاز to
find petrol misfiles roughly 1,087 stations, 28% of the country. Petrol is
anchored on بنزین (benzin) instead, and never on a gas word.
"""
from typing import Any, Dict, Optional

from app.crawlers.openstreetmap.normalize import normalize_text
from app.schemas.fuel_station import FuelType

# Persian fuel vocabulary. Normalised before matching, so the Arabic yeh/keheh
# and kaf variants below are the canonical spellings.
#
# بنرین is included because it is a real-world typo of بنزین that appears in
# mapped station names, not a hypothetical.
_RE_PETROL = ("بنزین", "بنرین", "petrol", "gasoline")
_RE_DIESEL = ("گازوئیل", "گازوییل", "دیزل", "diesel")

# CNG splits into a strong and a weak signal, and that split is what keeps the
# classifier correct. Persian for diesel is گازوئیل, which *contains* the bare
# gas word گاز, so a single undifferentiated gas pattern would read every
# diesel station as CNG. Explicit markers win; the bare word is only consulted
# once the more specific fuels have been ruled out.
_RE_CNG_STRONG = ("cng", "گاز طبیعی", "گاز فشار")
_RE_CNG_WEAK = ("گاز",)

_RE_LPG = ("lpg", "پی جی", "گاز مایع")

# Values OSM uses for a boolean-ish tag that counts as "yes".
_TRUTHY = {"yes", "only", "true", "1"}
# Explicit denial, which carries its own information.
_FALSEY = {"no", "false", "0"}


def _is_truthy(value: Optional[str]) -> bool:
    return value is not None and value.strip().lower() in _TRUTHY


def _is_falsey(value: Optional[str]) -> bool:
    return value is not None and value.strip().lower() in _FALSEY


def _matches_any(normalized: str, needles) -> bool:
    return any(n in normalized for n in needles)


def _classify_by_name(name: str) -> Optional[FuelType]:
    """Infer fuel type from a station name.

    Returns ``None`` when the name carries no fuel signal, which leaves the
    station unclassified rather than defaulting it.
    """
    if not name:
        return None
    text = normalize_text(name)
    if not text:
        return None

    # Order matters, and it is not "gas before petrol" but "specific before
    # general". Explicit CNG and LPG markers are unambiguous. Diesel outranks
    # the bare gas word because گازوئیل contains گاز. The bare gas word is
    # consulted late, so "پمپ گاز" reads as CNG while "پمپ گازوئیل" reads as
    # diesel. Petrol is checked last: it is anchored on بنزین, which no gas or
    # diesel word contains, so it cannot shadow the others.
    if _matches_any(text, _RE_LPG):
        return FuelType.LPG
    if _matches_any(text, _RE_CNG_STRONG):
        return FuelType.CNG
    if _matches_any(text, _RE_DIESEL):
        return FuelType.DIESEL
    if _matches_any(text, _RE_CNG_WEAK):
        return FuelType.CNG
    if _matches_any(text, _RE_PETROL):
        return FuelType.PETROL
    return None


def classify_fuel_type(
    tags: Optional[Dict[str, Any]] = None,
    name: Optional[str] = None,
) -> FuelType:
    """Classify a station as petrol, diesel, CNG, LPG or unknown.

    Unclassifiable stations stay ``unknown``. They are deliberately not
    defaulted to petrol: that would raise apparent coverage but would send a
    diesel driver to a CNG-only pump, possibly far from an alternative.
    """
    tags = tags or {}

    # 1. Structured positive tags.
    if _is_truthy(tags.get("fuel:gasoline")):
        return FuelType.PETROL
    if _is_truthy(tags.get("fuel:diesel")):
        return FuelType.DIESEL
    if _is_truthy(tags.get("fuel:cng")):
        return FuelType.CNG
    if _is_truthy(tags.get("fuel:lpg")):
        return FuelType.LPG

    # OSM also uses the older combined form: fuel=petrol;gasoline
    generic = tags.get("fuel")
    if isinstance(generic, str) and "gasoline" in generic.lower():
        return FuelType.PETROL
    if isinstance(generic, str) and "diesel" in generic.lower():
        return FuelType.DIESEL

    # 2. Negative structured tags imply the alternative.
    if _is_falsey(tags.get("fuel:diesel")):
        return FuelType.PETROL
    if _is_falsey(tags.get("fuel:gasoline")):
        return FuelType.DIESEL

    # 3. Name inference.
    from_name = _classify_by_name(name or "")
    if from_name is not None:
        return from_name

    return FuelType.UNKNOWN