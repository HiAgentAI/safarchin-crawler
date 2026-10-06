# Alibaba.ir Provider Integration

How the Alibaba provider works, and what is known to be incomplete.

**Status: flights and trains are live and verified. Bus and hotel are not integrated.**

Related: [PROVIDERS.md](PROVIDERS.md) for the full provider matrix,
[KNOWN_ISSUES.md](KNOWN_ISSUES.md) for outstanding problems.

---

## Services

| Service | Endpoint | State |
|---|---|---|
| Flights | `/api/v1/flights/domestic/available` | Live, verified |
| Trains | `/api/v1/train/available` | Live, verified |
| Buses | `/api/v2/bus/available` | Not integrated - see [Not integrated](#not-integrated) |
| Hotels | `/api/v1/hotel/search` | Not integrated - see [Not integrated](#not-integrated) |

Base host: `https://ws.alibaba.ir` (45.89.201.11), a separate origin from the
public site at `www.alibaba.ir` (45.89.201.10).

### Verified live

```
GET /api/v1/flights/search?origin=Tehran&destination=Mashhad&depart_date=2026-10-30&providers=alibaba
-> 2 bookable flights: 123,224,600 IRR (economy), 215,654,300 IRR (business)

GET /api/v1/transport/trains?origin=Tehran&destination=Mashhad&depart_date=2026-10-22&passengers=1&providers=alibaba
-> 10 bookable departures, 7,600,000 - 29,900,000 IRT
   including an overnight journey: dep=2026-10-22 16:50  arr=2026-10-23 03:00
```

## Authentication

**None.** No API key, no session cookie, and no custom request header are
required. TLS impersonation via `curl_cffi` (already used by the shared HTTP
client) made no measurable difference to success rate or latency for this
provider, and the follow-up request works with no cookie jar.

The host sits behind an **F5 BIG-IP ASM** WAF that sets a `TS01...` cookie and
already rejects some non-standard methods with `403 Request Rejected`. Response
headers identify the backend as `ab-resp-service: Indra.Backend`.

No rate-limit guidance was found. The two-phase pattern below is already the
minimum number of calls per search.

---

## The two-phase protocol

Every availability search takes two round trips. **The first response is not a
result set** - it contains only a handle.

```
 1. POST <endpoint>          criteria in, handle out
        |
        |   {"success":true,"result":{...handle...}}
        v
 2. GET  <endpoint>/<handle> the actual results
```

The handle is encoded differently per service, but the protocol is identical:

| | Flights | Trains |
|---|---|---|
| Criteria | `{"origin","destination","departureDate","adult","child","infant"}` | `{"origin","destination","departureDate","passengerCount"}` |
| Handle | `result.requestId` (opaque string) | `result` (base64-encoded criteria echo) |
| Result envelope | `{"result":{"departing":[...]}}` | `{"departing":[...]}` (top level) |

Two traps this protocol creates, both handled in
`app/crawlers/alibaba/protocol.py`:

- **The verb is not interchangeable.** A `GET` on the criteria URL returns
  `405 Method Not Allowed` with `Allow: POST`.
- **An empty `result` is not "no results".** A successful criteria response
  contains no flights or departures at all. Treating it as a result set returns
  zero rows while reporting success.

### Error envelopes

Two backend stacks sit behind this host, so two failure shapes exist and both
must be recognised:

```jsonc
// ASP.NET style - flights, trains
{"result":null,"success":false,
 "error":{"errorCode":1,"message":"تاریخ رفت خالی است.","details":"DepartureDate"}}

// Go style - hotels
{"status":"error","message":"city id is not valid probably","error":true}
```

`unauthorizedRequest: true` is also checked.

---

## Dates

**Gregorian only.** A Jalali string is parsed as a Gregorian year and rejected:

```
DepartureDate: UtcValue: 1405/07/23, UtcNow: 2026/10/05
```

Callers may pass either calendar; `to_gregorian` in `app/utils/calendar.py`
converts before the request is sent.

---

## Cities: names are resolved to codes

Alibaba accepts **only an exact IATA code** in `origin`/`destination`. Every other
form is rejected with HTTP 400:

```
THR      -> MHD      200
Tehran   -> Mashhad  400
TEHRAN   -> MASHHAD  400
THR      -> Mashhad  400
Tehran   -> MHD      400
تهران     -> مشهد      400
```

Since this API's endpoints are documented in terms of city names (`origin=Tehran`),
`app/crawlers/alibaba/locations.py` translates before sending. English and Persian
names both work, as do IATA codes in any casing.

An unresolvable city raises a `ValueError` rather than being forwarded, because a
forwarded bad value produces HTTP 400, which the orchestrator reports as an empty
result list - indistinguishable from having no availability.

### One data conflict worth knowing about

`app/crawlers/safarchin/airports.py` indexes English names by slug, and two of its
entries share the slug `Tehran`:

```
THR   slug='Tehran'  en='Tehran'         fa='تهران'
IKA   slug='Tehran'  en='Imam Khomaini'  fa='امام خمینی'
```

The later entry wins, so `find_airport("Tehran")` returns **IKA** - which Alibaba
rejects. The Alibaba resolver therefore maps the city name `Tehran` to `THR`
explicitly. Anyone who genuinely wants Imam Khomaini can still pass `IKA`, which is
passed through untouched.

Verified accepted for flights and trains: `THR`, `MHD`, `IFN`, `SYZ`, `TBZ`, `GBT`,
`AZD`, `ADU`, `KER`, `OMH`. `RAS` and `KSH` are rejected by the **train** endpoint;
these cities appear to have no rail service, and Alibaba answers 400 rather than an
empty result, so a train search for them reports no availability.

---

## Price units differ by service

**This is the highest-risk detail in this provider.**

| Service | Unit | Observed range (THR-MHD) |
|---|---|---|
| Flights | **IRR** (Rial) | 100,000,000 - 169,021,000 |
| Trains | **IRT** (Toman) | 7,600,000 - 36,200,000 |

Toman is one tenth of a Rial. The payloads contain **no currency token**, so the
unit was established from evidence outside the API:

1. **The public train page labels its own currency.** `www.alibaba.ir/train/thr-mhd`
   renders `تومان` (Toman) and contains no occurrence of `ریال` (Rial).
2. **The magnitudes force a ten-fold divergence between the two services.** A
   median flight fare is ~119,000,000 while a 4-star train fare is ~15,200,000.
   Read in one unit, a flight would cost roughly eight times a slower, premium
   overnight train on the same corridor - impossible. Read as Rial for flights
   and Toman for trains, the two land in the same range (~11.9M and ~15.2M Toman),
   which is correct for a 1.5-hour flight versus an 11-hour 4-star sleeper.
3. **The price ladder is coherent in Toman** and absurd in Rial: a 4-star
   compartment at 1,520,000 Rial (~$19) would be far cheaper than an economy
   flight, while 15,200,000 Toman (~$190) is the expected order.

A completed booking total was **not** obtained, since that requires an account and
a real purchase. The evidence above is strong but indirect; a booking total remains
worth checking before release. See [Open risks](#open-risks).

Because services can disagree, the orchestrator normalises amounts before
sorting. Without that, a Toman amount is ranked as if it were ten times cheaper
than an equal Rial amount.

---

## Field mappings

Captured from live responses. Alibaba publishes **no OpenAPI document** - swagger
paths redirect to the public homepage - so these are pinned by tests against the
captures in `tests/fixtures/`.

### Flights

| Result field | Provider field | Note |
|---|---|---|
| `id` | `uniqueKey` | Route/date/carrier/fare composite, unique per flight |
| `outbound[].airline_name` | `airlineName` | **Flat.** There is no nested `airline` object |
| `outbound[].airline_code` | `airlineCode` | Flat, may be absent |
| `outbound[].flight_number` | `flightNumber` | |
| `outbound[].aircraft` | `aircraft` | Normalised - see below |
| `outbound[].departure_time` / `departure_date` | `leaveDateTime` | Full ISO timestamp |
| `outbound[].arrival_time` / `arrival_date` | `arrivalDateTime` | Full ISO; may be the next day |
| `outbound[].cabin_class` | `classType` | Single-char code, mapped to `economy`/`business`/`first` |
| `outbound[].origin_code` | `origin` | **Not** `originCode` - flights and trains differ here |
| `outbound[].destination_code` | `destination` | As above |
| `price.amount` | `priceAdult` | IRR |
| `price.formatted` | derived | e.g. `107,590,000 ریال` |
| `is_charter` | `isCharter` | |
| `available_seats` | `seat` | |

### Trains

| Result field | Provider field | Note |
|---|---|---|
| `id` | `proposalId` | Stable across reads of one handle |
| `company_name` | `companyName` | Persian, e.g. `رجا` |
| `service_class` | `wagonName`, else `wagonClass` | Codes observed: `EC`, `EL`, `LX`, `S`, `V` |
| `origin_terminal` | `originName`, else `originCode` | Persian name, else IATA |
| `destination_terminal` | `destinationName`, else `destinationCode` | |
| `departure_date` / `departure_time` | `departureDateTime` | Full ISO |
| `arrival_time` | `arrivalDateTime` | Prefixed with its date when it differs from departure |
| `price.amount` | `cost` | **IRT** |
| `available_seats` | `maxPassengerCount` | Zero means not purchasable |

Journeys crossing midnight are common - 20 of 26 departures in one capture
arrived the following day - so the arrival date is reported rather than only a
time of day.

---

## Availability filtering

### Flights

`statusName` is the authoritative signal. Two values mean the flight cannot be
booked:

| `status` | `statusName` | Meaning |
|---|---|---|
| `C` | `تکمیل ظرفیت` | Capacity complete / sold out |
| `X` | `کنسل شده` | Cancelled |
| `3`,`5`,`6`,`7`,`9`,`10` | `""` (empty) | Bookable |

**`isAllowedToBuy` is not a usable filter.** It is `true` for every item in a
captured response, including cancelled ones. A test asserts this stays true, so
that if the provider ever changes it the filtering rule gets revisited rather
than silently doubled up.

Unbookable flights also carry a placeholder fare of exactly `100,000,000` and
`seat: 0`.

### Trains

A departure is excluded when `maxPassengerCount` is zero. This field carries real
inventory - values of 1, 2, 3, 4 and 6 were observed varying by date - and is not
a placeholder.

**Availability is tight near the departure date.** One capture three days out had
24 of 26 departures at zero capacity, so a filtered result can legitimately be
small or empty. That is a correct answer, not a failure.

---

## Normalisation

### Aircraft

A single 13-flight response contained six different designations for the same
families. `normalize_aircraft` collapses them:

| Raw | Normalised |
|---|---|
| `737`, `BOEING 737`, `Boeing 737` | `Boeing 737` |
| `319`, `320`, `A320`, `Airbus A320` | `Airbus A319` / `Airbus A320` / `Airbus A320` |
| `A310` | `Airbus A310` |
| `100` | `Fokker 100` |
| `Boeing 737-500` | `Boeing 737-500` |
| `MD8` | `MD8` (passed through - variant not confidently identifiable) |

Only unambiguous families are mapped. Unrecognised codes pass through unchanged
rather than being guessed at, since an unfamiliar code is still information.

### Cabin class

The provider emits single-character codes (`E`, `B`) rather than words. Mapped to
the project vocabulary; an unmapped code passes through rather than silently
becoming economy.

---

## Not integrated

### Buses

`GET /api/v2/bus/available` is reachable and validates its `DepartureDate`:

```
{"result":null,"success":false,
 "error":{"errorCode":100031,"message":"تاریخ حرکت صحیح نمیباشد","details":"DepartureDate"}}
```

Ten date encodings were tried - Gregorian, Jalali, RFC 3339 with and without
milliseconds, `YYYYMMDD`, `DD-MM-YYYY`, and URL- and space-separated forms - and
every one produced the *identical* error. An identical error across valid and
invalid formats indicates the value is not binding to the field, so this is a
parameter-name or missing-identifier problem rather than a format problem.

A bus search reaching this endpoint must not silently return trains;
`search_transport` raises `NotImplementedError` for `transport_type="bus"`.

### Hotels

`POST /api/v1/hotel/search` accepts RFC 3339 dates and then requires an
undocumented internal `cityId`:

```
{"status":"error","message":"city id is not valid probably","error":true}
```

The frontend bundle confirms `cityId` is the correct parameter *name*, so the
value space is an internal identifier that has not been recovered. Values tried
included integers, `"kish"`, `"Kish"`, `"ir-kish"` and arrays.

Both need a captured real request - most easily from a browser session - before a
behaviour contract can be written for them.

---

## Open risks

- **Train price unit rests on indirect evidence.** The site's own train page labels
  the currency as Toman and the magnitudes force the ten-fold divergence from
  flights, but no completed booking total was obtained. If this is wrong, every
  train price is out by a factor of ten. Pinned by a named test value; worth
  confirming against a real booking before release.
- **No OpenAPI surface, so upstream renames are undetectable.** Mitigated by
  tests asserting on captured field-level detail, which fail loudly on a rename.
- **Filtered result counts drop** roughly a fifth for flights and much more for
  near-date trains, compared with anything observed before this provider was
  fixed. Cached responses warmed before the change still serve unbookable
  entries for the remainder of their TTL; flush the search cache after deploying.
- **`statusName` values are Persian display strings** used as a data signal.
  These are undocumented and could be reworded; `status` codes are the fallback.