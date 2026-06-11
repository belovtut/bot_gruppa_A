"""Lightweight typing helpers for database rows (no runtime validation)."""
from __future__ import annotations

from typing import Any, TypedDict


class ControllerRow(TypedDict, total=False):
    """Subset of fields commonly read from ``controllers``."""

    id: int
    telegram_id: int | None
    username: str | None
    name: str
    rating: float
    specializations: list[str]
    experience_types: list[str]
    preferred_areas: list[str]
    languages: list[str]
    location: str | None
    phone: str | None
    birth_date: str | None
    is_active: int


class InvitationRow(TypedDict, total=False):
    """Fields used after loading an ``invitations`` row."""

    id: int
    event_id: int
    controller_id: int
    status: str
    decline_reason: str | None
    decline_comment: str | None


# Rows from joins may contain arbitrary extra keys
RowDict = dict[str, Any]
