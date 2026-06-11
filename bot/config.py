"""Centralized configuration loaded from the environment."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    """Immutable application settings (env-backed)."""

    bot_token: str
    admin_ids: tuple[int, ...]
    db_path: str
    reminder_hours: int
    broadcast_delay: float


def load_settings() -> Settings:
    """Parse environment variables into a Settings instance."""
    raw_admins = os.getenv("ADMIN_IDS", "")
    admin_ids: list[int] = []
    if raw_admins:
        for token in raw_admins.split(","):
            # Strip inline comments (e.g. "12345 # note") and whitespace.
            clean = token.split("#")[0].strip()
            if not clean:
                continue
            try:
                admin_ids.append(int(clean))
            except ValueError:
                logger.warning("Skipping invalid ADMIN_IDS entry: %r", token.strip())

    return Settings(
        bot_token=os.getenv("BOT_TOKEN", ""),
        admin_ids=tuple(admin_ids),
        db_path=os.getenv("DB_PATH", "database/data/users.db"),
        reminder_hours=int(os.getenv("REMINDER_HOURS", "6")),
        broadcast_delay=float(os.getenv("BROADCAST_DELAY", "0.05")),
    )


SETTINGS = load_settings()

# Backward-compatible module-level names (existing imports keep working)
BOT_TOKEN: str = SETTINGS.bot_token
ADMIN_IDS: list[int] = list(SETTINGS.admin_ids)
DB_PATH: str = SETTINGS.db_path
REMINDER_HOURS: int = SETTINGS.reminder_hours
BROADCAST_DELAY: float = SETTINGS.broadcast_delay
