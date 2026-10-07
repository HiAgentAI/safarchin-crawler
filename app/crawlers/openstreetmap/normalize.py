import math
from typing import Optional, Dict, Any, List
from app.schemas.restaurant import RestaurantResult
from app.schemas.common import ProviderInfo

def normalize_text(text: Optional[str]) -> str:
    """Normalize Persian and English text for comparison."""
    if not text:
        return ""
    text = text.strip().lower()
    text = text.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه").replace("‌", " ")
    return " ".join(text.split())

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in meters between two lat/lon coordinates."""
    r = 6371000.0  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c

def extract_restaurant_result(element: Dict[str, Any], city: str) -> Optional[RestaurantResult]:
    """Parse raw OSM element (node, way, relation) into a RestaurantResult."""
    tags = element.get("tags", {})
    el_type = element.get("type", "node")
    el_id = element.get("id")

    # Name is mandatory for meaningful restaurant listing
    name = tags.get("name") or tags.get("name:fa") or tags.get("name:en")
    if not name:
        return None

    name_en = tags.get("name:en") or tags.get("int_name")
    
    # Lat/Lon extraction: nodes have 'lat'/'lon', ways/relations have 'center'
    lat = element.get("lat")
    lon = element.get("lon")
    if lat is None or lon is None:
        center = element.get("center", {})
        lat = center.get("lat")
        lon = center.get("lon")

    if lat is None or lon is None:
        return None

    # Address composition
    street = tags.get("addr:street")
    full_addr = tags.get("addr:full")
    address = full_addr or street

    # Contact info
    phone = tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile")
    website = tags.get("website") or tags.get("contact:website")

    # Cuisine and metadata
    cuisine = tags.get("cuisine")
    amenity = tags.get("amenity", "restaurant")
    opening_hours = tags.get("opening_hours")
    last_edited = element.get("timestamp")

    unique_id = f"osm:{el_type}:{el_id}"

    return RestaurantResult(
        id=unique_id,
        provider=ProviderInfo(
            name="openstreetmap",
            deep_link=f"https://www.openstreetmap.org/{el_type}/{el_id}",
            scraped_at=None,
        ),
        name=name.strip(),
        name_en=name_en.strip() if name_en else None,
        city=city,
        cuisine=cuisine,
        amenity=amenity,
        latitude=float(lat),
        longitude=float(lon),
        address=address,
        phone=phone,
        website=website,
        opening_hours=opening_hours,
        last_edited=last_edited,
        tags=tags,
    )

def deduplicate_restaurants(restaurants: List[RestaurantResult], proximity_meters: float = 50.0) -> List[RestaurantResult]:
    """
    Collapse duplicate restaurants (e.g. node POI + way building outline)
    where names match and distance is under proximity_meters.
    """
    if not restaurants:
        return []

    deduped: List[RestaurantResult] = []

    for current in restaurants:
        current_norm = normalize_text(current.name)
        matched_idx = -1

        for idx, existing in enumerate(deduped):
            existing_norm = normalize_text(existing.name)
            # Check name match or containment
            if current_norm == existing_norm or current_norm in existing_norm or existing_norm in current_norm:
                dist = haversine_distance(
                    current.latitude, current.longitude,
                    existing.latitude, existing.longitude
                )
                if dist <= proximity_meters:
                    matched_idx = idx
                    break

        if matched_idx != -1:
            # Merge fields into the existing record
            existing = deduped[matched_idx]
            if not existing.phone and current.phone:
                existing.phone = current.phone
            if not existing.website and current.website:
                existing.website = current.website
            if not existing.address and current.address:
                existing.address = current.address
            if not existing.cuisine and current.cuisine:
                existing.cuisine = current.cuisine
            if not existing.opening_hours and current.opening_hours:
                existing.opening_hours = current.opening_hours
            if not existing.name_en and current.name_en:
                existing.name_en = current.name_en
            existing.tags.update(current.tags)
        else:
            deduped.append(current)

    return deduped
