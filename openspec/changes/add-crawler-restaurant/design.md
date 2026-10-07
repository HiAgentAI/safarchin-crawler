# Design

## Context

See `proposal.md` for motivation and `specs/osm-restaurant-search/spec.md` for normative requirements.
This document outlines the architecture, data structures, and failure handling mechanisms for integrating OpenStreetMap (Nominatim and Overpass API) into the crawler engine.

The platform currently aggregates travel services (flights, hotels, accommodations, buses, trains) with unified sorting and pricing. OpenStreetMap diverges from all existing providers:
- It requires a two-step resolution: geocoding the administrative boundary first (Nominatim), then querying the spatial area (Overpass).
- It provides no price, rating, reviews, or booking metadata.
- Public servers enforce strict policies:
  - Nominatim: max 1 request/sec, mandatory descriptive `User-Agent`.
  - Overpass (`overpass-api.de`, `kumi.systems`, `private.coffee`): 2 concurrent slots, frequent `HTTP 429` / `HTTP 504 Gateway Timeout` under heavy spatial join loads.
- Iranian city names may be supplied in Persian (e.g., "اصفهان", "تهران") or English ("Isfahan", "Tehran").

## Goals / Non-Goals

**Goals:**
- Provide a clean, robust `/api/v1/restaurants/search` endpoint adhering to project architecture (FastAPI router, adapter registry, BaseCrawler, Pydantic schemas).
- Cache resolved city boundaries in Redis indefinitely (or long TTL, e.g. 30 days) to minimize Nominatim calls and comply with usage policies.
- Execute full Overpass queries covering nodes, ways, and relations (`out center;`), avoiding silent undercounting.
- Deduplicate duplicate POI and building geometries using proximity clustering and name normalization.
- Expose a `last_edited` timestamp on each restaurant result to communicate data freshness.
- Surface explicit upstream errors (`502` / `504` / `429`) instead of misleading empty results `[]` when Overpass fails.

**Non-Goals:**
- Scraping menus, food items, or prices (unsupported by OpenStreetMap).
- Supporting cafes, fast food, and bakeries in this initial iteration (scoped strictly to `amenity=restaurant`).
- Reverse geocoding or user coordinate-based radius queries (scoped to administrative city boundaries).

## Decisions

### 1. Two-stage Provider Architecture: Nominatim + Overpass Adapter
- **Decision**: Encapsulate boundary lookup and Overpass querying inside a single `OpenStreetMapCrawler` (registered under `app/crawlers/openstreetmap/`).
- **Rationale**: Keeps the caller interface uniform (`crawler.search_restaurants(query)`).
- **Alternatives considered**:
  - *Hardcoding city Overpass area IDs in a static file*: Inflexible when users search smaller or unlisted towns.
  - *Bounding-box only search*: Would include outlying areas outside municipal administrative borders.

### 2. Redis Caching for Administrative Boundaries
- **Decision**: Cache `city_name -> area_id` mappings in Redis with a 30-day TTL.
- **Rationale**: City boundaries rarely change. This ensures Nominatim is only called once per city over a month, keeping traffic well within the 1 req/sec policy.
- **Alternatives considered**: In-memory dict (lost across worker restarts / container scaling).

### 3. Multi-mirror Overpass Client with Timeout and Retry
- **Decision**: Configure a list of fallback Overpass mirrors (`overpass-api.de`, `overpass.kumi.systems`, `overpass.private.coffee`) with a 15-second per-request timeout.
- **Rationale**: Live probing revealed intermittent `504 Gateway Timeout` on `overpass-api.de`. A fallback rotation significantly improves crawler availability.
- **Alternatives considered**: Single URL only (leads to frequent user-facing 504 errors).

### 4. Duplicate Collapsing via Coordinate Proximity & Name Normalization
- **Decision**: In OpenStreetMap, a restaurant is frequently tagged both as a node (POI point) and a way (building outline). If two elements share the same normalized name (case-folded, whitespace-trimmed, Persian letter unification) and are within 50 meters of each other, merge them into a single record.
- **Rationale**: Prevents bloated result sets with confusing duplicate listings.

### 5. Deliberate Omission of Price and Rating from Schema
- **Decision**: Define `RestaurantResult` without `price`, `currency`, `rating`, or `review_count`.
- **Rationale**: Prevents misleading callers or returning dummy zeros/nulls across an API that otherwise provides bookable prices.

### 6. Orchestrator Adaptation for Priceless Services
- **Decision**: In `CrawlerOrchestrator`, bypass price-based sorting when the query target is `restaurant`. Default sort by `name` or `last_edited` descending.
- **Rationale**: `CrawlerOrchestrator` currently attempts to sort by `price` which raises an `AttributeError` or unexpected behavior on restaurant results.

## Risks / Trade-offs

- **[Risk]** Public Overpass mirrors may be rate-limited or blocked during peak hours.
  - **Mitigation**: Rotate mirrors, cache search results in Redis with caller-controlled TTL, and immediately return `503 Service Unavailable` with provider attribution rather than empty lists.
- **[Risk]** Nominatim fails to resolve transliterated or colloquial city names (e.g. "Esfahan" vs "Isfahan").
  - **Mitigation**: Normalize Iranian city queries, support both Persian and common English variants, and return informative `404 City Boundary Not Found` errors.
- **[Risk]** Memory and payload size for large metropolises (e.g. Tehran has ~1,500 restaurants).
  - **Mitigation**: Use `out center;` to fetch centroid coordinates for ways/relations instead of full polygon node arrays, reducing payload size by ~80%.

## Migration Plan

1. Deploy new schema in `app/schemas/restaurant.py`.
2. Add `search_restaurants` abstract method to `BaseCrawler` and implement in `OpenStreetMapCrawler`.
3. Update `CrawlerOrchestrator` to dispatch restaurant queries.
4. Mount `app/api/v1/restaurants.py` router in `app/api/v1/api.py`.
5. Run full test suite with captured fixtures.
