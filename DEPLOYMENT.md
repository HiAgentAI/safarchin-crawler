# Server Deployment & Production Setup Guide

This guide walks you through deploying the **Safarchin Travel Crawler API** on a remote server from scratch using Docker Compose. It covers configuring custom application ports, database initialization, generating your first API key, and configuring token-authenticated providers (like Jajiga) with multi-token automatic rotation.

---

## 📋 Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Step 1: Clone the Repository](#2-step-1-clone-the-repository)
3. [Step 2: Configure Environment & Custom Application Port](#3-step-2-configure-environment--custom-application-port)
4. [Step 3: Start the Docker Services](#4-step-3-start-the-docker-services)
5. [Step 4: Initialize the Database Schema](#5-step-4-initialize-the-database-schema)
6. [Step 5: Create Your First API Key](#6-step-5-create-your-first-api-key)
7. [Step 6: Configure Providers That Require Tokens (Jajiga)](#7-step-6-configure-providers-that-require-tokens-jajiga)
8. [Step 7: Verify & Test API Endpoints](#8-step-7-verify--test-api-endpoints)
9. [Step 8: Production Best Practices & Maintenance](#9-step-8-production-best-practices--maintenance)

---

## 1. System Requirements

Ensure the server meets the following prerequisites:
- **Operating System**: Linux (Ubuntu 20.04/22.04/24.04, Debian 11/12, or AlmaLinux/RockyLinux)
- **Memory**: Minimum 2 GB RAM (4 GB recommended)
- **Disk Space**: At least 10 GB free
- **Installed Tools**:
  - Docker engine (`>= 24.0`)
  - Docker Compose plugin (`docker compose` v2)
  - `git`, `curl`

To verify Docker installation:
```bash
docker --version
docker compose version
```

---

## 2. Step 1: Clone the Repository

Clone the repository onto your server via SSH:

```bash
git clone git@github.com:HiAgentAI/safarchin-crawler.git
cd safarchin-crawler
```

---

## 3. Step 2: Configure Environment & Custom Application Port

Create your server `.env` file by copying `.env.example`:

```bash
cp .env.example .env
```

Open `.env` in your editor (`nano .env` or `vim .env`) and review the parameters:

```ini
# ==========================================
# Server & Application Configuration
# ==========================================
ENVIRONMENT=production
DEBUG=false

# APP PORT: Change this to whatever port you want the API to listen on!
# Examples: 8000, 8080, 5000, 3000
PORT=8000
HOST=0.0.0.0

# ==========================================
# Database Configuration (PostgreSQL)
# ==========================================
POSTGRES_USER=safarchin
POSTGRES_PASSWORD=generate_a_secure_postgres_password_here
POSTGRES_DB=safarchin_crawler
POSTGRES_PORT=5432

# ==========================================
# Security & Salt
# ==========================================
# Generate using: openssl rand -hex 32
SECRET_KEY=generate_a_random_64_character_hex_string_here
API_KEY_PREFIX=sc_
DEFAULT_RATE_LIMIT_PER_MINUTE=60
DEFAULT_DAILY_QUOTA=1000

# ==========================================
# Crawler Settings
# ==========================================
CRAWLER_DEFAULT_TIMEOUT=15.0
CRAWLER_MAX_CONCURRENCY=5
USER_AGENT_MODE=desktop

# Optional static provider token (can also be managed via CLI token pool)
JAJIGA_TOKEN=
```

### ⚙️ How the Port Configuration Works
- Both `Dockerfile` and `docker-compose.yml` dynamically reference `${PORT:-8000}`.
- If you set `PORT=8080` in `.env`, the Docker container will expose and bind to port `8080` automatically on the host (`0.0.0.0:8080`). No code or compose edits are required.

---

## 4. Step 3: Start the Docker Services

Build the application image and run all services (PostgreSQL 16, Redis 7, and FastAPI Web) in detached background mode:

```bash
docker compose up -d --build
```

### Inspect Container Status
Check that all three containers are healthy and running:

```bash
docker compose ps
```

You should see:
- `safarchin_postgres`: Up (healthy)
- `safarchin_redis`: Up (healthy)
- `safarchin_api`: Up (`0.0.0.0:<PORT>-><PORT>/tcp`)

### View Web Server Logs
Verify that Uvicorn started on your configured port:

```bash
docker compose logs -f web
```

### Test Service Health
Replace `<PORT>` with your configured port (e.g. `8000`):

```bash
curl http://localhost:8000/api/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "environment": "production",
  "database": "connected",
  "redis": "connected",
  "registered_crawlers": ["alibaba", "flytoday", "iranhotel", "jajiga", "safarchin"]
}
```

---

## 5. Step 4: Initialize the Database Schema

Before creating API keys or executing queries, initialize the PostgreSQL tables (`api_keys`, `search_logs`, `crawler_health`):

```bash
docker compose exec web python -m app.cli db init
```

Expected output:
```text
Initializing database schema...
✓ Database tables initialized successfully!
```

---

## 6. Step 5: Create Your First API Key

All search endpoints require authentication via the `X-API-Key` HTTP header. API keys are hashed with salted SHA-256 before storage in PostgreSQL and cached in Redis for high-speed authentication.

### Generate the First Key
Run the CLI `apikey create` command through Docker Compose:

```bash
docker compose exec web python -m app.cli apikey create \
  --name "Production Client" \
  --tier enterprise \
  --rate-limit 120 \
  --quota 50000
```

#### CLI Parameters:
- `--name`, `-n`: Client or application name.
- `--tier`, `-t`: Tier level (`standard`, `pro`, `enterprise`, `internal`).
- `--rate-limit`, `-r`: Max requests allowed per minute (sliding-window rate limit).
- `--quota`, `-q`: Daily search query quota.

#### Example Output:
```text
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ New API Key Created                                                    ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Client Name: Production Client                                         │
│ Key ID: 3a9f02b1-e251-4e76-88bc-4672e81190bc                           │
│ Tier: enterprise                                                       │
│ Rate Limit: 120 req/min                                                │
│ Daily Quota: 50000                                                     │
│                                                                        │
│ Secret Key (save this now, it won't be shown again):                   │
│  sc_live_f89c092a8b321...                                              │
└────────────────────────────────────────────────────────────────────────┘
```

> [!IMPORTANT]
> Copy and save the plain secret key (`sc_...`) immediately in your secrets manager. Only the cryptographic hash is stored in the database.

### List Active API Keys
```bash
docker compose exec web python -m app.cli apikey list
```

### Revoking an API Key
If a key is compromised, revoke it immediately by ID or ID prefix:
```bash
docker compose exec web python -m app.cli apikey revoke 3a9f02b1
```
This updates the database and immediately purges the key from the Redis authentication cache.

### Test Authentication With Your New Key
```bash
curl -H "X-API-Key: sc_your_generated_secret_key" http://localhost:8000/api/v1/providers
```

---

## 7. Step 6: Configure Providers That Require Tokens (Jajiga)

### Provider Authentication Models Overview

| Provider | Category | Auth Method | Requires Token? |
|---|---|---|---|
| **Safarchin** | Charter Flights, Trains | Direct / TLS Fingerprint | ❌ No (Public) |
| **Alibaba** | Domestic Flights, Buses, Trains | Direct / Reverse Proxy API | ❌ No (Public) |
| **FlyToday** | Flights, Hotels | Direct API / TLS Impersonation | ❌ No (Public) |
| **IranHotelOnline** | Hotels, Traditional Stays | Direct Search Endpoint | ❌ No (Public) |
| **Jajiga** | Villas, Cottages, Accommodations | Bearer JWT Token | ✅ **Yes** |

### How to Obtain a Jajiga Token
1. Open your browser and navigate to `https://www.jajiga.com`.
2. Open Developer Tools (`F12` or `Inspect`) and switch to the **Network** tab.
3. Perform any search or browse villas.
4. Filter requests for `api` or `search`.
5. Look under **Request Headers** for:
   ```http
   Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGci...
   ```
6. Copy the token string (with or without the leading `Bearer `).

---

### Managing Provider Tokens via CLI (Recommended)

The platform includes a **Multi-Token Pool with Automatic 429 Failover**:
- If Jajiga returns `HTTP 429 Too Many Requests`, the active token is placed on a **5-minute cooldown**, and the crawler automatically switches to the next available standby token in the pool with zero downtime.

#### 1. Set the Primary Token
```bash
docker compose exec web python -m app.cli providers token set \
  --provider jajiga \
  --token "Bearer eyJ0eXAiOiJKV1Qi..." \
  --expires-at "2027-10-01T00:00:00Z"
```

#### 2. Add Secondary/Failover Tokens to the Pool
```bash
docker compose exec web python -m app.cli providers token add \
  --provider jajiga \
  --token "Bearer eyJhbGciOi..." \
  --expires-at "2027-10-01T00:00:00Z"
```

#### 3. Inspect Configured Tokens & Cooldown Health
```bash
docker compose exec web python -m app.cli providers token list
```

Example status table:
```text
┏━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┓
┃ Provider ┃ Token ID ┃ Status           ┃ Expires At          ┃ Token Preview      ┃
┡━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━┩
│ jajiga   │ tok_1    │ ACTIVE (IN-USE)  │ 2027-10-01T00:00:00 │ eyJ0eXAi...S8Syad │
│          │ tok_2    │ STANDBY          │ 2027-10-01T00:00:00 │ eyJhbGci...49pLw  │
└──────────┴──────────┴──────────────────┴─────────────────────┴────────────────────┘
```

#### 4. Check Provider Overall Status
```bash
docker compose exec web python -m app.cli providers status
```

#### 5. Manually Rotate or Remove Tokens
- Advance to next token: `docker compose exec web python -m app.cli providers token rotate --provider jajiga`
- Remove a specific token: `docker compose exec web python -m app.cli providers token remove --provider jajiga --token tok_2`
- Revoke all tokens: `docker compose exec web python -m app.cli providers token revoke --provider jajiga`

---

### Alternative: Setting Token via `.env`
If you prefer not using the CLI token pool, you can specify a single token directly in your `.env` file:

```ini
JAJIGA_TOKEN=Bearer eyJ0eXAiOiJKV1QiLCJhbGci...
```

Then restart the web container:
```bash
docker compose restart web
```

---

## 8. Step 7: Verify & Test API Endpoints

Replace `<PORT>` with your configured port and `<API_KEY>` with your `sc_...` key.

### 1. Flights Search (Safarchin, FlyToday, Alibaba)
```bash
curl -s -H "X-API-Key: <API_KEY>" \
  "http://localhost:8000/api/v1/flights/search?origin=THR&destination=MHD&depart_date=2026-10-15&adults=1" | jq .
```

### 2. Accommodations & Villas (Jajiga)
```bash
curl -s -H "X-API-Key: <API_KEY>" \
  "http://localhost:8000/api/v1/accommodations/search?city=سوادکوه&checkin_date=2026-10-15&checkout_date=2026-10-17&guests=2" | jq .
```

### 3. Hotels Search (IranHotelOnline, FlyToday)
```bash
curl -s -H "X-API-Key: <API_KEY>" \
  "http://localhost:8000/api/v1/hotels/search?city=Kish&checkin_date=2026-10-15&checkout_date=2026-10-18&rooms=1&adults=2" | jq .
```

### 4. Ground Transport (Intercity Buses)
```bash
curl -s -H "X-API-Key: <API_KEY>" \
  "http://localhost:8000/api/v1/transport/buses?origin=Tehran&destination=Isfahan&depart_date=2026-10-15" | jq .
```

---

## 9. Step 8: Production Best Practices & Maintenance

### A. Nginx Reverse Proxy Setup (HTTP + HTTPS SSL)

A production-tuned Nginx configuration file is provided in [`nginx/safarchin-crawler.conf`](nginx/safarchin-crawler.conf).

#### 1. Copy the configuration to Nginx:
```bash
sudo cp nginx/safarchin-crawler.conf /etc/nginx/sites-available/safarchin-crawler.conf
sudo ln -s /etc/nginx/sites-available/safarchin-crawler.conf /etc/nginx/sites-enabled/
```

#### 2. Edit domain and port:
Open `/etc/nginx/sites-available/safarchin-crawler.conf` and adjust:
- `server 127.0.0.1:8000;` (change `8000` to your `.env` `PORT` if modified)
- `server_name api.yourdomain.com;` (replace with your domain or server IP)

#### 3. Obtain free SSL certificates with Certbot:
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d api.yourdomain.com
```

#### 4. Test configuration and reload Nginx:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### B. Redis Cache Management
Inspect cache memory and key count:
```bash
docker compose exec web python -m app.cli cache stats
```

Purge all cached search results when provider formats change:
```bash
docker compose exec web python -m app.cli cache flush
```

### C. Viewing Live Logs
```bash
# Follow all container logs
docker compose logs -f

# Follow only the API web service
docker compose logs -f web
```

### D. Systemd Auto-Restart on Host Boot (Optional)
Create `/etc/systemd/system/safarchin-crawler.service`:

```ini
[Unit]
Description=Safarchin Crawler Docker Stack
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/safarchin-crawler
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable safarchin-crawler
```

---

## 🛠 Troubleshooting Quick Reference

| Issue | Cause | Solution |
|---|---|---|
| `Port already in use` | Another service uses `PORT` | Change `PORT` in `.env` (e.g. `PORT=8080`) and rerun `docker compose up -d` |
| `401 Unauthorized` | Missing/invalid `X-API-Key` | Create key via `python -m app.cli apikey create` and pass `X-API-Key: sc_...` header |
| `429 Rate Limit Exceeded` | Key quota or per-minute rate hit | Increase `--rate-limit` / `--quota` or add backup tokens for Jajiga |
| `Database connection error` | PostgreSQL container still starting | Ensure healthy status via `docker compose ps` |
| `Jajiga returning empty` | Token expired or rate-limited | Update token via `python -m app.cli providers token set --provider jajiga --token ...` |
