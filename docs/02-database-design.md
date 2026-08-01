# Document 2: Database Design

**Project:** Pak Clean API  
**Engine:** PostgreSQL  
**ORM:** SQLAlchemy 2.x  
**Migrations:** Alembic  

Legend: **[Implemented]** vs **[Planned]**

---

## 1. Table: `users` **[Implemented]**

Identity for all roles (customer, provider, admin).

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|--------|
| `id` | `UUID` | NO | `uuid4` | Primary key |
| `email` | `VARCHAR(255)` | NO | — | Unique, indexed, stored lowercased in app |
| `phone` | `VARCHAR(20)` | YES | — | Unique when set, indexed |
| `hashed_password` | `VARCHAR(255)` | YES | — | bcrypt; null for OTP-only users |
| `full_name` | `VARCHAR(150)` | NO | — | Display name |
| `role` | `user_role` ENUM | NO | `customer` | `customer` \| `provider` \| `admin` |
| `is_active` | `BOOLEAN` | NO | `true` | Soft disable |
| `created_at` | `TIMESTAMPTZ` | NO | `now()` | |
| `updated_at` | `TIMESTAMPTZ` | NO | `now()` | App/ORM `onupdate` |

### Constraints

- `PRIMARY KEY (id)`
- `UNIQUE (email)` — `uq_users_email`
- `UNIQUE (phone)` — `uq_users_phone` (multiple NULLs allowed in Postgres)

### Indexes

- `ix_users_email`
- `ix_users_phone`
- `ix_users_role`
- PK index on `id`

### Enum type

- Postgres type `user_role`: `'customer'`, `'provider'`, `'admin'`

---

## 2. Table: `otp_challenges` **[Implemented]**

Email OTP send/verify attempts.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|--------|
| `id` | `UUID` | NO | `uuid4` | Primary key |
| `email` | `VARCHAR(255)` | NO | — | Lowercased, indexed |
| `code_hash` | `VARCHAR(255)` | NO | — | Hash of 6-digit code |
| `expires_at` | `TIMESTAMPTZ` | NO | — | Indexed |
| `attempt_count` | `INTEGER` | NO | `0` | Wrong verify attempts |
| `consumed_at` | `TIMESTAMPTZ` | YES | — | Set on successful verify |
| `created_at` | `TIMESTAMPTZ` | NO | `now()` | |

### Constraints / indexes

- `PRIMARY KEY (id)`
- `ix_otp_challenges_email`
- `ix_otp_challenges_expires_at`

### Lifecycle

`request` → insert row → `verify` checks hash/expiry/attempts → set `consumed_at`

---

## 3. Table: `provider_profiles` **[Planned]**

One-to-one extension of `users` for providers (skills, verification, availability, location).

Suggested columns (to implement later):

| Column | Type | Notes |
|--------|------|--------|
| `id` | `UUID` | PK |
| `user_id` | `UUID` | FK → `users.id`, **UNIQUE** (1:1) |
| `bio` | `TEXT` | Optional |
| `is_verified` | `BOOLEAN` | Admin verification |
| `is_online` | `BOOLEAN` | Availability |
| `rating_avg` | `NUMERIC` | Denormalized later |
| `service_radius_km` | `INTEGER` | Optional |
| `last_lat` / `last_lng` | `DOUBLE` | Live tracking later |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | |

**Why separate from `users`?** Keeps identity thin; provider-only fields don’t pollute customer rows.

---

## 4. Relationships

### Implemented

```text
(none between users and otp_challenges by FK)
otp_challenges.email  ≈  users.email   (logical link by email string)
```

OTP is intentionally keyed by email (works before/after user creation).

### Planned

```text
users (1) ────── (0..1) provider_profiles
users (1) ────── (N)    bookings          [later]
users (1) ────── (N)    addresses         [later]
```

---

## 5. Constraints (summary)

| Area | Rule |
|------|------|
| Identity | Unique email; unique phone when present |
| Roles | DB enum prevents invalid role strings |
| Soft delete | Prefer `is_active=false` over hard delete |
| OTP | Hashed code; expiry; attempt limit; single consume |
| Money / bookings | Future tables will use integer minor units (paisa), not float |

---

## 6. Indexes (summary)

| Table | Index | Purpose |
|-------|--------|---------|
| `users` | email, phone, role | Login + admin filters |
| `otp_challenges` | email, expires_at | Latest challenge + cleanup |
| Future `provider_profiles` | `user_id` unique | 1:1 join; `is_online` for matching |

---

## 7. Migrations

| Revision | Purpose |
|----------|---------|
| `20260801_0001` | Create `users` + `user_role` |
| `20260801_0002` | Create `otp_challenges` |

Command: `alembic upgrade head`
