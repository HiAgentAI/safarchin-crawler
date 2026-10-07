# Proposal

## Why

The aggregator answers flight, hotel, accommodation, bus and train searches but nothing for restaurants,
which is the one travel need a traveller has on every trip after arriving. OpenStreetMap supplies
restaurant data free and without an API key, but it differs from every existing provider in ways that
must be designed for rather than discovered in production: it carries no price and no rating at all,
its records are years old, and its upstream services publish usage policies that constrain how they
may be called.

Live measurement on 7 October 2026 against `nominatim.openstreetmap.org` and `overpass-api.de`
established the feasible shape and the limits. Tehran's city boundary returns 1431 restaurants in
about 2 seconds, but the median record was last edited 1289 days ago, only 1% carry a surveyor
verification date, and 56% have never been edited since creation.

## What Changes

- **Add a `restaurant` service** served by a new OpenStreetMap provider adapter, registered in the
  existing crawler registry and reachable through a new `/api/v1/restaurants/search` endpoint.
- **Resolve a city to its administrative boundary** through Nominatim, accepting English and Persian
  city names. Resolution results are cached and persisted so a repeated city is not re-geocoded.
- **Retrieve restaurants within that boundary** from Overpass. The query selects nodes, ways and
  relations rather than nodes alone: a node-only query returns 1337 of Tehran's 1431 restaurants and
  silently undercounts by 6.6%.
- **Collapse near-identical records.** A restaurant mapped as both a point of interest and a building
  appears twice; 14 such pairs and 51 repeated names were measured in Tehran alone.
- **Report how current each record is.** Every result carries the date its underlying map entry was
  last edited, so a caller can judge staleness instead of inheriting an unstated assumption.
- **Report provider failure rather than an empty result.** Overpass serves two concurrent slots and
  answers excess load with HTTP 429; a search that fails must be distinguishable from a city that has
  no restaurants.
- **Carry no price and no rating.** Neither exists in the source. The response will state this rather
  than presenting a price-less result in a shape that implies one is missing from the data.

**BREAKING**: this introduces a service whose results are structurally unlike the existing ones.
Restaurant results have no price and no rating, where every other service in this API carries both.
Any consumer that sorts or filters results uniformly across services must handle their absence.

### Out of scope

- **Rating, review count, and price.** All three were requested and none exist in OpenStreetMap.
  OpenStreetMap has no rating or review model at all, and no price tag exists for restaurants.
  Delivering them requires a paid provider and is a separate change.
- **Menus, photos, and table booking.** No corresponding data in the source.
- **Cafes, bars, and fast food.** The initial tag selection is `amenity=restaurant` only. Sibling
  tags are numerous and their inclusion is a content decision, not a technical one.
- **Reverse geocoding and radius search.** The service is city-scoped by boundary.
- **Generalising the orchestrator's failure reporting.** Only this provider's behaviour is specified
  here. The cross-provider case described in `docs/KNOWN_ISSUES.md` remains open.

## Capabilities

### New Capabilities

- `osm-restaurant-search`: Querying OpenStreetMap for restaurants within an administratively bounded
  city, including boundary resolution, result mapping, record deduplication, currency-of-record
  reporting, and the distinction between an unavailable search and a city with no restaurants.

### Modified Capabilities

None. The project's existing capabilities are `alibaba-flight-search` and `alibaba-train-search`,
neither of which this change touches.

## Impact

**Code**

- `app/crawlers/openstreetmap/` — new adapter: boundary resolution, Overpass query construction, and
  mapping to the restaurant schema.
- `app/schemas/restaurant.py` — new query and result models. Deliberately omits the `PriceInfo` and
  rating fields every other result schema carries.
- `app/crawlers/base.py` — new `search_restaurants` method on the base class.
- `app/crawlers/orchestrator.py` — restaurant dispatch. The orchestrator's sort key is built from
  price, which does not exist for this service and must be given an alternative.
- `app/api/v1/restaurants.py`, `app/api/v1/api.py` — new router.
- `app/core/redis.py` — persisted boundary-resolution cache, so a city is geocoded once rather than
  on every request.

**Contracts and tests**

- `tests/fixtures/` — captured Overpass and Nominatim responses. Per the principle established in
  `2026-10-07-fix-alibaba-crawler`, fixtures must be captured from the live service; a hand-authored
  fixture whose identifiers are the values the test asserts on cannot fail.
- Tests must cover the node-only undercount, duplicate collapsing, and failure-versus-empty, since each
  is a silent-wrong-answer defect that a result-count assertion would not catch.

**External services and their policies**

- `nominatim.openstreetmap.org` — resolution only, and only from a cache-miss path. Its policy caps
  use at one request per second, requires an identifying User-Agent, and states that commercial
  applications serving paying customers must keep in mind that their access may be withdrawn. This
  API has key tiers and quotas, so it is such an application. The Nominatim policy additionally
  prohibits offering the public API through AI coding assistants as a generic geocoding service
  unless the developer has made a deliberate, informed decision and is directly responsible for
  compliance.
- `overpass-api.de` — the retrieval half. Its documentation names "setting up an app for more than
  just OSM mappers and relying on the public instances as backend" as problematic behaviour, and
  states that only running one's own instance sustainably serves such a mission. It also publishes
  limits of roughly 10000 requests and 1 GB per day, two concurrent slots, and HTTP 429 on overflow.

This change is therefore built against services whose operators have asked not to be used this way.
It is recorded in `design.md` with the mitigations chosen and the residual risk left open, rather than
treated as settled.