"""
Core package: cross-cutting infrastructure used by the whole API.

Typical contents (we add these one file at a time):
  - config.py      → environment settings
  - security.py    → password hashing + JWT
  - dependencies.py → FastAPI Depends() helpers (db session, current user)
  - exceptions.py  → domain errors mapped to HTTP responses
"""
