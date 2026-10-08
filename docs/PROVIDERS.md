# Providers and Services

What each provider is registered for, and whether it actually works right now.

Last checked: **7 October 2026**, against the running container.

---

## Capability table

"Declared" is what the crawler registers in
`app/crawlers/registry.py`. "Working" is whether a search currently returns data.

| Provider | Flight | Hotel | Accommodation | Bus | Train | Host reachable | Notes |
|---|---|---|---|---|---|---|---|
| **alibaba** | yes | - | - | - | yes | yes | Verified live. Bus and hotel not integrated |
| **iranbus** | - | - | - | yes | - | yes | Verified live. The only working bus provider |
| **flytoday** | yes | yes | - | yes | yes | **no** | All four sub-domains fail DNS |
| **iranhotel** | - | yes | yes | - | - | yes | Needs a provider token from the pool |
| **jajiga** | - | - | yes | - | - | yes | Only accommodation provider with pagination |
| **karnaval** | - | - | - | - | - | yes | Registered but serves nothing |
| **safarchin** | yes | - | - | - | - | yes | Also declares a dead `transport` service |

### What each row means in practice

**alibaba** - Flights and trains both verified returning live, bookable data.

**iranbus** - Intercity bus departures from iranbus.ir, the national bus
cooperatives union, which sells for around 1400 companies and returns company,
bus class, departure time, terminal, remaining seats and price. This is the
**only working bus provider** in the system, and it is reached with no changes
to the endpoints or the orchestrator.

Two things about it are worth knowing before querying it:

- **Dates are Jalali and formatted `YYYY/MM/DD`.** Callers may pass either a
  Gregorian or a Jalali date; the adapter converts to the provider's form. The
  provider rejects anything else with `تاریخ شمسی معتبر نیست`.
- **Search is city-level, not terminal-level.** A query for Tehran can be
  answered by any of Tehran's terminals, and the terminal that actually serves
  the trip is reported in the result's `origin_terminal`.

The provider keys a search by numeric city code, so names are resolved through
its own city directory (690 cities), cached for 24 hours. English and Persian
names both resolve; an unknown city raises rather than returning nothing.

Prices are quoted in **rial**, unlike the Alibaba trains (toman) and Alibaba
flights (rial). The unit is set on each result, so the orchestrator's price
sort normalizes across providers correctly.

```bash
# Bus search, iranbus only
curl -H "X-API-Key: $KEY" \
  "http://localhost:8000/api/v1/transport/buses?origin=Tehran&destination=Mashhad&depart_date=2026-10-30&providers=iranbus"
```

**flytoday** - Registers four services, but every host it uses fails to resolve:

```
flight.flytoday.ir    DOES NOT RESOLVE
hotel.flytoday.ir     DOES NOT RESOLVE
villa.flytoday.ir     DOES NOT RESOLVE
train.flytoday.ir     DOES NOT RESOLVE
bus.flytoday.ir       DOES NOT RESOLVE
flytoday.ir           resolves
```

The parent domain resolves but no service sub-domain does, so **every FlyToday
search currently fails** and contributes nothing to a multi-provider response.
This is why a train search with no `providers` filter returns only Alibaba rows.

**iranhotel** - Hotel and accommodation. Requires a token in the provider pool
(`app/cli.py providers token add`); without one, searches fail. Results are never
cached - see [Caching rules](#caching-rules).

**jajiga** - Accommodation only. Provides province and city listings, and is the
only accommodation provider that returns pagination metadata.

**karnaval** - Registered with an empty service set and a comment saying it is
temporarily disabled pending an accommodation API change. It appears in
`/api/v1/providers` supporting nothing. It can safely be left registered (it is
never dispatched) or removed.

**safarchin** - Flights work (verified: 6 results THR to MHD). It also declares a
`transport` service that is **unreachable**, explained below.

---

## Fuel stations (not part of the orchestrator)

Fuel stations come from **OpenStreetMap**, and they deliberately do **not** go
through `CrawlerOrchestrator`.

```python
GET /api/v1/fuel-stations?origin=Tehran&destination=Isfahan&radius_m=1000
```

The service is `app/crawlers/fuelstation/`, driven by `FuelStationService`:

```
origin / destination  ->  geocode if needed (Nominatim)
                      ->  route (OSRM)          geometry, distance, duration
                      ->  bbox + projection     all fuel nodes near the route
                      ->  filter, classify, sort corridor radius, fuel type, km along route
```

Three things differ from every other service here.

**It does not use the orchestrator.** The orchestrator merges results from
several providers and sorts by price. Neither applies to a corridor: there is
one source, and the useful ordering is distance into the trip. The projection
step also happens *between* data sources, which the orchestrator has no hook
for. It reuses the OSM adapter's mirror list and Redis conventions, but not its
pipeline.

**It answers a corridor question, not an area question.** The OSM adapter's
restaurant search resolves a city boundary and queries inside it. "Along this
road" needs a route geometry first. Candidates are fetched with a **single
bounding-box query** and then filtered locally. The obvious alternative — a
union of `node(around:…)` selectors sampled along the route — was measured
returning **1 node instead of 22** on Tehran→Isfahan, with HTTP 200. It fails
silently, so the query shape is pinned by test rather than left to taste.

**It reports coverage, not just results.** The response carries
`largest_gap_km`. OpenStreetMap coverage of Iranian fuel stations is uneven,
and an unreported gap reads as a verified absence. See
[KNOWN_ISSUES.md](KNOWN_ISSUES.md#6-fuel-station-coverage-is-uneven).

Fuel prices are **not** returned. Iranian octane-tier pricing and ration-card
programmes are administratively set and appear nowhere in OpenStreetMap, so
there is no value this API could report honestly.

---

## Service dispatch: how a search finds its providers

A search asks the registry for every crawler registered under a service name:

```python
crawler_registry.get_crawlers_for_service(service_name, requested_providers)
```

The service name is normally the service itself - `flight`, `hotel`,
`accommodation`. **Ground transport is the exception.** The orchestrator dispatches
it on the transport *subtype* rather than on a `transport` service:

```python
# app/crawlers/orchestrator.py
service_name = query.transport_type.lower()      # -> "bus" or "train"
```

So `bus` and `train` are looked up directly. **`transport` is never a lookup key.**

### The `safarchin` `transport` defect

`safarchin` registers `services={"flight", "transport"}` and implements
`search_transport`. Because dispatch uses the subtype, none of it can ever run:

```
lookup 'transport' -> ['safarchin']      <- nobody asks for this
lookup 'bus'       -> ['flytoday', 'iranbus']
lookup 'train'     -> ['alibaba', 'flytoday']
```

A provider declaring `bus` or `train` is picked up directly. `iranbus`
declares `bus`; `safarchin` declares `transport` and so is not.

`SafarchinCrawler.search_transport` is unreachable dead code. Declaring `bus`
and/or `train` instead of `transport` would activate it - but that is only correct
if the method actually handles both subtypes. See
[KNOWN_ISSUES.md](KNOWN_ISSUES.md#3-safarchin-transport-service-is-unreachable).

---

## Caching rules

`CrawlerOrchestrator` holds two mechanisms for the same policy, which is worth
knowing when reading the code:

1. A hardcoded set, `NON_CACHEABLE_PROVIDERS = {"iranhotel"}`.
2. A per-crawler `is_cacheable` class attribute.

Either one marks a provider as never-cacheable. IranHotel is excluded because its
prices and availability must be real-time.

**Practical consequence for Alibaba:** flight and train results *are* cached. A
cache entry warmed before the availability filtering was added will keep serving
cancelled, sold-out and zero-capacity entries until its TTL expires. Flush the
search cache after deploying that change:

```bash
docker compose run --rm web python -m app.cli cache flush
```

---

## Requesting a specific provider

Every search endpoint accepts a comma-separated `providers` filter:

```bash
# Alibaba only
curl -H "X-API-Key: $KEY" \
  "http://localhost:8000/api/v1/flights/search?origin=THR&destination=MHD&depart_date=2026-10-30&providers=alibaba"

# Alibaba or FlyToday
curl -H "X-API-Key: $KEY" \
  "http://localhost:8000/api/v1/transport/trains?origin=THR&destination=MHD&depart_date=2026-10-22&providers=alibaba,flytoday"
```

To see what is registered at runtime:

```bash
curl -H "X-API-Key: $KEY" http://localhost:8000/api/v1/providers
```

---

## Adding a provider

1. Create `app/crawlers/<name>/crawler.py` with a class deriving from
   `BaseCrawler`.
2. Register it with `@register_crawler(name="<name>", services={...})`. The service
   names must be ones the orchestrator actually looks up - for ground transport
   that means `bus` or `train`, **not** `transport`.
3. Make sure the class is imported. `app/crawlers/__init__.py` imports each
   provider package, and `app/crawlers/orchestrator.py` imports
   `app.crawlers` to guarantee registration.

The crawler is then discovered automatically by the registry, the CLI, and
multi-provider searches, with no router or orchestrator changes.