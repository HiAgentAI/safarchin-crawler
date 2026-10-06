# Spec Delta

## Purpose

Defines how the system retrieves bookable domestic passenger train departures from Alibaba,
including its two-phase request protocol, its distinct price unit from the same provider's flight
service, and the seat-capacity rules that decide which departures are offered to callers.

## ADDED Requirements

### Requirement: Two-phase train retrieval
The system SHALL submit search criteria in a single request, then use the handle returned by that
request to retrieve the departure list. The criteria response SHALL NOT be treated as a departure
list.

#### Scenario: Successful search returns departures
- **WHEN** a valid origin, destination, departure date and passenger count are submitted
- **THEN** the system retrieves departures using the handle from the criteria response
- **AND** returns one result per departure the provider reports

#### Scenario: Criteria response echoes the criteria
- **WHEN** the criteria request completes successfully
- **THEN** the system does not treat the echoed criteria as departures
- **AND** retrieves the departure list before determining that no departures exist

#### Scenario: Handle cannot be retrieved
- **WHEN** the departure list cannot be retrieved for a returned handle
- **THEN** the system reports the Alibaba train search as failed
- **AND** does not return an empty list as though no departures existed

### Requirement: Passenger count is supplied
The system SHALL transmit the requested passenger count with the train search criteria.

#### Scenario: Single passenger requested
- **WHEN** a caller requests travel for one passenger
- **THEN** the criteria request carries a passenger count of one

#### Scenario: Passenger count omitted by the provider call
- **WHEN** criteria are submitted without a passenger count
- **THEN** the provider rejects the request as invalid
- **AND** the system treats that rejection as a search failure rather than an empty result

### Requirement: Train service participation
The system SHALL offer Alibaba train search as a provider of the train transport service, so that
it is included in train searches and can be selected or excluded by name.

#### Scenario: Train search without a provider filter
- **WHEN** a caller requests a train search with no provider filter
- **THEN** Alibaba is among the providers searched

#### Scenario: Caller selects Alibaba explicitly
- **WHEN** a caller requests a train search naming only Alibaba
- **THEN** no other provider is queried

### Requirement: Departure and arrival across calendar days
The system SHALL report both departure and arrival with a calendar date, because a train journey
frequently crosses midnight.

#### Scenario: Journey arrives the next morning
- **WHEN** a departure occurs late in the evening and arrival is on the following date
- **THEN** the result reports the arrival date as the later date
- **AND** the result does not present the arrival as occurring before the departure

#### Scenario: Journey arrives the same day
- **WHEN** arrival occurs on the departure date
- **THEN** the result reports both dates as the same date

### Requirement: Bookable departures only
The system SHALL NOT return a departure whose purchasable seat capacity is zero.

#### Scenario: Departure with zero purchasable capacity
- **WHEN** the provider reports zero purchasable seats for a departure
- **THEN** that departure is excluded from the returned results

#### Scenario: Departure with purchasable capacity
- **WHEN** the provider reports a positive purchasable seat capacity
- **THEN** that departure is retained
- **AND** the capacity is reported on the result

#### Scenario: Most departures unavailable for a near date
- **WHEN** a search returns predominantly zero-capacity departures
- **THEN** the result reflects only the departures that retain capacity
- **AND** the search is not reported as failed

### Requirement: Train price unit
The system SHALL report Alibaba train prices in Iranian Toman, and SHALL label the unit as such.
This unit differs from Alibaba's flight prices, which are reported in Rial.

#### Scenario: Price returned from a departure
- **WHEN** the provider supplies a fare for a departure
- **THEN** the result reports that amount in Iranian Toman
- **AND** the currency label reads Iranian Toman

#### Scenario: Flight and train prices compared
- **WHEN** a caller compares a flight price and a train price from the same provider
- **THEN** the two results carry different currency units
- **AND** neither amount is presented as though it were in the other's unit

### Requirement: Operating company and service class
Every returned departure SHALL identify the operating company and the service class of the coach,
so that callers can distinguish departures of different grade on the same route.

#### Scenario: Departure carries company and class
- **WHEN** a departure is returned by the provider
- **THEN** the result reports the operating company name
- **AND** the result reports the service class as reported by the provider

#### Scenario: Several classes on one route
- **WHEN** a search returns departures of differing service classes
- **THEN** each result carries its own service class
- **AND** the classes are not collapsed into a single route-level value

### Requirement: Departure identity
Every returned departure SHALL carry a provider-stable identifier.

#### Scenario: Repeated retrieval of one handle
- **WHEN** the same handle is retrieved more than once
- **THEN** departures from separate retrievals can be matched by identifier
- **AND** results can be cached and de-duplicated by that identifier

### Requirement: Date input conversion
The system SHALL accept a Jalali or Gregorian departure date from the caller and SHALL transmit
the equivalent Gregorian date to the provider.

#### Scenario: Jalali date supplied
- **WHEN** a caller supplies a Jalali departure date
- **THEN** the corresponding Gregorian date is transmitted to the provider
- **AND** the search is executed rather than rejected

#### Scenario: Same origin and destination requested
- **WHEN** a caller requests a train journey whose origin equals its destination
- **THEN** the provider rejects the request
- **AND** the system surfaces that rejection rather than reporting an empty departure list

## Out of Scope

Bus availability from Alibaba is not specified here. Its search endpoint is reachable and validates
its departure date parameter, but rejects every date encoding attempted with an identical error,
indicating the value does not bind to the field. That needs a captured real request before a
behavior contract can be stated.