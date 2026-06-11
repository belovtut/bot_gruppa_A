"""Broadcast orchestration (admin → all bot users)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram.types import Message

from database import Database

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BroadcastResult:
    success: int
    failed: int
    total: int


async def run_broadcast_copy(
    message: Message,
    db: Database,
    *,
    delay_seconds: float,
) -> BroadcastResult:
    """Copy *message* to every stored user id; rate-limited by *delay_seconds*."""
    user_ids = await db.get_all_user_ids()
    success = 0
    failed = 0
    for uid in user_ids:
        try:
            await message.copy_to(uid)
            success += 1
        except Exception as exc:
            logger.warning(
                "Broadcast failed for user_id=%s: %s: %s",
                uid,
                type(exc).__name__,
                exc,
            )
            failed += 1
        await asyncio.sleep(delay_seconds)
    return BroadcastResult(success=success, failed=failed, total=len(user_ids))
