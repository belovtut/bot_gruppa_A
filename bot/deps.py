"""Shared dependencies and access helpers (no business rules)."""
from __future__ import annotations

from bot.config import SETTINGS


def is_admin(user_id: int) -> bool:
    """Return True if *user_id* is allowed to use admin features."""
    return user_id in SETTINGS.admin_ids
