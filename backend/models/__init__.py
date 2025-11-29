# backend/models/__init__.py
"""
Data Models for FA CS Automator

Contains Pydantic models for assets, audit events, and other data structures.
"""

from .asset import Asset, AuditEvent

__all__ = ["Asset", "AuditEvent"]
