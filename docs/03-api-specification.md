# Document 3: API Specification

**Base URL (local):** `http://127.0.0.1:8000` or `:8001`  
**API prefix:** `/api/v1`  
**Content-Type:** `application/json` (except OAuth2 form login)

OpenAPI live docs (development only): `GET /docs`

---

## 1. System

### `GET /health`

**Auth:** None  

**Response `200`**

```json
{
  "status": "ok",
  "app": "Pak Clean API",
  "env": "development"
}
```

---

## 2. Auth endpoints

### `POST /api/v1/auth/register`

Register customer with email/password. Returns JWT.

**Auth:** None  

**Request**

```json
{
  "email": "user@example.com",
  "password": "12345678",
  "full_name": "Daniyal",
  "phone": "03424834128",
  "role": "customer"
}
```

| Field | Required | Rules |
|-------|----------|--------|
| `email` | yes | Valid email |
| `password` | yes | 8–128 chars |
| `full_name` | yes | 2–150 chars |
| `phone` | no | max 20 |
| `role` | no | `customer` (default) or `provider` — not `admin` |

**Response `201`**

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "role": "customer"
}
```

**Errors**

| Status | When |
|--------|------|
| `422` | Validation (e.g. short password) |
| `409` | Email or phone already taken |

---

### `POST /api/v1/auth/login`

JSON login for mobile/clients.

**Auth:** None  

**Request**

```json
{
  "email": "user@example.com",
  "password": "12345678"
}
```

**Response `200`**

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "role": "provider"
}
```

**Errors**

| Status | Body / when |
|--------|-------------|
| `401` | `{ "detail": "Invalid email or password" }` |
| `403` | Inactive user |
| `422` | Validation |

---

### `POST /api/v1/auth/login/form`

OAuth2 password form for Swagger Authorize.  
Form fields: `username` (email), `password`.

**Auth:** None  
**Content-Type:** `application/x-www-form-urlencoded`

**Response `200`:** same `Token` as JSON login.

---

### `POST /api/v1/auth/otp/request`

Request email OTP.

**Auth:** None  

**Request**

```json
{
  "email": "user@example.com"
}
```

**Response `200`**

```json
{
  "message": "If the email is valid, an OTP has been sent.",
  "expires_in_seconds": 300,
  "dev_code": "483920"
}
```

- `dev_code` only when `DEBUG=true`.
- Message is always generic (no “email not found”).

**Errors**

| Status | When |
|--------|------|
| `429` | Resend cooldown (&lt; 60s) |
| `422` | Invalid email format |

---

### `POST /api/v1/auth/otp/verify`

Verify OTP; create customer or provider if new; return JWT.

**Auth:** None  

**Request**

```json
{
  "email": "user@example.com",
  "code": "483920",
  "role": "provider"
}
```

| Field | Rules |
|-------|--------|
| `code` | Exactly 6 digits |
| `role` | Optional; `customer` (default) or `provider`; used **only** for new accounts |

**Response `200`**

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "role": "provider",
  "is_new_user": true
}
```

**Errors**

| Status | When |
|--------|------|
| `400` | Invalid / expired code |
| `429` | Too many attempts / locked |
| `403` | Inactive user |
| `422` | Validation |

---

### `GET /api/v1/auth/me`

Current authenticated user.

**Auth:** Bearer JWT required  

**Response `200`**

```json
{
  "id": "28ac78b7-ae89-48f8-bdef-53b52450708c",
  "email": "daniyalqais6@gmail.com",
  "phone": "03424834128",
  "full_name": "Daniyal",
  "role": "customer",
  "is_active": true,
  "created_at": "2026-08-01T11:18:43.847552-07:00",
  "updated_at": "2026-08-01T11:18:43.847552-07:00"
}
```

Never includes `hashed_password`.

**Errors**

| Status | When |
|--------|------|
| `401` | Missing/invalid/expired token |
| `403` | Inactive user |

---

## 3. Error response shape

FastAPI default:

```json
{
  "detail": "Human readable message"
}
```

Validation (`422`):

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "password"],
      "msg": "String should have at least 8 characters",
      "input": "1234567"
    }
  ]
}
```

---

## 4. Status code summary

| Code | Meaning in this API |
|------|---------------------|
| `200` | Success |
| `201` | Resource created (register) |
| `400` | Bad OTP |
| `401` | Unauthenticated / bad credentials |
| `403` | Authenticated but forbidden / inactive |
| `409` | Conflict (duplicate email/phone) |
| `422` | Request validation failed |
| `429` | Rate limit / OTP cooldown or lock |

---

## 5. Auth header

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```
