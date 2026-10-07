# Tasks

## 1. Orchestrator correctness fixes

These land before the Alibaba work because Alibaba's two-phase flow makes slow and partial failures
routine, and the currency-aware sort is required once trains mix units. See `design.md` - Decisions.

- [x] 1.1 Correct result-to-provider pairing in `CrawlerOrchestrator._run_parallel` so results are returned alongside the crawler that produced them rather than positionally, and add a unit test where one provider raises and the survivor is asserted to be attributed to itself and recorded in cache under its own name
- [x] 1.2 Replace the single shared `asyncio.wait_for` with a per-provider deadline, and add a unit test where a provider exceeds its budget while a sibling completes, asserting the sibling's results are returned and the slow provider contributes nothing
- [x] 1.3 Make the cross-provider result sort currency-aware so mixed Rial and Toman amounts are compared in a common unit, and add a unit test mixing both currencies in one service and asserting the cheaper result sorts first
- [x] 1.4 Run the existing orchestrator test suite and verify all pre-existing orchestrator tests still pass unchanged

## 2. Alibaba provider foundation

- [x] 2.1 Add a two-phase search helper in `app/crawlers/alibaba/` that submits criteria with `POST`, extracts the handle, and fetches results with `GET`, and add a unit test with a stubbed HTTP client asserting the verb sequence, that the criteria response is never parsed as results, and that a handle-retrieval failure surfaces as an error rather than an empty list
- [x] 2.2 Replace `tests/fixtures/alibaba_flight_response.json` with a captured live flight payload and add a captured train payload, then add a test asserting both fixtures parse and contain the specific fields the mapping depends on, so an upstream rename fails a test rather than silently yielding empty results
- [x] 2.3 Declare the train service on `AlibabaCrawler.supported_services` and verify through a registry test that Alibaba is discovered for the train service and for flights

## 3. Alibaba flight search

- [x] 3.1 Rewrite `AlibabaCrawler.search_flights` to use the two-phase helper with `POST`, and add a test asserting `POST` is used and that a flight count is returned from the captured payload, replacing the existing mock that never exercises a verb
- [x] 3.2 Map carrier name, carrier code and flight number from the flat provider fields, and add a test asserting carrier identity is populated on every captured flight rather than falling back to a default
- [x] 3.3 Map departure and arrival as full timestamps including their calendar dates, and add a test asserting an overnight arrival reports the later date and a distinct departure date
- [x] 3.4 Map the provider's single-character cabin code to the project vocabulary, and add a test asserting `E` maps to `economy`, `B` maps to `business`, and an unmapped code passes through unchanged
- [x] 3.5 Add aircraft normalization so equivalent aircraft are not reported under differing labels, and add a test covering the bare numeric, uppercase, spelled-out and manufacturer-prefixed forms observed in a live response
- [x] 3.6 Exclude flights the provider reports as cancelled or at full capacity, and add a test asserting both are removed, a flight with no explicit status is retained, and that the provider's buyable flag is not used as the filter
- [x] 3.7 Report flight prices in Rial with the unit labeled, and add a test asserting the currency label and an exact expected amount
- [x] 3.8 Confirm Gregorian dates are transmitted for a Jalali input using the existing `to_gregorian` helper, and add a test asserting a Jalali query reaches the provider as the equivalent Gregorian date

## 4. Alibaba train search

- [x] 4.1 Implement `AlibabaCrawler.search_transport` for trains via the two-phase helper, sending the passenger count under the provider's expected field name, and add a test asserting a departure list is returned from the captured payload
- [x] 4.2 Map departures onto `TransportResult`, and add a test asserting operating company, service class, origin and destination, and a provider-stable identifier are populated on every departure
- [x] 4.3 Report departure and arrival with their calendar dates so an overnight journey is not presented as arriving before it departs, and add a test asserting the arrival date is the later date
- [x] 4.4 Report train prices in Toman with the unit labeled, and add a test pinning the currency label and an exact expected amount by name, guarding the ten-fold difference from flight prices
- [x] 4.5 Exclude departures reporting zero purchasable seat capacity, and add a test asserting zero-capacity departures are removed, a positive-capacity departure is retained with its capacity, and a predominantly unavailable search is not reported as a failure
- [x] 4.6 Verify through an API-level test that a train search with no provider filter includes Alibaba and that a search naming only Alibaba queries no other provider

## 5. Cleanup, documentation, and release verification

- [x] 5.1 Remove `search_hotels` and `search_accommodations` from `AlibabaCrawler`, and add a test asserting no Alibaba call targets a host that fails DNS resolution or a path that returns 404
- [x] 5.2 Update `README.md` to state that Alibaba serves flights and trains, that bus and hotel are not integrated, and verify every documented request parameter matches the implemented query schema
- [x] 5.3 Add `docs/ALIBABA_PROVIDER.md` documenting the two-phase protocol, both endpoint shapes, the captured field mappings, the per-service price units, and the unverified status vocabulary, then verify each documented field against a live response
- [x] 5.4 Run the full test suite and verify it passes with no previously passing test removed to accommodate the new behavior
- [x] 5.5 Confirm the train price unit against a live booking total before release, since the Toman reading is inferred from the price ladder rather than provider documentation, and correct the currency if it proves wrong
- [x] 5.6 Flush the search cache and verify a post-deploy Alibaba flight and train search return live bookable results rather than entries cached before the change