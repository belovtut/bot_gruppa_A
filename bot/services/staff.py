"""Staff application flows: formatting and admin↔candidate messaging."""
from __future__ import annotations

import logging
from html import escape
from typing import Any

from aiogram import Bot

from database.models import ExperienceType, Language, Specialization, WorkArea
from bot.utils import (
    age_from_birth_date,
    birth_date_to_display,
    format_db_timestamp_msk,
)
from bot.services.notifications import notify_admins

logger = logging.getLogger(__name__)


def staff_application_labels() -> dict[str, str]:
    return {
        "new": "🆕 Новая",
        "in_review": "👀 На рассмотрении",
        "closed": "✅ Закрыта",
        "deleted": "🗑 Удалена",
    }


def _enum_labels(values: list[str], enum_cls: Any) -> str:
    items = []
    for v in values:
        try:
            items.append(enum_cls(v).label)
        except (ValueError, KeyError):
            items.append(str(v))
    return ", ".join(items) if items else "—"


def format_staff_application_card(app: dict, messages: list[dict]) -> str:
    """HTML card for admin view of a staff application."""
    status_map = staff_application_labels()
    birth_disp = birth_date_to_display(app.get("birth_date"))
    age = age_from_birth_date(app.get("birth_date"))
    age_str = f" ({age} лет)" if age is not None else ""

    text = (
        f"📄 <b>Заявка #{app['id']}</b>\n\n"
        f"Статус: {status_map.get(app.get('status', 'new'), app.get('status', 'new'))}\n"
        f"👤 ФИО: {escape(app.get('full_name', '—'))}\n"
        f"🎂 Дата рождения: {escape(birth_disp)}{age_str}\n"
        f"📱 Телефон: {escape(app.get('phone') or '—')}\n"
        f"👤 Username: @{escape(app.get('username') or '—')}\n"
        f"🆔 Telegram ID: {app.get('user_id')}\n"
        f"🎯 Специализации: {_enum_labels(app.get('specializations', []), Specialization)}\n"
        f"🏢 Опыт: {_enum_labels(app.get('experience_types', []), ExperienceType)}\n"
        f"📍 Районы: {_enum_labels(app.get('preferred_areas', []), WorkArea)}\n"
        f"🌐 Языки: {_enum_labels(app.get('languages', []), Language)}"
    )
    if messages:
        last = messages[0]
        who = "Админ" if last.get("sender_role") == "admin" else "Кандидат"
        text += f"\n\n🕓 Последнее сообщение ({who}):\n{escape(last.get('message_text', ''))}"
    return text


def format_dialog_history(messages: list[dict]) -> str:
    if not messages:
        return "Сообщений пока нет."
    lines: list[str] = []
    for item in reversed(messages):
        role = "Админ" if item.get("sender_role") == "admin" else "Кандидат"
        created = format_db_timestamp_msk(item.get("created_at"))
        lines.append(
            f"<b>{role}</b> [{created}]\n"
            f"📢 {escape(item.get('message_text', ''))}"
        )
    return "\n\n".join(lines)


async def send_admin_reply_to_candidate(
    bot: Bot,
    *,
    candidate_chat_id: int,
    text: str,
    thread_text: str,
    reply_markup: Any,
) -> bool:
    """Return True if the candidate received the Telegram message."""
    try:
        await bot.send_message(
            chat_id=candidate_chat_id,
            text=(
                "🆕 <b>Сообщение от администратора по вашей заявке в штат КРС</b>\n\n"
                f"📢 {escape(text)}\n\n"
                f"💬 <b>История диалога:</b>\n\n"
                f"{thread_text}\n\n"
                "Нажмите кнопку «Ответить администратору», чтобы отправить сообщение"
            ),
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
        return True
    except Exception as exc:
        logger.warning(
            "Admin reply delivery failed chat_id=%s: %s: %s",
            candidate_chat_id,
            type(exc).__name__,
            exc,
        )
        return False


async def notify_admins_staff_reply(
    bot: Bot,
    *,
    notify_text: str,
    reply_markup: Any,
) -> None:
    await notify_admins(bot, notify_text, reply_markup=reply_markup)
