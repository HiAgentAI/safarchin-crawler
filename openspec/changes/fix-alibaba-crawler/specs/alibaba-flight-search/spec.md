# Spec Delta

## Purpose

Defines how the system retrieves bookable domestic flight availability from Alibaba, including the
provider's two-phase request protocol, the mapping of live response fields, and the rules that
decide which flights are offered to callers.

## ADDED Requirements

### Requirement: Two-phase flight retrieval
The system SHALL submit search criteria in a single request, then use the handle returned by that
request to retrieve the result set. The criteria response SHALL NOT be treated as a result set.

#### Scenario: Successful search returns flights
- **WHEN** a valid origin, destination and departure date are submitted
- **THEN** the system retrieves flights using the handle from the criteria response
- **AND** returns one result per flight the provider reports as departing

#### Scenario: Criteria response carries no flights
- **WHEN** the criteria request completes successfully
- **THEN** the system does not report zero flights on the basis of that response alone
- **AND** retrieves the result set before determining that no flights exist

#### Scenario: Handle cannot be retrieved
- **WHEN** the result set cannot be retrieved for a returned handle
- **THEN** the system reports the Alibaba flight search as failed
- **AND** does not return an empty list as though no flights existed

### Requirement: Flight identity and carrier attribution
Every returned flight SHALL carry a provider-stable identifier, an operating carrier name, a
carrier code where the provider supplies one, and a flight number.

#### Scenario: Carrier attribution is populated
- **WHEN** a flight is returned by the provider
- **THEN** the result includes the operating carrier name as reported by the provider
- **AND** the carrier code and flight number are populated where supplied

#### Scenario: Carrier code absent for a flight
- **WHEN** the provider omits a carrier code for a specific flight
- **THEN** the result omits that code rather than substituting a placeholder
- **AND** the flight remains in the result set

### Requirement: Departure and arrival timestamps
The system SHALL report departure and arrival as full timestamps carrying a calendar date, not only
a time of day.

#### Scenario: Same-day arrival
- **WHEN** a flight arrives on its departure date
- **THEN** the result reports the arrival date and time of that date

#### Scenario: Overnight arrival
- **WHEN** a flight arrives after midnight on a later date
- **THEN** the result reports the later arrival date
- **AND** the departure date is reported as the distinct earlier date

### Requirement: Cabin class normalization
The system SHALL translate the provider's cabin class code into the project's cabin class
vocabulary before returning a result.

#### Scenario: Provider economy code
- **WHEN** the provider reports an economy cabin code
- **THEN** the result reports cabin class `economy`

#### Scenario: Provider business code
- **WHEN** the provider reports a business cabin code
- **THEN** the result reports cabin class `business`

#### Scenario: Provider reports an unmapped cabin code
- **WHEN** the provider reports a cabin code with no defined mapping
- **THEN** the result carries the provider's raw code
- **AND** the flight remains in the result set

### Requirement: Aircraft normalization
The system SHALL present an aircraft designation consistently, so that equivalent aircraft are not
reported under materially different labels for the same search.

#### Scenario: Provider supplies a bare numeric aircraft code
- **WHEN** the provider reports an aircraft as a bare numeric code
- **THEN** the result presents that code in the same normalized form as a spelled-out equivalent

#### Scenario: Provider supplies an inconsistent spelling
- **WHEN** the provider reports the same aircraft family with differing capitalization or
  manufacturer wording across flights in one result set
- **THEN** the result set uses one consistent designation for that family

### Requirement: Bookable flights only
The system SHALL NOT return a flight that the provider reports as cancelled or as having no
remaining capacity.

#### Scenario: Cancelled flight present in provider feed
- **WHEN** the provider marks a flight as cancelled
- **THEN** that flight is excluded from the returned results

#### Scenario: Sold-out flight present in provider feed
- **WHEN** the provider marks a flight as having no remaining capacity
- **THEN** that flight is excluded from the returned results

#### Scenario: Provider reports no explicit status
- **WHEN** a flight carries no cancellation or capacity status
- **THEN** the flight is retained in the returned results

### Requirement: Flight price unit
The system SHALL report Alibaba flight prices in Iranian Rial, and SHALL label the unit as such
rather than relying on the caller to infer it.

#### Scenario: Price returned from a flight
- **WHEN** the provider supplies an adult fare
- **THEN** the result reports that amount in Iranian Rial
- **AND** the currency label reads Iranian Rial

### Requirement: Date input conversion
The system SHALL accept a Jalali or Gregorian departure date from the caller and SHALL transmit
the equivalent Gregorian date to the provider.

#### Scenario: Jalali date supplied
- **WHEN** a caller supplies a Jalali departure date
- **THEN** the corresponding Gregorian date is transmitted to the provider
- **AND** the search is executed rather than rejected

#### Scenario: Gregorian date supplied
- **WHEN** a caller supplies a Gregorian departure date
- **THEN** that date is transmitted to the provider unchanged

### Requirement: Isolated provider failure
When the Alibaba flight search fails or exceeds its time budget, the system SHALL still return
results from other providers requested in the same search.

#### Scenario: Alibaba fails while another provider succeeds
- **WHEN** a multi-provider flight search is requested
- **AND** the Alibaba flight search fails
- **THEN** results from the other providers are returned
- **AND** the Alibaba failure is recorded rather than raised as a whole-request error

#### Scenario: Alibaba exceeds its time budget
- **WHEN** the Alibaba flight search does not complete within its allotted budget
- **THEN** results from providers running alongside it are still returned
- **AND** Alibaba contributes no flights to that response

## Out of Scope

Bus and hotel availability from Alibaba are not specified here. Neither has a reachable search that
accepts a complete valid request, so neither has a behavior contract to state.