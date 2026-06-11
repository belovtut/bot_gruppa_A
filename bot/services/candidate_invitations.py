"""Candidate actions on invitations (persistence + data for notifications)."""
from __future__ import annotations

from typing import Any, Dict, Literal, Union

from database import Database
from database.models import DeclineReason, InvitationStatus

AcceptResult = Union[Literal["missing"], Literal["closed"], Dict[str, Any]]
ThinkResult = Union[Literal["missing"], Literal["closed"], Dict[str, Any]]
DeclineResult = Union[Literal["missing"], Literal["closed"], Dict[str, Any]]


class CandidateInvitationService:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def accept(self, invitation_id: int) -> AcceptResult:
        inv = await self._db.get_invitation(invitation_id)
        if not inv:
            return "missing"
        if inv["status"] not in (
            InvitationStatus.SENT.value,
            InvitationStatus.THINKING.value,
        ):
            return "closed"
        await self._db.update_invitation_status(
            invitation_id, InvitationStatus.ACCEPTED.value
        )
        details = await self._db.get_invitation_with_details(invitation_id)
        return details if details else "missing"

    async def mark_thinking(self, invitation_id: int) -> ThinkResult:
        inv = await self._db.get_invitation(invitation_id)
        if not inv:
            return "missing"
        if inv["status"] not in (
            InvitationStatus.SENT.value,
            InvitationStatus.THINKING.value,
        ):
            return "closed"
        await self._db.update_invitation_status(
            invitation_id, InvitationStatus.THINKING.value
        )
        return await self._db.get_invitation(invitation_id) or "missing"

    async def decline_with_reason(
        self,
        invitation_id: int,
        *,
        reason_code: str,
        decline_comment: str | None = None,
    ) -> DeclineResult:
        inv = await self._db.get_invitation(invitation_id)
        if not inv:
            return "missing"
        if inv["status"] not in (
            InvitationStatus.SENT.value,
            InvitationStatus.THINKING.value,
        ):
            return "closed"
        await self._db.update_invitation_status(
            invitation_id,
            InvitationStatus.DECLINED.value,
            decline_reason=reason_code,
            decline_comment=decline_comment,
        )
        details = await self._db.get_invitation_with_details(invitation_id)
        return details if details else "missing"

    @staticmethod
    def decline_reason_label(reason_code: str) -> str:
        try:
            return DeclineReason(reason_code).label
        except ValueError:
            return reason_code
