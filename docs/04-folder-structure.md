# Document 4: Folder Structure

**Root:** `pak-clean-backend/`  
**Style:** Layered modular monolith (FastAPI)

---

## 1. Tree (current)

```text
pak-clean-backend/
├── app/
│   ├── main.py                 # FastAPI app factory, CORS, /health, mount routers
│   ├── api/
│   │   └── v1/
│   │       ├── router.py       # Aggregates v1 routers
│   │       └── auth.py         # HTTP auth + OTP endpoints
│   ├── core/
│   │   ├── config.py           # Settings from env (.env / Render)
│   │   ├── security.py         # bcrypt + JWT
│   │   └── dependencies.py     # get_db, get_current_user, require_roles
│   ├── db/
│   │   ├── base.py             # SQLAlchemy DeclarativeBase
│   │   └── session.py          # Engine, SessionLocal, get_db()
│   ├── models/
│   │   ├── user.py             # User, UserRole
│   │   └── otp.py              # OtpChallenge
│   ├── schemas/
│   │   ├── auth.py             # Register/Login/Token/UserRead
│   │   └── otp.py              # OTP request/verify DTOs
│   └── services/
│       ├── auth_service.py     # Register/login business rules
│       └── otp_service.py      # OTP request/verify business rules
├── alembic/
│   ├── env.py                  # Migration runtime (uses Settings + Base.metadata)
│   ├── script.py.mako          # Revision template
│   └── versions/               # Migration scripts
├── docs/                       # Project documentation (this folder)
├── .env.example                # Safe env template (commit)
├── .gitignore
├── Procfile                    # Render/Heroku start command
├── render.yaml                 # Render Blueprint
├── docker-compose.yml          # Local Postgres (optional)
├── requirements.txt
├── alembic.ini
└── README.md
```

Not committed: `.env`, `.venv/`

---

## 2. Where every concern belongs

| Concern | Folder / file | Why |
|---------|----------------|-----|
| HTTP routes | `app/api/v1/*.py` | Thin: validate in → call service → return schema / HTTP error |
| Request/response JSON | `app/schemas/` | Public API contract; never leak password hashes |
| Business rules | `app/services/` | Testable without HTTP; domain errors (`AuthError`, `OtpError`) |
| DB tables | `app/models/` | ORM only; maps to Postgres |
| DB session / engine | `app/db/` | One connection strategy for the app |
| Config / JWT / deps | `app/core/` | Cross-cutting infrastructure |
| Schema evolution | `alembic/versions/` | Versioned DDL for every environment |
| Deploy | `Procfile`, `render.yaml` | How the process runs in the cloud |

---

## 3. Why each layer exists (interview)

### `api` (presentation)

- Speaks HTTP status codes and OpenAPI.
- Does **not** hash passwords or invent booking rules.

### `schemas` (DTO)

- Separates **API shape** from **DB shape**.
- Pydantic validates input early (`422`).

### `services` (domain / application)

- “Can this user register?” “Is OTP expired?”
- Raises domain errors; routes map them to HTTP.

### `models` + `db` (persistence)

- Tables and sessions.
- Alembic reads `Base.metadata` after models are imported.

### `core`

- Settings fail fast at startup.
- Security primitives reused by services and dependencies.
- `Depends()` injects auth/DB into every protected route.

---

## 4. Request flow example

```text
POST /api/v1/auth/otp/verify
        │
        ▼
 app/api/v1/auth.py          (route)
        │
        ▼
 app/schemas/otp.py          (validate body)
        │
        ▼
 app/services/otp_service.py (rules + DB writes)
        │
        ├── app/models/otp.py
        ├── app/models/user.py
        └── app/core/security.py (hash/JWT)
        │
        ▼
 JSON OtpVerifyResponse
```

Protected example:

```text
GET /api/v1/auth/me
  → dependencies.get_current_user (JWT + DB)
  → schemas.UserRead
```

---

## 5. Planned folders (not created yet)

| Path | Purpose |
|------|---------|
| `app/models/provider.py` | `ProviderProfile` |
| `app/api/v1/bookings.py` | Booking endpoints |
| `app/api/v1/admin/` | Admin-only routers |
| `app/integrations/email.py` | Resend/SendGrid OTP delivery |
| `tests/` | Pytest API + service tests |

---

## 6. Versioning

All feature routes hang under `/api/v1` via `settings.api_v1_prefix` so a future `/api/v2` can coexist without breaking React Native.
