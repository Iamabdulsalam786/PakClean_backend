# PakClean Backend (FastAPI)

Production-ready auth API for the PakClean React Native app.

## Stack

- **FastAPI** + Uvicorn
- **PostgreSQL** (async SQLAlchemy + asyncpg)
- **JWT** access + refresh tokens
- **Email OTP** (6 digits) for registration and password reset

## Quick start

```bash
cd Pakclean_backend

# 1. Environment
cp .env.example .env

# 2. Database
# Option A — local dev (SQLite, no Docker needed):
#   DATABASE_URL=sqlite+aiosqlite:///./dev.db
# Option B — PostgreSQL:
docker compose up -d
# Then set DATABASE_URL=postgresql+asyncpg://pakclean:pakclean@localhost:5432/pakclean

# 3. Python virtualenv (recommended)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Run API
uvicorn app.main:app --reload --port 8000
```

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

In development, OTP codes are printed to the console when SMTP is not configured.

## Auth endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Sign up (sends email OTP) |
| POST | `/api/v1/auth/verify-otp` | Verify registration or password-reset OTP |
| POST | `/api/v1/auth/resend-otp` | Resend OTP |
| POST | `/api/v1/auth/login` | Login (no OTP) |
| POST | `/api/v1/auth/forgot-password` | Send password-reset OTP |
| POST | `/api/v1/auth/reset-password` | Set new password |
| POST | `/api/v1/auth/refresh-token` | Refresh JWT |
| POST | `/api/v1/auth/logout` | Revoke refresh token |
| GET | `/api/v1/auth/me` | Current user (Bearer token) |

## Auth flows

**Register:** `register` → email OTP → `verify-otp` → JWT → customer: home / cleaner: agreement

**Login:** `login` → JWT (no OTP)

**Forgot password:** `forgot-password` → email OTP → `verify-otp` (purpose: password_reset) → `reset-password` → login

## Environment variables

See `.env.example`. Required secrets:

- `JWT_ACCESS_SECRET` — min 32 characters
- `JWT_REFRESH_SECRET` — min 32 characters
- `DATABASE_URL` — PostgreSQL async URL

## Deploy on Render

1. Push this repo (branch must contain `render.yaml` at the root).
2. Render Dashboard → **New** → **Blueprint**.
3. Connect the repo and select the branch (e.g. `development`).
4. Render creates **pakclean-api** (web) + **pakclean-db** (PostgreSQL).
5. After deploy, open `https://<your-service>.onrender.com/docs`.

Optional: add SMTP env vars in the Render dashboard for real OTP emails (`SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`).
