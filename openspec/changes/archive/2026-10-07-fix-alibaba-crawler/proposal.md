# Proposal

## Why

The Alibaba provider is registered and reports healthy, but returns nothing usable for any
service. Its crawler was written against an imagined API and verified only against a
hand-authored fixture, so it fails silently and unconditionally in production while its tests
pass. Live investigation of `ws.alibaba.ir` established two services that return real data today
(flights and trains) and two that cannot yet be integrated (buses and hotels).

## What Changes

- **Fix domestic flight search.** The endpoint is correct but requires `POST`; the crawler sends
  `GET` and receives `405 Method Not Allowed`, so every search fails at `raise_for_status()`.
- **Adopt Alibaba's two-phase search protocol** for flights and trains: a criteria `POST` returns
  a handle, which is then used to `GET` the result set. Results are not present in the phase-one
  response.
- **Correct the flight field mapping.** Five of the twelve fields the parser reads do not exist in
  the live payload, so airline name and code silently resolve to `None` on every result.
- **Filter unbookable flights.** The live feed returns cancelled and sold-out departures; the
  existing parser emits them as if they were purchasable.
- **Add domestic train search** as a new capability, including its own handle encoding, price
  unit, and seat-availability filtering.
- **Assign a per-provider time budget.** The two round trips plus a slow tail can exceed the
  orchestrator's shared timeout, which currently sacrifices Alibaba's own result for the whole
  request.
- **Stop the accommodation integration from being reachable.** It points at a host that does not
  resolve in DNS.

**BREAKING**: Alibaba flight results change shape and content. Prices are now sourced from the
provider rather than assumed, and unbookable departures are no longer returned, so result counts
will differ from anything observed previously.

### Out of scope

- **Bus search.** `GET /api/v2/bus/available` is reachable and validates its `DepartureDate`
  parameter, but rejects every date encoding tried (Gregorian, Jalali, RFC 3339, `YYYYMMDD`,
  `DD-MM-YYYY`) with an identical error, which indicates the value is not binding to the field
  rather than a format problem. Needs a captured real request.
- **Hotel search.** `POST /api/v1/hotel/search` accepts RFC 3339 dates and then requires an
  undocumented internal `cityId`; every value tried is refused with `city id is not valid
  probably`. The frontend confirms `cityId` is the correct parameter name, so the value space
  must be recovered from a live session.

Neither service is stubbed or partially registered; both remain unimplemented.

## Capabilities

### New Capabilities

- `alibaba-flight-search`: Querying Alibaba for bookable domestic flight availability, including
  its two-phase request protocol, result mapping, and availability rules.
- `alibaba-train-search`: Querying Alibaba for bookable domestic passenger train departures,
  including its distinct price unit and seat-capacity rules.

### Modified Capabilities

None. The project's spec inventory is empty, so nothing existing is being changed.

## Impact

**Code**

- `app/crawlers/alibaba/crawler.py` — rewritten flight mapping; new train implementation. The
  fictional hotel and accommodation calls are removed rather than corrected.
- `app/crawlers/alibaba/` — new support module for the two-phase protocol, provider-specific
  enums, and aircraft normalization.
- `app/crawlers/orchestrator.py` — per-provider timeout, so a slow provider cannot consume the
  shared budget of the providers running beside it.

**Contracts and tests**

- `app/schemas/flight.py`, `app/schemas/transport.py` — train departure fields; flight segment
  availability, corrected cabin class, and provider timestamp semantics.
- `tests/fixtures/alibaba_flight_response.json` — replaced with a captured response. The current
  fixture is self-invented: its `uniqueKey` values (`alibaba_fl_101`) are the same strings the
  test asserts on, so it cannot fail.
- `tests/crawlers/test_alibaba.py` — no test exercises a URL or verb, and `search_hotels` and
  `search_accommodations` have no tests at all. Tests must assert against captured payloads.

**External**

- `ws.alibaba.ir` (45.89.201.11), an Alibaba backend behind an F5 BIG-IP ASM WAF. No
  authentication, API key, session cookie, or custom header is required; anti-bot impersonation
  made no measurable difference to success or latency.
- Two different server stacks sit behind that one host: flights and trains answer with ASP.NET-style
  error payloads, hotels with Go-style ones. Neither exposes an OpenAPI document.
- Rate-of-return is unmeasured and no request-volume guidance is available from the provider.