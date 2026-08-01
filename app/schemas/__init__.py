"""
Pydantic schemas (DTOs) — request/response shapes for the API.

Why separate from ORM models?
  - Clients must not see hashed_password or internal flags by accident
  - Request validation (email format, password length) lives here
  - You can version/change API JSON without renaming DB columns

Import public schemas here as we add them, e.g.:
  from app.schemas.auth import Token, UserLogin, UserRegister
"""
