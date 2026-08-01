# Document 1: Authentication Requirements

**Project:** Pak Clean API  
**Status:** Phase 1 implemented (password + email OTP)  
**Base path:** `/api/v1`

---

## 1. User roles

| Role | Value | Who | Current support |
|------|--------|-----|-----------------|
| Customer | `customer` | End users booking services | Implemented (default on register / OTP) |
| Provider | `provider` | Service professionals | Role exists; profile/onboarding later |
| Admin | `admin` | Back-office operators | Role exists; admin APIs later |

**Rules**

- Public self-registration always creates `customer`.
- Clients **cannot** set `role` on register (privilege escalation prevention).
- Providers/admins are created by admin flows (planned) or seeded manually.
- Authorization uses `require_roles(...)` dependency (ready for admin routes).

---

## 2. Login methods

| Method | Endpoints | Notes |
|--------|-----------|--------|
| Email + password | `POST /auth/register`, `POST /auth/login`, `POST /auth/login/form` | Primary password path |
| Email OTP | `POST /auth/otp/request`, `POST /auth/otp/verify` | Passwordless; can create user on first verify |
| Bearer JWT | Header on protected routes | `Authorization: Bearer <access_token>` |
| Google / phone SMS / WhatsApp | — | **Not implemented** (future) |

**Swagger Authorize:** uses OAuth2 password flow against `/auth/login/form` (`username` = email).

---

## 3. Password policy

| Rule | Value |
|------|--------|
| Minimum length | 8 characters |
| Maximum length | 128 characters |
| Storage | bcrypt hash only (`hashed_password`) |
| Plain password | Never stored, never returned in API responses |
| OTP-only users | `hashed_password` may be `NULL` until they set a password |

---

## 4. Token strategy

| Item | Decision |
|------|----------|
| Type | JWT (HS256) |
| Claim `sub` | User UUID (string) |
| Claim `role` | Role string (e.g. `customer`) — convenience; DB is source of truth |
| Claim `iat` / `exp` | Issued-at / expiry |
| Access token lifetime | `ACCESS_TOKEN_EXPIRE_MINUTES` (default **30**) |
| Refresh tokens | Config exists (`REFRESH_TOKEN_EXPIRE_DAYS`); **not issued yet** |
| Secret | `SECRET_KEY` from environment |
| Invalid / expired token | HTTP **401** |
| Inactive user | HTTP **403** |

**Client usage**

```http
Authorization: Bearer <access_token>
```

---

## 5. Business rules

### Registration (password)

1. Email stored lowercased; must be unique.
2. Phone optional; if present, must be unique.
3. Password hashed with bcrypt before insert.
4. Role forced to `customer`.
5. Returns access token (user is logged in immediately).
6. Duplicate email/phone → **409 Conflict**.

### Login (password)

1. Lookup by lowercased email.
2. Same error message for unknown user and wrong password (`Invalid email or password`) → **401**.
3. Missing password hash (OTP-only account) → treat as invalid credentials.
4. Inactive user → **403**.

### Email OTP

1. Channel: **email only** (SMS/WhatsApp later).
2. Code: 6 digits, cryptographically random (`secrets`).
3. Store **hash** of code in `otp_challenges` (never plain OTP in DB).
4. Expiry: **300 seconds** (5 minutes).
5. Max verify attempts: **5** per challenge → then locked (**429**).
6. Resend cooldown: **60 seconds** (**429**).
7. Request always returns generic success message (anti-enumeration).
8. In `DEBUG=true`, response may include `dev_code`; production must not.
9. Delivery today: server log + optional `dev_code` (no real SMTP yet).
10. Verify success: consume challenge (`consumed_at` set).
11. If email has no user → create `customer` with `full_name` from email local-part, `hashed_password=NULL`.
12. Inactive user → **403** (OTP not consumed).

### Protected routes

1. Missing/invalid JWT → **401**.
2. Valid JWT but user deleted → **401**.
3. Valid JWT but `is_active=false` → **403**.
4. Role checks via `require_roles` → **403** if insufficient.

---

## 6. Interview talking points

- Domain errors (`AuthError`, `OtpError`) are mapped to HTTP in the route layer.
- OTP delivery is a provider concern; rules stay in the service layer.
- Fail closed on auth; fail generic on OTP request to avoid account enumeration.
