# Store Locator API

A production-ready store locator REST API built with **FastAPI** and **PostgreSQL**. Supports public store search by location, role-based store management, JWT authentication, batch CSV import, Redis caching, and rate limiting.

## Tech Stack

| Layer | Choice |
|---|---|
| Framework | FastAPI 0.115 + Uvicorn/Gunicorn |
| Database | PostgreSQL 16 + SQLAlchemy 2 + Alembic |
| Cache | Redis 7 (geocoding TTL 30 d, search TTL 5 min) |
| Auth | JWT — access token (15 min) + refresh token (7 d) |
| Geocoding | Nominatim (OpenStreetMap) via `geopy` |
| CSV processing | Python built-in `csv` module |
| Distance | Bounding box pre-filter + Haversine (`geopy.distance.geodesic`) |
| Rate limiting | `slowapi` — 100 req/hr / 10 req/min per IP (public search) |
| Deployment | Render (Docker, free tier) |

---

## Project Structure

```
store-locator/
├── app/
│   ├── core/          # cache, dependencies, permissions, rate limiter, security
│   ├── models/        # SQLAlchemy ORM models (store, user, role, token)
│   ├── routers/       # FastAPI routers (auth, search, admin_stores, admin_users)
│   ├── schemas/       # Pydantic schemas
│   ├── services/      # Business logic (auth, store, csv, geo)
│   ├── utils/         # Distance + hours helpers
│   ├── config.py
│   ├── database.py
│   └── main.py
├── alembic/           # Database migrations
├── data/              # stores_50.csv + stores_1000.csv
├── seeds/             # Seed scripts (roles, users, stores)
├── tests/
│   ├── api/           # API endpoint tests
│   ├── integration/   # End-to-end flow tests
│   └── unit/          # Distance, hours, password, CSV validation
├── docker-compose.yml
├── Dockerfile
├── render.yaml
└── requirements.txt
```

---

## Local Setup

### Prerequisites

- Python 3.10+
- PostgreSQL 16
- Redis 7
- (or Docker — see below)

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd store-locator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` — the required fields:

```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/store_locator
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">
NOMINATIM_USER_AGENT=store-locator/1.0 (your-email@example.com)
```

### 3. Run migrations

```bash
alembic upgrade head
```

### 4. Seed database

```bash
python -m seeds.seed_roles
python -m seeds.seed_users
python -m seeds.seed_stores    # loads stores_50.csv (50 stores)
```

To load the full 1 000-store dataset use the CSV import endpoint instead (see below).

### 5. Start the server

```bash
uvicorn app.main:app --reload
```

API available at `http://localhost:8000`  
Swagger UI at `http://localhost:8000/docs`

---

## Docker (all-in-one)

```bash
docker compose up --build
```

This starts PostgreSQL, Redis, and the API together. Then run seeds inside the container:

```bash
docker compose exec api alembic upgrade head
docker compose exec api python -m seeds.seed_roles
docker compose exec api python -m seeds.seed_users
```

---

## Running Tests

```bash
pytest                               # all tests
pytest tests/unit/                   # unit tests only
pytest tests/api/                    # API tests only
pytest tests/integration/            # integration tests only
pytest --cov=app --cov-report=html   # coverage report → htmlcov/index.html
```

Test configuration is in `pytest.ini`. Tests use an in-memory SQLite database via the fixtures in `tests/conftest.py`. External geocoding calls are mocked.

---

## API Endpoints

### Health

| Method | Path | Description |
|---|---|---|
| GET | `/health` | DB + cache connectivity check |

### Auth

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/login` | Email/password → access + refresh tokens |
| POST | `/api/auth/refresh` | Refresh token → new access token |
| POST | `/api/auth/logout` | Revoke refresh token |

### Public Store Search

| Method | Path | Auth | Rate limit |
|---|---|---|---|
| POST | `/api/stores/search` | None | 100/hr, 10/min per IP |

Search request body:

```json
{
  "latitude": 42.36,
  "longitude": -71.06,
  "radius_miles": 10,
  "services": ["pharmacy"],
  "store_types": ["flagship", "regular"],
  "open_now": false
}
```

Alternatively, search by address or postal code:

```json
{ "address": "100 Cambridge St, Boston, MA" }
{ "postal_code": "02114" }
```

### Admin — Store Management (authenticated)

| Method | Path | Required permission |
|---|---|---|
| POST | `/api/admin/stores` | `store:create` |
| GET | `/api/admin/stores` | `store:read` |
| GET | `/api/admin/stores/{store_id}` | `store:read` |
| PATCH | `/api/admin/stores/{store_id}` | `store:update` |
| DELETE | `/api/admin/stores/{store_id}` | `store:delete` (soft delete) |
| POST | `/api/admin/stores/import` | `store:import` (CSV upload) |

PATCH accepts only: `name`, `phone`, `services`, `status`, `hours_*`.  
DELETE sets `status = inactive` — records are never physically removed.

### Admin — User Management (Admin only)

| Method | Path | Required permission |
|---|---|---|
| POST | `/api/admin/users` | `user:manage` |
| GET | `/api/admin/users` | `user:manage` |
| PUT | `/api/admin/users/{user_id}` | `user:manage` |
| DELETE | `/api/admin/users/{user_id}` | `user:manage` |

---

## Authentication Flow

1. `POST /api/auth/login` — returns `access_token` (15 min) and `refresh_token` (7 days).
2. Send `Authorization: Bearer <access_token>` on protected requests.
3. When the access token expires, call `POST /api/auth/refresh` with the refresh token.
4. On sign-out, call `POST /api/auth/logout` — the refresh token is revoked in the database.

The JWT payload includes `user_id`, `email`, and `role`. Refresh tokens are stored (hashed) in the `refresh_tokens` table so they can be individually revoked.

---

## Role-Based Access Control

| Permission | Admin | Marketer | Viewer |
|---|:---:|:---:|:---:|
| `store:read` | ✓ | ✓ | ✓ |
| `store:create` | ✓ | ✓ | |
| `store:update` | ✓ | ✓ | |
| `store:delete` | ✓ | ✓ | |
| `store:import` | ✓ | ✓ | |
| `user:manage` | ✓ | | |

---

## Distance Calculation

Search uses a two-step approach to avoid full-table scans:

1. **Bounding box (SQL)** — a latitude/longitude rectangle is computed around the search point and applied as a `WHERE` clause, leveraging the composite `(latitude, longitude)` index.

```python
latitude_delta  = radius_miles / 69.0
longitude_delta = radius_miles / (69.0 * cos(radians(lat)))
```

2. **Haversine (Python)** — exact geodesic distances are computed for the pre-filtered rows using `geopy.distance.geodesic`, and results are sorted nearest-first.

---

## CSV Import

`POST /api/admin/stores/import` — upload a `.csv` file.

**Upsert logic:** if `store_id` already exists the row is updated; otherwise a new store is created. The entire import runs in a single database transaction (all-or-nothing).

Required CSV columns (exact order):

```
store_id,name,store_type,status,latitude,longitude,
address_street,address_city,address_state,address_postal_code,address_country,
phone,services,hours_mon,hours_tue,hours_wed,hours_thu,hours_fri,hours_sat,hours_sun
```

Response includes `created`, `updated`, and `failed` counts with per-row error details.

---

## Database Schema

Core tables: `stores`, `users`, `roles`, `permissions`, `role_permissions`, `refresh_tokens`.

Indexes: `(latitude, longitude)` composite, `status` partial (active stores), `store_type`, `address_postal_code`, `users.email`, `refresh_tokens.token_hash`.

Run `alembic history` to inspect migration versions.

---

## Test Credentials

| Role | Email | Password |
|---|---|---|
| Admin | `admin@test.com` | `AdminTest123!` |
| Marketer | `marketer@test.com` | `MarketerTest123!` |
| Viewer | `viewer@test.com` | `ViewerTest123!` |

---

## Deployment (Render)

The `render.yaml` defines three Render services: a Docker web service, a Redis instance, and a managed PostgreSQL database. Deploy by connecting the repository to Render — it picks up the blueprint automatically.

Post-deploy, run migrations and seeds via the Render shell:

```bash
alembic upgrade head
python -m seeds.seed_roles
python -m seeds.seed_users
```

Then import the full dataset through the `/api/admin/stores/import` endpoint using `data/stores_1000.csv`.

Health check endpoint: `GET /health`
