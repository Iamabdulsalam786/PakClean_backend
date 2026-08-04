# Pak Clean API

FastAPI backend for the Pak Clean on-demand home services app.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env with your DATABASE_URL, SECRET_KEY, and Gmail SMTP App Password
# Start PostgreSQL locally, then:
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Health: http://127.0.0.1:8000/health
- Docs: http://127.0.0.1:8000/docs

**Never commit `.env`.** It contains secrets (DB password, JWT secret, Gmail App Password).  
Share secrets with teammates privately; commit only `.env.example`.

## Frontend integration (React Native)

Frontend developers do **not** need the backend `.env` file.  
They only need a **reachable API base URL** and the auth/booking contracts below.

If the frontend developer is remote (different city/country), `localhost` and LAN IPs will **not** work for them. Use one of:

1. **Deployed API** (best): Render/Railway/Fly — share the public HTTPS URL  
2. **Tunnel while you run locally**: [ngrok](https://ngrok.com) / Cloudflare Tunnel → share the public URL temporarily  

Never email/commit your `.env`. If they also run the backend themselves, they copy `.env.example` and you send SMTP/DB secrets through a private channel.

### Base URL

| Where API runs | Example base URL |
|----------------|------------------|
| Same PC as emulator (local only) | `http://127.0.0.1:8000` |
| Android emulator → host machine | `http://10.0.2.2:8000` |
| Physical phone on same Wi‑Fi | `http://<YOUR_PC_LAN_IP>:8000` |
| Remote teammate / production | `https://your-api.onrender.com` (or ngrok URL) |

Start the API so phones can reach it:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Interactive docs: `{BASE_URL}/docs`

### Auth flow (signup screen)

1. `POST /api/v1/auth/register`  
   Body: `full_name`, `email`, `phone`, `password`, `confirm_password`, `role` (`customer` \| `provider`)  
   → `201` (no JWT yet). Backend emails a 6-digit OTP.
2. User reads email → `POST /api/v1/auth/verify-otp`  
   Body: `{ "email", "code" }`  
   → `access_token` + `refresh_token`
3. Store tokens; send `Authorization: Bearer <access_token>` on protected routes.
4. Optional: `POST /api/v1/auth/resend-otp` (60s cooldown).
5. Later sessions: `POST /api/v1/auth/login` (blocked until email verified).
6. When access expires: `POST /api/v1/auth/refresh` with `{ "refresh_token" }`.
7. Profile: `GET /api/v1/auth/me`

### Other useful APIs

- Catalog (public): `GET /api/v1/catalog/categories`, `GET /api/v1/catalog/services`
- Customer bookings: `POST/GET /api/v1/bookings` (Bearer, customer role)
- Provider bookings: `/api/v1/bookings/provider/...`
- Admin: `/api/v1/bookings/admin/...` (admin token)

## Auth endpoints (summary)

- `POST /api/v1/auth/register` — create unverified user + send OTP email
- `POST /api/v1/auth/verify-otp` — verify email → JWT pair
- `POST /api/v1/auth/resend-otp` — new OTP email
- `POST /api/v1/auth/login` — password login (verified users only)
- `POST /api/v1/auth/refresh` — rotate tokens
- `GET /api/v1/auth/me` — current user

## Admin bootstrap

Create the first admin user (or promote an existing user to admin):

```powershell
python -m scripts.bootstrap_admin --email admin@example.com --password "StrongPass123" --full-name "Pak Clean Admin"
```

Then login via `POST /api/v1/auth/login` and use admin-only endpoints.

## Deploy (Render)

See `render.yaml`. Connect this repo as a Blueprint, or set the Web Service root to this project and run:

- Build: `pip install -r requirements.txt`
- Pre-deploy: `alembic upgrade head`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Set SMTP and DB env vars in the Render dashboard (not in git).
