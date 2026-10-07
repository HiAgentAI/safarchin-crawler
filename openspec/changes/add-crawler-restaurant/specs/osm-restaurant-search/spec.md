# Spec Delta

## Purpose

Enables querying OpenStreetMap for restaurants located within an administratively bounded city, including boundary resolution, Overpass query execution, record deduplication, and currency-of-record reporting.

## ADDED Requirements

### Requirement: Administrative boundary resolution
The system SHALL resolve a city name in Persian or English to an OpenStreetMap administrative boundary relation identifier using Nominatim geocoding.

#### Scenario: Successful boundary resolution
- **WHEN** a valid Persian or English city name is provided
- **THEN** the system resolves the city to its administrative boundary relation ID
- **AND** caches the resolution result to prevent redundant external geocoding requests

#### Scenario: Unknown city resolution
- **WHEN** a city name cannot be resolved to an administrative boundary
- **THEN** the system returns a boundary-not-found error
- **AND** does not execute a restaurant query against Overpass

### Requirement: Multi-geometry restaurant retrieval
The system SHALL query OpenStreetMap via Overpass API for nodes, ways, and relations tagged with `amenity=restaurant` located inside the resolved administrative boundary area.

#### Scenario: Retrieval includes node and area geometries
- **WHEN** an Overpass query is executed for a resolved city boundary
- **THEN** the system retrieves both point (node) and polygon (way/relation) restaurants
- **AND** computes center coordinates for way and relation geometries

#### Scenario: City with no restaurants
- **WHEN** a resolved boundary contains zero matching restaurant elements
- **THEN** the system returns an empty result list with a successful status

### Requirement: Record deduplication
The system SHALL collapse duplicate records where the same restaurant is mapped as both a point-of-interest node and a building way or relation sharing the same name and proximity.

#### Scenario: Node and way duplicate collapsed
- **WHEN** a restaurant exists in the Overpass response as both a node and a way with matching name and overlapping location
- **THEN** the system returns a single consolidated restaurant result
- **AND** merges available contact and metadata tags

#### Scenario: Distinct restaurants with same name
- **WHEN** two restaurants share the same brand or name but have distinct, separated coordinates
- **THEN** the system retains both distinct restaurants in the result list

### Requirement: Currency-of-record reporting
Every restaurant result SHALL report the timestamp when its underlying OpenStreetMap element was last edited or surveyed.

#### Scenario: Last edited date populated
- **WHEN** a restaurant element is parsed from Overpass
- **THEN** the result includes a `last_edited` timestamp reflecting the element's OSM modification date

### Requirement: Price and rating omission
The restaurant response schema SHALL deliberately omit price, price range, and rating fields, reflecting the absence of this data in OpenStreetMap.

#### Scenario: Schema guarantees no artificial price or rating
- **WHEN** restaurant search results are returned
- **THEN** results contain name, coordinates, address, tags, and currency of record
- **AND** do not contain price, currency, or review score fields

### Requirement: Upstream failure distinction
The system SHALL distinguish upstream provider failures such as rate limits (HTTP 429) and timeouts (HTTP 504) from an empty result set.

#### Scenario: Overpass timeout or rate limit
- **WHEN** the Overpass API responds with an HTTP 429, 504, or network timeout
- **THEN** the system reports a provider failure error
- **AND** does not report zero restaurants found
- **AND** does not write an empty result set to the cache
