# Safarchin Travel Crawler API (FastAPI)

An extensible, asynchronous online crawler engine aggregating real-time travel and hospitality data across **Safarchin.ir**, **Alibaba.ir**, **FlyToday.ir**, **Karnaval.ir**, **Jajiga.com**, and **IranHotelOnline.com**.

> 📖 **Guides**: 
> - **Server Deployment & Production Setup**: [DEPLOYMENT.md](DEPLOYMENT.md)
> - **Safarchin.ir Integration & Route Guide**: [docs/SAFARCHIN_PROVIDER.md](docs/SAFARCHIN_PROVIDER.md)
> - **Jajiga Integration & Filter Guide**: [docs/JAJIGA_PROVIDER.md](docs/JAJIGA_PROVIDER.md)
> - **IranHotelOnline Integration Guide**: [docs/IRANHOTEL_PROVIDER.md](docs/IRANHOTEL_PROVIDER.md)

---

## 🚀 Key Features

- **Extensible Architecture**: Built with the **Adapter + Registry Pattern**. Adding a new website crawler takes just one isolated class without modifying existing endpoints or routers.
- **Configurable Port via `.env`**: App port is configurable via `PORT` in `.env` (maps dynamically through Docker Compose, Dockerfile, and FastAPI).
- **TDD (Test-Driven Development)**: Comprehensive test suite covering domain schemas, calendar converters, API key security, rate limiting, provider adapters, and the orchestrator (40+ automated unit & integration tests).
- **Anti-Bot Resilience**: Leverages `curl_cffi` to match browser TLS fingerprints (JA3/JA4) and Chrome headers to prevent anti-bot blocking from target portals.
- **Smart Concurrency & Caching**: Multi-provider queries execute in parallel using `asyncio.gather` with timeout protection and Redis result caching (configurable TTL).
- **Security & Rate Limiting**: Salted SHA-256 hashed `X-API-Key` authentication with Redis-backed sliding-window rate limiting.
- **Management CLI (`app/cli.py`)**: Built-in administration tool to manage API keys, monitor crawler health, flush cache, and initialize the database.

---

## 🛠 Docker Setup (Using Cached Local Images)

The project is pinned to images available on your system:
- **Python**: `python:3.11-slim`
- **PostgreSQL**: `postgres:16`
- **Redis**: `redis:7-alpine`

### Starting the Stack
```bash
# 1. Copy environment template (and optionally configure PORT=8000)
cp .env.example .env

# 2. Start all services
docker compose up -d
```

Services will be accessible at:
- **API Server & Swagger UI**: `http://localhost:${PORT:-8000}/docs`
- **PostgreSQL**: `localhost:5432`
- **Redis**: `localhost:6379`

---

## 🧪 Running Tests (TDD)

All tests run inside the containerized test environment without polluting your host:

```bash
# Run full test suite
docker compose run --rm web pytest -v

# Run with test coverage
docker compose run --rm web pytest --cov=app tests/
```

---

## 💻 Project Management CLI (`app/cli.py`)

Manage the platform using the CLI directly through Docker:

### 1. Database Initialization
```bash
docker compose run --rm web python -m app.cli db init
```

### 2. API Key Management
```bash
# Create a new API key
docker compose run --rm web python -m app.cli apikey create --name "Frontend App" --tier pro --rate-limit 120 --quota 10000

# List all keys
docker compose run --rm web python -m app.cli apikey list

# Revoke a key
docker compose run --rm web python -m app.cli apikey revoke <key_id_prefix>
```

### 3. Crawler Status & Health
```bash
docker compose run --rm web python -m app.cli crawlers status
```

### 4. Cache Management
```bash
# Inspect Redis cache stats
docker compose run --rm web python -m app.cli cache stats

# Flush search cache
docker compose run --rm web python -m app.cli cache flush
```

### 5. Multi-Token Pool & Provider Credentials (`app/cli.py`)
```bash
# Add token to provider pool (enables 429 auto-failover)
docker compose run --rm web python -m app.cli providers token add --provider jajiga --token "Bearer eyJ..." --expires-at "2027-10-01T00:00:00Z"

# List active provider token pools & cooldown statuses
docker compose run --rm web python -m app.cli providers token list

# Inspect active token for a provider
docker compose run --rm web python -m app.cli providers token get --provider jajiga

# Manually advance/rotate to next token in pool
docker compose run --rm web python -m app.cli providers token rotate --provider jajiga

# Inspect all providers and authentication statuses
docker compose run --rm web python -m app.cli providers status

# Remove a specific token from the pool
docker compose run --rm web python -m app.cli providers token remove --provider jajiga --token-id tok_2

# Revoke all tokens for a provider
docker compose run --rm web python -m app.cli providers token revoke --provider jajiga
```

---

## 🌐 API Endpoints Reference

All search requests require the `X-API-Key` header.

### 1. Flights
`GET /api/v1/flights/search`
- **Query Params**: `origin` (e.g. `THR`), `destination` (e.g. `MHD`), `depart_date` (e.g. `2026-10-15` or `1405-07-24`), `adults`, `providers` (optional: `alibaba,flytoday`).

### 2. Hotels
`GET /api/v1/hotels/search`
- **Query Params**: `city` (e.g. `Kish`), `checkin_date`, `checkout_date`, `rooms`, `adults`, `providers`.

### 3. Accommodations & Villas (Jajiga)
- **Search**: `GET /api/v1/accommodations/search`
  - Returns structured `pagination` (`current_page`, `per_page`, `total_count`, `total_pages`, `has_next_page`, `has_prev_page`) and `results`.
  - **Query Params**:
    - `city` (required): Destination city or region name in Persian or English (e.g. `سوادکوه`, `Savadkuh`, `رامسر`, `Ramsar`, `کیش`, `تهران`).
    - `checkin_date` (required): Check-in date in Gregorian `YYYY-MM-DD` or Jalali `1405-07-24`.
    - `checkout_date` (required): Check-out date in Gregorian `YYYY-MM-DD` or Jalali `1405-07-26`.
    - `guests` (optional, default `2`): Minimum guest capacity required.
    - `property_type` (optional): Filter: `villa`, `cottage`, `wooden_cottage`, `swiss_cottage`, `apartment`, `suite`, `ruralhome`, `ecolog`, `apartmenthotel`, `motel`.
    - `min_price` (optional): Minimum price per night in Tomans (IRT).
    - `max_price` (optional): Maximum price per night in Tomans (IRT).
    - `amenities` (optional): Comma-separated: `pool`, `pool-indoor`, `pool-outdoor`, `pool-hot`, `jacuzzi`, `sauna`, `billiard`, `foosball`, `parking`, `heating`, `cooler`, `wifi`, `elevator`, `furniture`.
    - `sort_by` (optional, default `popularity`): `popularity`, `low_price`, `high_price`, `rating`, `newest`, `books`, `discount`.
    - `page` (optional, default `1`): Pagination page number.
    - `providers` (optional, default `jajiga`): Comma-separated providers (e.g. `jajiga`).
- **Provinces Listing**: `GET /api/v1/accommodations/provinces?provider=jajiga`
  - Returns all 39 provinces sorted by room count.
- **Cities Listing**: `GET /api/v1/accommodations/cities?provider=jajiga&province_id=p26`
  - Returns cities/districts (optionally filtered by parent province ID, e.g. `p24` for Gilan, `p26` for Mazandaran).

### 4. Ground Transport (Buses & Trains)
- Intercity Buses: `GET /api/v1/transport/buses?origin=Tehran&destination=Isfahan&depart_date=2026-10-15`
- Passenger Trains: `GET /api/v1/transport/trains?origin=Tehran&destination=Mashhad&depart_date=2026-10-15`

### 5. System & Discovery
- `GET /api/v1/providers`: Lists all active providers and supported services.
- `GET /api/v1/health`: Service health status.

---

## 🧩 How to Add a New Crawler Later

To add a new platform (e.g., `snapptrip` or `safarmarket`), create a single file in `app/crawlers/<provider_name>/crawler.py`:

```python
from app.crawlers.base import BaseCrawler
from app.crawlers.registry import register_crawler
from app.schemas.flight import FlightSearchQuery, FlightResult

@register_crawler(name="snapptrip", services={"flight", "hotel"})
class SnappTripCrawler(BaseCrawler):
    provider_name = "snapptrip"
    supported_services = {"flight", "hotel"}

    async def search_flights(self, query: FlightSearchQuery) -> list[FlightResult]:
        # Implement provider API call & parse to FlightResult
        ...
```

The crawler will be **automatically discovered**, registered in the CLI, and included in multi-provider parallel searches without touching router or orchestrator code!
