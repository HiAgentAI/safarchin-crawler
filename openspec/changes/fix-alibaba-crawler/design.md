# Design

## Context

See `proposal.md` for motivation and the two capability specs for requirements:
`specs/alibaba-flight-search/spec.md` and `specs/alibaba-train-search/spec.md`. What follows is
only the current state and constraints that shaped the technical choices.

Alibaba exposes two reachable services on `ws.alibaba.ir`, both using the same two-phase shape but
with different handle encodings:

| | Flights | Trains |
|---|---|---|
| Criteria request | `POST /api/v1/flights/domestic/available` | `POST /api/v1/train/available` |
| Criteria response | `{"result":{"requestId":"GE4...","bannerId":"General"}}` | `{"result":"<base64 JSON>"}` |
| Result request | `GET .../available/{requestId}` | `GET .../available/{base64}` |
| Result envelope | `{"result":{"departing":[...], "returning":[]}}` | `{"departing":[...], "returning":[]}` unwrapped |
| Verified | 20-37 flights, 3 routes | 21 departures, THR-MHD |

Constraints that bound the approach:

- **No auth, no cookies, no custom headers.** TLS impersonation via `curl_cffi` made no measurable
  difference to success or latency, so no anti-bot work is needed for this provider.
- **No OpenAPI document.** Swagger paths 302 to the homepage. Field names come from captured
  payloads, so nothing prevents silent upstream drift.
- **Two server stacks behind one host.** Flights and trains return ASP.NET-style validation errors
  (`{"error":{"validationErrors":[...]}}`); hotels return Go-style ones. Error handling cannot assume
  one shape.
- **Dates must be Gregorian.** A Jalali string is parsed as Gregorian year 1405 and rejected. The
  existing `to_gregorian` in `app/utils/calendar.py` already handles this conversion and needs no
  change.
- **Trains require a passenger count**; omitting it yields a validation error, not an empty result.
  The provider field is `passengerCount`, not `passengers` as the existing schema names it.
- **Two round trips with a long tail.** Phase one measured 1.1-2.0s typically with outliers past
  10s and once past 25s; phase two measured 2.4-9.9s. A full flow reached 13.0s and 15.0s against
  the orchestrator's shared 15s budget.

Two pre-existing orchestrator behaviors interact badly with this provider and must be addressed for
the fix to hold:

- `CrawlerOrchestrator._run_parallel` wraps the whole `asyncio.gather` in one
  `asyncio.wait_for(self.timeout)`. A slow provider therefore fails the entire request, discarding
  providers that already succeeded.
- The same method returns only successful results, but the caller pairs them with
  `zip(live_crawlers, live_results)`. When one provider fails, that zip misaligns: a surviving
  provider's results are attributed to the failed provider, whose name is then recorded in the
  cache as satisfied. Per-provider timeouts would make partial failure routine and so make this
  defect far more likely to corrupt cache state.

## Goals / Non-Goals

**Goals:**

- Make Alibaba flights and trains return real, correct, bookable data through the existing API.
- Represent each service's prices in the unit the provider actually charges, and stop the
  aggregation layer from comparing amounts across different units.
- Keep a slow or failing Alibaba call from degrading providers running beside it.
- Replace the fabricated fixtures with captured payloads, so a future regression in field names
  fails a test.
- Remove the two calls that cannot work, rather than leaving them as unreachable code.

**Non-Goals:**

- Bus and hotel integration. Neither has a reachable search that accepts a valid request; both are
  deferred pending a captured real request.
- Round-trip and multi-city flights. The provider does return a `returning` array, but only one-way
  searches were verified, so no requirement is stated for it.
- Generalizing currency handling across the whole system. Every service is internally consistent
  today, so only the transport service becomes mixed-unit as a result of this change.
- Reworking provider registry or the adapter pattern. The registry works as designed here.

## Decisions

### Two-phase protocol as a shared helper

Both services are "submit criteria, get a handle, fetch results". Flights hand back an opaque
`requestId` string; trains hand back a base64-encoded echo of the criteria. That difference is an
encoding detail, not a protocol difference, so both go through one helper that owns the POST, the
handle extraction, and the follow-up GET.

**Alternative considered:** write the two round trips inline per service, as flytoday does. Rejected:
it duplicates the failure handling that the 405 and empty-`result` traps both demand, and the second
copy would be written against a schema nobody has verified end to end.

### Provider payloads accessed by field name, with unknown fields ignored

The live payloads carry roughly 70 fields per item with a mix of Persian display strings and
internal identifiers. Extra keys are ignored rather than treated as errors, since the schema is
undocumented and may gain fields.

### True native price units, with currency-aware aggregation

Alibaba flight fares are Rial; Alibaba train fares are Toman. Each result is labeled with the unit
the provider charges. Because Toman is one tenth of a Rial, the orchestrator's cross-provider sort
must convert to a common unit before comparing amounts.

**Alternative considered:** convert Alibaba train fares to Rial so the transport service stays
single-unit and the orchestrator needs no change. Rejected: it would report a synthetic unit the
provider never quotes, leave the `formatted` string inconsistent with the amount, and hide the trap
for the next provider added. Note this is the first service to mix units — today hotels are
uniformly Rial and accommodation uniformly Toman — so the conversion has to happen anyway before a
second unit appears in any merged result set.

### Per-provider timeout, and fixing the result-to-provider pairing first

Each provider call gets its own deadline instead of sharing one, so a slow provider drops out alone.
Because that makes partial failure common, the `zip` misalignment in `_run_parallel` is corrected in
the same change: results are returned paired with the crawler that produced them rather than
positional. Correcting it afterwards would leave a window where the new timeout behavior actively
corrupts cache attribution.

**Alternative considered:** give Alibaba a longer budget only, leaving the shared budget in place.
Rejected: it treats the symptom, and the misalignment defect stays live for any provider that fails.

### Filtering and normalization tables local to the provider

Provider-specific vocabularies stay in the Alibaba package rather than in shared modules:

- Cabin class: the provider emits single-character codes (`E`, `B`), not words. Map known codes to
  `economy`/`business` and pass unknown codes through unchanged.
- Aircraft: 13 distinct formats appear in one 37-item response (`100`, `MD8`, `BOEING 737`,
  `Airbus A320`, `Boeing 737-500`). Normalize case and manufacturer wording so one family does not
  appear under several labels in a single result set.
- Flight availability: `statusName` carries the authoritative Persian text - cancelled and
  capacity-complete. `isAllowedToBuy` is `true` for every item including cancelled ones, so it
  cannot be the filter.
- Train availability: exclude departures reporting zero purchasable seat capacity. This field was
  verified to vary by date with real values (1, 2, 3, 4, 6), and it is not a placeholder.

### Remove the unreachable hotel and accommodation calls

`search_hotels` targets a path that returns 404 on every verb, and `search_accommodations` targets a
host that does not resolve in DNS. Both are deleted rather than left in place behind a service
declaration that keeps them unreachable.

**Alternative considered:** keep the methods and register them for a future change. Rejected: they
are unreachable already - accommodation is not in the declared services - and leaving invented URLs
in the tree invites someone to trust them.

### Tests assert against captured payloads

The existing Alibaba fixture is self-invented: its `uniqueKey` values are the same strings the test
asserts on, and the test mocks the HTTP client, so no URL or verb is ever exercised. Fixtures are
replaced with captured responses, and tests assert the specific fields the fix depends on - carrier
identity, timestamps, currency, and the filtering rules - so that renaming a provider field fails.

## Risks / Trade-offs

- **Provider schema drift is undetectable.** No OpenAPI surface exists, so an upstream rename
  presents as empty or malformed results. → Tests assert on captured field-level detail rather than
  only on result counts, so drift fails loudly.
- **Request volume limits are unknown.** No rate-limit guidance was found, and the WAF is an F5
  BIG-IP ASM that already rejects some methods. → The change adds no new polling; the two-phase
  pattern is the minimum number of calls per search.
- **Filtering reduces result counts.** Cancelled, sold-out and zero-capacity departures are no
  longer returned, so counts drop by roughly a fifth for flights and by more for near-date trains.
  Cached responses therefore differ from anything observed before. → Breaking change, stated in the
  proposal; results remain sorted and priced identically.
- **Train price unit is inferred, not documented.** The conclusion rests on a coherent price ladder
  across service classes (second class 7.6M, 4-star 13M, 5-star 29.9M) and on the absence of any
  currency token in the payload, not on provider documentation. → Reported as Toman per the train
  spec, and confirmed against a booking total before release; a wrong reading is a factor of ten,
  not a rounding error.
- **The train price ladder could be re-read as Rial by a future maintainer.** → The unit is asserted
  in the spec and pinned by a test with a named expected value.
- **Two-phase flows make Alibaba the slowest provider by construction.** → It is given its own
  budget, and its cost is measured rather than assumed.
- **Cached results now exclude unbookable entries**, so a cache warmed before this change would
  still serve them for the remaining TTL. → Operators flushing the search cache clears it; the CLI
  already supports this.

## Migration Plan

No data migration and no schema changes to existing stored data. Deploy in one step: the flight
field mapping, the train service, the orchestrator timeout and pairing fixes, and the removal of
the two dead calls ship together, because the orchestrator change is what makes the slower
two-phase provider safe.

Rollback is a revert of the change. The only externally visible difference to roll back is Alibaba
result content, and the cache is the one thing that would not revert on its own, so flush the
search cache as part of rolling back.

## Open Questions

- Round-trip flights: whether `return_date` needs a different criteria shape or is served by the
  same request. Only one-way searches were verified.
- Whether `availableType` values beyond `Regular` require distinct handling in train results.
- The provider's actual request-rate ceiling, which could not be measured without deliberately
  provoking the WAF.