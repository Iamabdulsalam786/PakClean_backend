# Pak Clean API

FastAPI backend for the Pak Clean on-demand home services app.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
# Start PostgreSQL locally, then:
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Health: http://127.0.0.1:8000/health
- Docs: http://127.0.0.1:8000/docs

## Auth

- `POST /api/v1/auth/register` — email/password
- `POST /api/v1/auth/login` — email/password
- `POST /api/v1/auth/otp/request` — email OTP (dev: `dev_code` when `DEBUG=true`)
- `POST /api/v1/auth/otp/verify` — verify OTP → JWT
- `GET /api/v1/auth/me` — current user (Bearer token)

## Deploy (Render)

See `render.yaml`. Connect this repo as a Blueprint, or set the Web Service root to this project and run:

- Build: `pip install -r requirements.txt`
- Pre-deploy: `alembic upgrade head`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
