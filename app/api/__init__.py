"""
HTTP API package.

Structure:
  app/api/v1/     → versioned route modules (auth, users, bookings, ...)
  app/api/v1/router.py will aggregate them under /api/v1

Versioning lets us ship /api/v2 later without breaking the React Native app.
"""
