# Known Issues and How to Fix Them

Five problems found on 6 October 2026, written out in plain language. Each one
says what a user sees, why it happens, and what the fix would be. Re-verified
7 October 2026, when `iranbus` was added as a working bus provider. Issue 6 was
added 8 October 2026 alongside the fuel station endpoint.

Nothing here is fixed. Issue 1 is the most important.

**Since 7 October 2026, bus searches return real data** from the `iranbus`
provider (iranbus.ir, the national bus cooperatives union), which is
registered under the `bus` service and verified live. Bus coverage used to be
zero: FlyToday's bus host does not resolve, Safarchin's transport code is
unreachable dead code, and Alibaba's bus endpoint rejects every date. Issues 2
and 4 below are therefore about a *second* bus provider rather than about
having none.

---

## 1. A provider failure looks like "no results"

**What a user sees:** a request that should have returned data comes back
`200 OK` with an empty list, and a message saying there are zero results.

```
GET /api/v1/transport/trains?origin=Atlantis&destination=Mashhad&...
-> 200 OK
   {"status": "success", "total_results": 0, "results": []}
```

The honest answer would have been an error. Nothing in the response tells the
caller that a provider failed - it is indistinguishable from a real answer meaning
"there is nothing available on that date".

**Why it happens.** This is deliberate behaviour at three layers that nobody
reconciled:

- The Alibaba crawler raises an error when a search fails, because returning an
  empty list for a failure would be a lie.
- The orchestrator catches per-provider errors so one bad provider cannot fail a
  whole request. This is good - it stops a slow or broken provider taking down
  the others.
- The endpoint then takes whatever list it was handed, empty or not, and reports
  `total_results` with no indication of failure.

Each layer is defensible on its own. Together they turn "Alibaba was broken" into
"there are no trains", which is the worst possible outcome because it looks like
a successful answer.

**The fix.** Track failure explicitly rather than inferring it from an empty list.

The smallest change is to have the orchestrator remember which providers failed
and return that alongside the results:

```
{
  "status": "partial",
  "total_results": 10,
  "results": [ ... ],
  "failed_providers": ["flytoday"],
  "errors": {"flytoday": "Could not resolve host: train.flytoday.ir"}
}
```

That keeps the failure isolation - callers still get the 10 Alibaba trains - while
making the failure visible. It is a new field, so it is backwards compatible: code
that ignores it behaves exactly as it does today.

If a stronger guarantee is wanted, when *every* requested provider failed the
endpoint could return `502 Bad Gateway` rather than `200` with nothing, because
that is genuinely not a successful search. This changes observable behaviour, so
it is worth agreeing on before implementing.

**Where the code is.** `app/crawlers/orchestrator.py` (`_run_parallel` already
knows which providers failed and logs them) and the endpoint handlers in
`app/api/v1/`.

---

## 2. FlyToday contributes nothing at all

**What a user sees:** a train search with no provider filter returns only Alibaba
trains, and the logs are full of:

```
Could not resolve host: train.flytoday.ir
Could not resolve host: bus.flytoday.ir
```

**Why it happens.** FlyToday registers four services, but none of the hosts it
calls exist:

```
flytoday.ir           resolves
flight.flytoday.ir    DOES NOT RESOLVE
hotel.flytoday.ir     DOES NOT RESOLVE
villa.flytoday.ir     DOES NOT RESOLVE
train.flytoday.ir     DOES NOT RESOLVE
bus.flytoday.ir       DOES NOT RESOLVE
```

The parent domain resolves, so the company and site exist. Either FlyToday moved
its API to new host names, or these particular sub-domains were retired. Nothing
in the code or docs says which.

**The fix.** Someone needs to open flytoday.ir in a browser, search for a flight
and a train, and read the real network requests to find the current host and path.
That is a five-minute job with browser devtools open, and it is the same technique
that would unblock the Alibaba bus and hotel work in issue 4.

Once the real endpoint is known, updating `BASE_URL` and the per-service URLs at
the top of `app/crawlers/flytoday/crawler.py` is a small change. The response
parsing would need checking against the new shape, since the fixtures for FlyToday
were captured against whatever the old endpoints returned.

Until then, the honest options are to fix it or to stop advertising it. Right now
`/api/v1/providers` lists FlyToday as supporting four services, which overstates
what the system can actually do.

---

## 3. `safarchin` `transport` service is unreachable

**What a user sees:** nothing, directly. Safarchin's bus and train code never runs.

**Why it happens.** Safarchin registers `services={"flight", "transport"}` and
implements a `search_transport` method. But the orchestrator dispatches ground
transport on the *subtype*:

```python
service_name = query.transport_type.lower()      # "bus" or "train", never "transport"
```

So the registry is asked for `bus` and `train`, never `transport`:

```
lookup 'transport' -> ['safarchin']      nobody asks
lookup 'bus'       -> ['flytoday']
lookup 'train'     -> ['alibaba', 'flytoday']
```

`SafarchinCrawler.search_transport` is dead code. Nothing is broken visibly -
Safarchin flights work fine - but a provider appears ready for a service it can
never be asked for.

**The fix.** Decide which is true, then make the code match:

- *If Safarchin genuinely serves trains*: change the declaration to
  `services={"flight", "train"}` and confirm `search_transport` handles the train
  subtype. The method will also need to reject or implement `bus` the way the
  Alibaba crawler now does, so a bus search cannot silently return trains.
- *If it does not*: remove `search_transport` and the `transport` declaration, the
  same way the dead Alibaba hotel and accommodation calls were removed.

The first option is better if the code is real. Worth a quick look at the method
before deciding. Note that Safarchin is the provider this project is named after,
so having it actually contribute to more than just flights would be a meaningful
improvement.

---

## 4. Alibaba bus and hotel are not integrated

**What a user sees:** neither service is available. `/api/v1/providers` correctly
omits them, so there is no false promise.

**Why it happens.** Both endpoints exist and are reachable, but neither will accept
a request that has been constructed correctly.

**Bus** - `GET /api/v2/bus/available` validates its departure date and then
rejects every value:

```
"message": "تاریخ حرکت صحیح نمیباشد"  (departure date is not valid)
```

Ten formats were tried - Gregorian, Jalali, RFC 3339 with and without
milliseconds, `YYYYMMDD`, `DD-MM-YYYY`, URL- and space-separated - and all ten
produced the *identical* error. If a correctly formatted date produced the same
error as a nonsense one, the value is not reaching the field at all. This points
at a wrong parameter name, or a missing company or terminal identifier, rather
than a date format problem.

**Hotel** - `POST /api/v1/hotel/search` accepts RFC 3339 dates, then demands an
internal city identifier:

```
"message": "city id is not valid probably"
```

The frontend JavaScript confirms `cityId` is the right parameter *name*, so it is
the value space that is unknown. Integers, `"kish"`, `"Kish"`, `"ir-kish"` and
arrays were all refused.

**The fix.** Capture a real request. Open `www.alibaba.ir/bus-ticket` and
`www.alibaba.ir/hotel` in a browser with devtools open, perform a search, and read
the actual request: its URL, method, headers, and body. That single capture answers
both questions at once.

The bus equivalent of the work already done for the hotel's `cityId` would be
checking whether the site's own hotel results page embeds the identifier in its
server-rendered HTML, which sometimes avoids needing devtools.

Once captured, integration is straightforward: both services use the same two-phase
protocol already implemented in `app/crawlers/alibaba/protocol.py`, so the work is
mostly mapping fields.

**Why it was not done during implementation.** It needs a browser session, and the
automated tests run in a container with no browser available. Rather than guess at
a protocol, the decision was to integrate only what could be verified end to end
and leave the rest explicitly out of scope.

---

## 5. Duplicate train departures

**What a user sees:** the same train listed twice, identical in every visible way:

```
رجا  4 ستاره اتوبوسي صبا  dep=2026-10-22 09:20  arr=21:45  7,600,000 IRT  seats=4
رجا  4 ستاره اتوبوسي صبا  dep=2026-10-22 09:20  arr=21:45  7,600,000 IRT  seats=4
```

**Why it happens.** The provider returns two different `proposalId` values for one
physical departure - `23053898989` and `23053899014`. They are genuinely separate
booking offers from Alibaba's side, which is why each has its own identifier.

**The fix, and the risk.** Deduplicating on
`(train number, departure time, service class, company)` would collapse them, but
it would also hide cases where two offers really do differ - a discount on one, or
a different cancellation policy. Those differences are invisible in the current
response, so a caller cannot make the decision themselves.

The safer fix is to keep both and expose what distinguishes them, rather than
silently dropping one. Alibaba's payload does carry fields that could do this, such
as `fullPrice`, `discount`, `hasDiscount` and the cancellation rules in `crcn`.
Mapping at least one of those onto the result would let a caller see why there are
two rows.

Recommended: expose the distinguishing detail first, and only deduplicate if
duplicates still appear identical afterwards.

---

## Priority order

1. **Issue 1** - a provider failure that looks like success will mislead callers
   into thinking there is no availability. Small change, meaningful improvement.
2. **Issue 2** - FlyToday is dead weight, and advertising four services it cannot
   serve overstates the system.
3. **Issue 5** - cosmetic today, but confusing enough to cost a support question.
4. **Issue 4** - new capability rather than a defect. Needs a browser capture.
   Bus is now served by `iranbus`, so this is worth doing only if Alibaba's bus
   results are specifically wanted (its hotel half is still unbuilt).
5. **Issue 3** - invisible, but it hides working code and needs a decision on
   whether Safarchin's transport implementation is real.
6. **Issue 6** - not a defect in this codebase. Fuel station coverage comes from
   OpenStreetMap and is uneven on rural highways. The API already reports
   `largest_gap_km` so absence is not mistaken for fact; the underlying gap
   needs a coverage audit, or contributions to OpenStreetMap.

Issues 2 and 4 both need the same first step: open the provider's site in a browser
and watch what it actually requests.

---

## 6. Fuel station coverage is uneven

**What a user sees:** a route search that finds nothing for a long stretch.
On Tehran → Isfahan, with a 1 km corridor, stations appear near km 28 and then
nothing until roughly km 120 — a **92 km hole** in the middle of the trip.

**Why it happens.** OpenStreetMap's fuel coverage is not uniform. Iran has
3,924 mapped `amenity=fuel` nodes against roughly 3,800 real stations, so the
national total is close to complete. The gaps are local, not national: they
cluster on rural highway stretches where mapping has thinned.

**Whether this is a mapping gap or genuinely empty road is unresolved.**
Probes for other amenities in the same stretch came back with zero pharmacies,
which is not credible for rural Iran and points at unmapped ground rather than
an absence of settlements. Those probes were rate-limited part of the time, so
the question is not settled. Either way, the API's behaviour is the same.

**What the API does about it.** The response reports `largest_gap_km`, the
longest stretch of route between consecutive returned stations. This is
deliberate: a bare empty list reads as "there is no fuel here", which is a
claim about the world this system cannot support. A reported gap reads as what
it is — *we found nothing here*, which may mean the ground is unmapped.

```
GET /api/v1/fuel-stations?origin=Tehran&destination=Isfahan&radius_m=1000

{
  "status": "success",
  "total_results": 22,
  "data_source": "openstreetmap",
  "route": {"origin": "Tehran", "destination": "Isfahan",
            "distance_km": 437.96, "duration_h": 4.82},
  "corridor_radius_m": 1000,
  "largest_gap_km": 92.5,
  "results": [ ... ]
}
```

**How it could be fixed.** The fix is not in this API. If the stretch is
unmapped, the correct action is to contribute those stations to OpenStreetMap;
the response shape will pick them up with no code change. A coverage audit
against a second source would settle which case this is.

**A related trap, already handled.** Around 10% of stations cannot be
classified by fuel type, mostly because they carry no name at all. They are
reported as `unknown` rather than defaulted to petrol — defaulting raises
apparent coverage but would send a diesel driver to a CNG-only pump. Note also
that `پمپ گاز` means **CNG**, not petrol: Persian for natural gas is the same
word an English reader takes to mean gasoline, and matching on it misfiles
about 28% of the country. The classifier orders its patterns to make that
mistake unrepresentable, and the ordering is pinned by test.