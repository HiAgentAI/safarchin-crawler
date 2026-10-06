# Providers and Services

What each provider is registered for, and whether it actually works right now.

Last checked: **6 October 2026**, against the running container.

---

## Capability table

"Declared" is what the crawler registers in
`app/crawlers/registry.py`. "Working" is whether a search currently returns data.

| Provider | Flight | Hotel | Accommodation | Bus | Train | Host reachable | Notes |
|---|---|---|---|---|---|---|---|
| **alibaba** | yes | - | - | - | yes | yes | Verified live. Bus and hotel not integrated |
| **flytoday** | yes | yes | - | yes | yes | **no** | All four sub-domains fail DNS |
| **iranhotel** | - | yes | yes | - | - | yes | Needs a provider token from the pool |
| **jajiga** | - | - | yes | - | - | yes | Only accommodation provider with pagination |
| **karnaval** | - | - | - | - | - | yes | Registered but serves nothing |
| **safarchin** | yes | - | - | - | - | yes | Also declares a dead `transport` service |

### What each row means in practice

**alibaba** - Flights and trains both verified returning live, bookable data.
This is the only provider with no known blocker.

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
lookup 'bus'       -> ['flytoday']
lookup 'train'     -> ['alibaba', 'flytoday']
```

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