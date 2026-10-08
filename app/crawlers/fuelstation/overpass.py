"""Overpass retrieval of candidate fuel stations.

One bounding-box query, then distance filtering in the caller. This is a
deliberate choice, not a convenience.

The textbook way to ask Overpass for a corridor is a union of per-point
proximity selectors —

    node["amenity"="fuel"](around:1500,lon1,lat1);
    node["amenity"="fuel"](around:1500,lon2,lat2);
    ...

On the Tehran -> Isfahan route that query returned **1 node instead of 22**,
with HTTP 200, across four mirrors and two chunkings. It fails silently, which
is the dangerous shape: a test asserting "returns some stations" passes, and a
caller gets a confident, wrong answer.

A single bbox selector covering the route envelope returns the full set. The
corridor filter then happens locally, in :mod:`geometry`, which also produces
km_into_trip as a by-product.
"""
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from app.crawlers.openstreetmap.crawler import DEFAULT_OVERPASS_MIRRORS
from app.core.config import settings

logger = logging.getLogger(__name__)

USER_AGENT = "SafarchinApp/1.0 (contact@safarchin.ir)"


class OverpassRetrievalError(RuntimeError):
    """Every configured Overpass mirror failed or rate-limited the query."""


def build_corridor_query(bbox: Tuple[float, float, float, float]) -> str:
    """Build a single bounding-box Overpass QL query.

    ``bbox`` is (south, west, north, east) in degrees.

    Exactly one selector is emitted. This function is the guard against a
    regression to the per-point proximity union described in the module
    docstring, so it must not grow a loop over sample points.
    """
    south, west, north, east = bbox
    return (
        f"[out:json][timeout:{int(settings.CRAWLER_DEFAULT_TIMEOUT * 2)}];\n"
        f'node["amenity"="fuel"]({south:.6f},{west:.6f},{north:.6f},{east:.6f});\n'
        "out body;"
    )


def _is_useful_response(status_code: int, text: str) -> bool:
    """A 200 carrying valid JSON with an elements list.

    Overpass answers rate limits and gateway errors with HTML bodies under a
    200 in some deployments, so the body shape has to be checked too.
    """
    if status_code != 200:
        return False
    stripped = text.strip()
    if not stripped.startswith("{"):
        return False
    return '"elements"' in stripped


async def fetch_corridor_stations(
    bbox: Tuple[float, float, float, float],
    timeout: float = 60.0,
    mirrors: Optional[Sequence[str]] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> List[Dict[str, Any]]:
    """Fetch every amenity=fuel node inside a bounding box.

    Rotates across mirrors because Overpass rate-limits aggressively — during
    exploration the main mirror returned HTTP 429 on roughly a fifth of queries
    and a secondary mirror served the rest.

    Raises OverpassRetrievalError when every mirror fails. It must not return
    an empty list on failure: an empty list means "the corridor genuinely has
    no stations", which is a materially different claim.
    """
    query = build_corridor_query(bbox)
    mirror_list = list(mirrors or DEFAULT_OVERPASS_MIRRORS)

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    try:
        for mirror in mirror_list:
            try:
                logger.info(f"Querying Overpass mirror for fuel corridor: {mirror}")
                response = await http.post(
                    mirror,
                    data={"data": query},
                    headers={"User-Agent": USER_AGENT},
                )
                text = response.text
                if _is_useful_response(response.status_code, text):
                    payload = response.json()
                    return list(payload.get("elements") or [])
                logger.warning(
                    f"Overpass mirror {mirror} returned HTTP {response.status_code} "
                    f"with an unusable body"
                )
            except Exception as e:
                logger.warning(f"Overpass mirror {mirror} failed: {e}")
    finally:
        if owns_client:
            await http.aclose()

    raise OverpassRetrievalError(
        f"All {len(mirror_list)} Overpass mirrors failed or rate-limited the fuel "
        f"corridor query. Last attempt: {mirror_list[-1] if mirror_list else 'none'}"
    )


def extract_station(element: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalise an Overpass node into the fields the service needs."""
    element_type = element.get("type")
    element_id = element.get("id")
    lat = element.get("lat")
    lon = element.get("lon")

    # Fuel stations are mapped as nodes; a way or relation without a usable
    # centre cannot be positioned on the route.
    if element_type != "node" or element_id is None:
        return None
    if lat is None or lon is None:
        return None

    tags = element.get("tags") or {}
    return {
        "id": f"osm:{element_type}:{element_id}",
        "latitude": float(lat),
        "longitude": float(lon),
        "tags": tags,
        "name": tags.get("name") or tags.get("name:fa"),
        "name_en": tags.get("name:en"),
        "address": tags.get("addr:full") or tags.get("addr:street"),
        "opening_hours": tags.get("opening_hours"),
    }