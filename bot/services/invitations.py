"""Invitation creation and Telegram delivery orchestration."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from aiogram import Bot

from bot.config import SETTINGS
from bot.keyboards import get_invitation_buttons
from database import Database
from bot.utils import format_invitation_message

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InvitationDispatchResult:
    success: int
    failed: int
    skipped_no_telegram: int
    event_id: int


class InvitationFlowService:
    """Create event + invitation rows, then send Telegram messages."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create_event_and_deliver(
        self,
        bot: Bot,
        *,
        event_data: Dict[str, Any],
        selected_controller_ids: List[int],
        created_by: int,
    ) -> InvitationDispatchResult:
        """Persist event + invitations atomically, then send messages (best-effort).

        ``skipped_no_telegram`` counts controllers in *selected_controller_ids* that
        had no invitation row created (no ``telegram_id``), matching legacy behaviour.
        """
        title = event_data.get("title", "—")
        event_date = event_data.get("event_date", "")
        location = event_data.get("location", "")
        event_id, delivery = await self._db.create_event_with_invitations(
            title=title,
            event_date=event_date,
            location=location,
            event_time=event_data.get("event_time"),
            rate=event_data.get("rate"),
            dress_code=event_data.get("dress_code"),
            task_description=event_data.get("task_description"),
            description=None,
            created_by=created_by,
            controller_ids=selected_controller_ids,
        )

        event = await self._db.get_event(event_id)
        if not event:
            logger.error("Event %s missing after atomic create", event_id)
            return InvitationDispatchResult(
                success=0,
                failed=0,
                skipped_no_telegram=len(selected_controller_ids),
                event_id=event_id,
            )

        inv_text = format_invitation_message(event)
        success = 0
        failed = 0
        for row in delivery:
            try:
                await bot.send_message(
                    chat_id=row["telegram_id"],
                    text=inv_text,
                    parse_mode="HTML",
                    reply_markup=get_invitation_buttons(row["invitation_id"]),
                )
                success += 1
            except Exception as exc:
                logger.warning(
                    "Invitation Telegram delivery failed invitation_id=%s tg=%s: %s: %s",
                    row.get("invitation_id"),
                    row.get("telegram_id"),
                    type(exc).__name__,
                    exc,
                )
                failed += 1
            await asyncio.sleep(SETTINGS.broadcast_delay)

        invited_ids = {r["controller_id"] for r in delivery}
        skipped = len([cid for cid in selected_controller_ids if cid not in invited_ids])

        return InvitationDispatchResult(
            success=success,
            failed=failed,
            skipped_no_telegram=skipped,
            event_id=event_id,
        )
