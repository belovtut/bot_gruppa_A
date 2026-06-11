"""Notify configured admins via Telegram (best-effort)."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot

from bot.config import SETTINGS

logger = logging.getLogger(__name__)


async def notify_admins(
    bot: Bot,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    reply_markup: Any = None,
) -> None:
    """Send the same text to every admin id; log individual failures."""
    for admin_id in SETTINGS.admin_ids:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
        except Exception as exc:
            logger.warning(
                "Admin notify failed admin_id=%s: %s: %s",
                admin_id,
                type(exc).__name__,
                exc,
            )
