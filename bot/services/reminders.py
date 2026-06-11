"""Scheduled reminder checks for pending invitation responses."""
from __future__ import annotations

import logging

from aiogram import Bot

from bot.config import SETTINGS
from database import Database
from bot.keyboards import get_reminder_keyboard

logger = logging.getLogger(__name__)


async def run_reminder_check(bot: Bot, db: Database) -> None:
    """Send reminders for invitations in ``thinking`` status past the threshold."""
    try:
        pending = await db.get_pending_reminders(hours=SETTINGS.reminder_hours)
    except Exception as exc:
        logger.error(
            "Reminder check failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        return

    for row in pending:
        inv_id = row["id"]
        tg_id = row.get("telegram_id")
        if not tg_id:
            continue

        title = row.get("event_title", "—")
        date = row.get("event_date", "")
        time_ = row.get("event_time", "")
        time_str = f" в {time_}" if time_ else ""

        text = (
            f"⏰ <b>Напоминание!</b>\n\n"
            f"У вас есть неотвеченное приглашение:\n"
            f"📌 {title}\n"
            f"📅 {date}{time_str}\n\n"
            f"Пожалуйста, примите решение."
        )
        try:
            await bot.send_message(
                chat_id=tg_id,
                text=text,
                parse_mode="HTML",
                reply_markup=get_reminder_keyboard(inv_id),
            )
            await db.mark_reminder_sent(inv_id)
            logger.info(
                "Reminder sent invitation_id=%s telegram_id=%s",
                inv_id,
                tg_id,
            )
        except Exception as exc:
            logger.warning(
                "Reminder send failed invitation_id=%s telegram_id=%s: %s: %s",
                inv_id,
                tg_id,
                type(exc).__name__,
                exc,
            )
