# IranHotelOnline Provider Documentation & AI Agent Integration Guide

This document provides a comprehensive integration guide for the **IranHotelOnline (ایران هتل آنلاین)** provider within the Safarchin Travel Crawler API.

> IranHotelOnline serves hotel and accommodation, and its results are **never cached**
> so prices stay real-time. See [PROVIDERS.md](PROVIDERS.md) for the full provider and
> service matrix.

---

## 📌 1. Provider Overview

| Attribute | Specification |
| :--- | :--- |
| **Provider Name** | `iranhotel` |
| **Category** | Domestic Hotels, Boutique Hotels, Hotel Apartments, Eco-resorts |
| **Target Website** | [https://www.iranhotelonline.com](https://www.iranhotelonline.com) |
| **Backend API Gateway** | `https://www.iranhotelonline.com/api/mvc` |
| **Image CDN** | `https://cdn.iranhotelonline.com` |
| **Currency** | Iranian Rials (IRR) converted to formatted representations |
| **Authentication** | Public REST API (No API key / token required) |
| **CDN / Infrastructure** | ArvanCloud CDN with Express.js SSR |

---

## 🏗️ 2. Architecture & Data Flow

```mermaid
flowchart TD
    Client["Client / AI Agent"] -->|"GET /api/v1/hotels/search?cache_ttl=N"| API["FastAPI Router (/hotels)"]
    API --> Orchestrator["CrawlerOrchestrator"]
    Orchestrator -->|"Check Cache for Cacheable Providers"| Redis[("Redis Cache")]
    
    subgraph IranHotel Crawler Subsystem (Live Scrape Only - Never Cached)
        Orchestrator -->|"Always Live Scrape"| IHO["IranHotelCrawler"]
        IHO -->|"1. Date Normalization"| Calendar["Calendar Converter<br/>Gregorian -> Jalali (YYYY/MM/DD)"]
        IHO -->|"2. City Mapping"| CityMap["City Slug Resolver<br/>(Tehran, Mashhad, Kish, etc.)"]
        IHO -->|"3. Search Request"| SearchAPI["IHO Search API<br/>/v1/search/filter"]
        IHO -->|"4. Detailed Rates (Optional)"| RoomsAPI["IHO Rooms API<br/>POST /v1/hotelInfo/hotelRooms"]
    end

    SearchAPI -->|"Live Hotel Results"| IHO
    IHO -->|"Transform to HotelResult"| Orchestrator
    Orchestrator -->|"Cached Providers Only (Caller TTL)<br/>*Iran Hotel Excluded*"| Redis
    Orchestrator -->|"Unified Merged Response"| Client
```

> [!IMPORTANT]
> **No-Cache Policy for Iran Hotel**: To guarantee 100% real-time room availability and volatile pricing, **Iran Hotel results are NEVER stored in or retrieved from the cache**. In multi-provider searches (e.g. Accommodations with Jajiga & Iran Hotel, or Hotels with Alibaba & Iran Hotel), cacheable providers are cached using the caller-defined TTL (`cache_ttl` or `cache_time`), while Iran Hotel is always fetched live.

---

## 🎛️ 3. Supported Endpoints

### 1. Hotel Search & Filtering (`GET /api/v1/hotels/search`)
Query parameters supported:
* `city` (string, required): e.g. `Tehran`, `تهران`, `mashhad`, `kish`, `shiraz`, `isfahan`
* `checkin_date` (string, required): Gregorian (`2026-10-07`) or Jalali (`1405-07-15`)
* `checkout_date` (string, required): Gregorian (`2026-10-08`) or Jalali (`1405-07-16`)
* `rooms` (integer, default: 1): Number of rooms
* `adults` (integer, default: 2): Total adult guests
* `stars` (integer, optional): Star rating filter (`1` to `5`)
* `min_price` / `max_price` (integer, optional): Nightly price boundaries in IRR
* `sort_by` (string, optional): `price_asc`, `price_desc`, `rate`, `popular`
* `page` (integer, default: 1): Page number
* `providers` (string, optional): Target provider (e.g. `iranhotel`, `alibaba`, `flytoday`)

### 2. Real-Time Room Inventory & Rates (`GET /api/v1/hotels/rooms`)
Direct room-level availability, bed capacities, meal plans, and discounted rates.
* `hotel_id` (integer, required): e.g. `149` (Parsian Azadi), `465` (Toranj Kish), `25` (Esteghlal)
* `checkin_date` (string, required)
* `checkout_date` (string, required)
* `provider` (string, default: `iranhotel`)

### 3. Provinces Hierarchy (`GET /api/v1/hotels/provinces`)
Returns all **40 provinces** with real-time hotel counts directly from IranHotelOnline's metadata tree.

### 4. Cities by Province (`GET /api/v1/hotels/cities`)
Returns **320 cities**, optionally filtered by parent `province_id` (e.g. `8` for Tehran, `11` for Khorasan Razavi, `4` for Isfahan).

---

## 🧪 4. Example API Requests

### 1. Search 5-Star Hotels in Kish Island
```bash
curl -X GET "http://localhost:8000/api/v1/hotels/search?city=kish&checkin_date=2026-10-07&checkout_date=2026-10-08&stars=5&providers=iranhotel" \
  -H "X-API-Key: YOUR_API_KEY"
```

### 2. Check Room Inventory & Prices for Parsian Azadi (Hotel ID: 149)
```bash
curl -X GET "http://localhost:8000/api/v1/hotels/rooms?hotel_id=149&checkin_date=2026-10-07&checkout_date=2026-10-08&provider=iranhotel" \
  -H "X-API-Key: YOUR_API_KEY"
```

### 3. Fetch Cities in Tehran Province (Province ID: 8)
```bash
curl -X GET "http://localhost:8000/api/v1/hotels/cities?provider=iranhotel&province_id=8" \
  -H "X-API-Key: YOUR_API_KEY"
```
