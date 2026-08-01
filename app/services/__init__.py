"""
Service layer — business logic lives here, not in route handlers.

Routes: parse HTTP, call a service, return a schema.
Services: enforce rules (unique email, hash password, issue token), talk to DB.

This split keeps handlers thin and makes logic easier to unit-test without HTTP.
"""
