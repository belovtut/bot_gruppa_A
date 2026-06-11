"""Utility helpers for formatting and validation."""
import re
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from database.models import (
    Specialization, ExperienceType, Language,
    InvitationStatus, DeclineReason,
)


def format_controller_card(ctrl: Dict, *, short: bool = False) -> str:
    """Format a controller record into a readable card.

    Args:
        ctrl: Controller dict from the database.
        short: If True, return a one-line summary.
    """
    name = ctrl.get("name", "—")
    rating = ctrl.get("rating", 0.0)
    stars = format_rating(rating)

    if short:
        specs = format_enum_list(ctrl.get("specializations", []), Specialization)
        loc = ctrl.get("location") or "—"
        return f"{name} {stars}\n   🎯 {specs} | 📍 {loc}"

    lines = [f"👤 <b>{name}</b>"]
    lines.append(f"⭐ Рейтинг: {stars}")

    specs = format_enum_list(ctrl.get("specializations", []), Specialization)
    if specs:
        lines.append(f"🎯 Специализация: {specs}")

    exps = format_enum_list(ctrl.get("experience_types", []), ExperienceType)
    if exps:
        lines.append(f"🏢 Опыт: {exps}")

    loc = ctrl.get("location")
    if loc:
        lines.append(f"📍 Локация: {loc}")

    langs = format_enum_list(ctrl.get("languages", []), Language)
    if langs:
        lines.append(f"🌐 Языки: {langs}")

    phone = ctrl.get("phone")
    if phone:
        lines.append(f"📱 Телефон: {phone}")

    birth_date = birth_date_to_display(ctrl.get("birth_date"))
    if birth_date != "—":
        age = age_from_birth_date(ctrl.get("birth_date"))
        age_str = f" ({age} лет)" if age is not None else ""
        lines.append(f"🎂 Дата рождения: {birth_date}{age_str}")

    tg = ctrl.get("telegram_id")
    if tg:
        lines.append(f"🆔 Telegram ID: {tg}")

    username = ctrl.get("username")
    if username:
        lines.append(f"👤 Username: @{username}")

    return "\n".join(lines)


def format_event_card(event: Dict) -> str:
    """Format an event record into a readable message."""
    lines = [f"📌 <b>{event.get('title', '—')}</b>"]
    lines.append(f"📅 Дата: {event.get('event_date', '—')}")

    if event.get("event_time"):
        lines.append(f"🕐 Время: {event['event_time']}")

    lines.append(f"📍 Локация: {event.get('location', '—')}")

    if event.get("rate"):
        lines.append(f"💰 Ставка: {event['rate']}")
    if event.get("dress_code"):
        lines.append(f"👔 Дресс-код: {event['dress_code']}")
    if event.get("task_description"):
        lines.append(f"📝 Задача: {event['task_description']}")

    return "\n".join(lines)


def format_invitation_message(event: Dict) -> str:
    """Build the invitation message that controllers will receive."""
    header = "📨 <b>Новое приглашение на мероприятие!</b>\n"
    return header + "\n" + format_event_card(event)


def format_history_entry(entry: Dict) -> str:
    """Format a single event_history row."""
    date = entry.get("event_date", "—")
    title = entry.get("title", "—")
    loc = entry.get("location", "—")
    role = entry.get("role", "—")
    r = entry.get("admin_rating")
    rating_str = f"⭐ {r}" if r else "—"
    comment = entry.get("admin_comment") or ""
    line = f"📅 {date} — <b>{title}</b>\n   📍 {loc} | 🎯 {role} | {rating_str}"
    if comment:
        line += f"\n   💬 {comment}"
    return line


def format_rating(rating: float) -> str:
    """Return a rating string like '4.5/5.0'."""
    return f"{rating:.1f}/5.0"


def validate_date(text: str) -> Optional[str]:
    """Parse date from DD.MM.YYYY and return YYYY-MM-DD or None."""
    text = text.strip()
    for fmt, out_fmt in [
        (r"^\d{2}\.\d{2}\.\d{4}$", "%d.%m.%Y"),
        (r"^\d{4}-\d{2}-\d{2}$", "%Y-%m-%d"),
    ]:
        if re.match(fmt, text):
            try:
                dt = datetime.strptime(text, out_fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                return None
    return None


def validate_time(text: str) -> Optional[str]:
    """Parse time from HH:MM and return HH:MM or None."""
    text = text.strip()
    if re.match(r"^\d{1,2}:\d{2}$", text):
        try:
            dt = datetime.strptime(text, "%H:%M")
            return dt.strftime("%H:%M")
        except ValueError:
            return None
    return None


def validate_full_name(text: str) -> Optional[str]:
    """Validate full name as at least 3 words (no initials)."""
    value = " ".join((text or "").strip().split())
    if not value or "." in value:
        return None

    parts = value.split(" ")
    if len(parts) < 3:
        return None

    for part in parts[:3]:
        # Allows Russian/Latin letters and hyphenated surnames.
        if not re.match(r"^[A-Za-zА-Яа-яЁё-]{2,}$", part):
            return None
    return value


def validate_phone_ru(text: str) -> Optional[str]:
    """Validate Russian phone in strict format +7XXXXXXXXXX."""
    value = (text or "").strip()
    if re.fullmatch(r"\+7\d{10}", value):
        return value
    return None


def validate_birth_date(text: str, min_age: int = 18, max_age: int = 80) -> Optional[str]:
    """Validate birth date DD.MM.YYYY and return ISO YYYY-MM-DD."""
    raw = (text or "").strip()
    if not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", raw):
        return None
    try:
        dt = datetime.strptime(raw, "%d.%m.%Y").date()
    except ValueError:
        return None

    today = date.today()
    age = today.year - dt.year - ((today.month, today.day) < (dt.month, dt.day))
    if age < min_age or age > max_age:
        return None
    return dt.strftime("%Y-%m-%d")


def birth_date_to_display(iso_date: Optional[str]) -> str:
    """Convert ISO birth date to DD.MM.YYYY format."""
    if not iso_date:
        return "—"
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return iso_date


def age_from_birth_date(iso_date: Optional[str]) -> Optional[int]:
    """Calculate age in full years from ISO birth date."""
    if not iso_date:
        return None
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    today = date.today()
    return today.year - dt.year - ((today.month, today.day) < (dt.month, dt.day))


def format_db_timestamp_msk(value: Optional[str]) -> str:
    """Convert DB UTC timestamp (YYYY-MM-DD HH:MM[:SS]) to Moscow time string."""
    if not value:
        return "—"

    parsed = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(value, fmt)
            break
        except ValueError:
            continue

    if not parsed:
        return value

    utc_dt = parsed.replace(tzinfo=timezone.utc)
    msk_dt = utc_dt.astimezone(timezone(timedelta(hours=3)))
    return msk_dt.strftime("%d.%m.%Y, %H:%M")


def format_enum_list(values: list, enum_cls) -> str:
    """Convert a list of enum values to their labels, joined by comma."""
    if not values:
        return "—"
    labels = []
    for v in values:
        try:
            labels.append(enum_cls(v).label)
        except (ValueError, KeyError):
            labels.append(str(v))
    return ", ".join(labels) if labels else "—"
