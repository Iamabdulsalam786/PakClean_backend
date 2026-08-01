"""
Database package: SQLAlchemy engine, sessions, and declarative base.

Keeps all persistence wiring in one place so routes/services never create
engines ad hoc — one connection strategy for the whole app.
"""
