"""Tests for the service layer — CandidateInvitationService and controller_filters."""
import pytest
import pytest_asyncio
from database.db import Database
from database.models import FilterState, InvitationStatus
from bot.services.candidate_invitations import CandidateInvitationService
from bot.services.controller_filters import filters_to_search_kwargs, work_area_labels


# ---------------------------------------------------------------------------
# controller_filters — pure functions
# ---------------------------------------------------------------------------

class TestWorkAreaLabels:
    def test_valid_code_returns_label(self):
        labels = work_area_labels(["nn_sovetsky"])
        assert labels == ["НН, Советский"]

    def test_unknown_code_returned_as_is(self):
        labels = work_area_labels(["unknown_area"])
        assert labels == ["unknown_area"]

    def test_empty_list(self):
        assert work_area_labels([]) == []


class TestFiltersToSearchKwargs:
    def test_empty_filter_state(self):
        fs = FilterState()
        kwargs = filters_to_search_kwargs(fs)
        assert kwargs["specializations"] is None
        assert kwargs["min_rating"] == 0.0
        assert kwargs["experience_types"] is None
        assert kwargs["areas"] is None
        assert kwargs["languages"] is None
        assert kwargs["available_date"] is None

    def test_specializations_passed_through(self):
        fs = FilterState(specializations=["entrance", "vip"])
        kwargs = filters_to_search_kwargs(fs)
        assert kwargs["specializations"] == ["entrance", "vip"]

    def test_areas_translated_to_labels(self):
        fs = FilterState(areas=["nn_sovetsky", "nn_avtozavod"])
        kwargs = filters_to_search_kwargs(fs)
        assert "НН, Советский" in kwargs["areas"]
        assert "НН, Автозавод" in kwargs["areas"]

    def test_empty_specializations_become_none(self):
        fs = FilterState(specializations=[])
        kwargs = filters_to_search_kwargs(fs)
        assert kwargs["specializations"] is None

    def test_rating_passed_through(self):
        fs = FilterState(min_rating=3.5)
        kwargs = filters_to_search_kwargs(fs)
        assert kwargs["min_rating"] == 3.5


# ---------------------------------------------------------------------------
# CandidateInvitationService — integration with in-memory DB
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def svc_with_invitation(in_memory_db_path):
    """Returns (service, invitation_id) for a fresh DB with one pending invitation."""
    db = Database(in_memory_db_path)
    await db.init_db()
    await db.add_user(55555)
    cid = await db.add_controller(
        telegram_id=55555,
        username="candidate",
        name="Кандидатов Кандидат Кандидатович",
    )
    event_id, delivery = await db.create_event_with_invitations(
        title="Тест",
        event_date="2025-11-01",
        location="НН",
        controller_ids=[cid],
        created_by=55555,
    )
    inv_id = delivery[0]["invitation_id"]
    service = CandidateInvitationService(db)
    return service, inv_id, db


class TestCandidateInvitationServiceAccept:
    async def test_accept_changes_status(self, svc_with_invitation):
        service, inv_id, db = svc_with_invitation
        result = await service.accept(inv_id)
        assert isinstance(result, dict)
        inv = await db.get_invitation(inv_id)
        assert inv["status"] == InvitationStatus.ACCEPTED.value

    async def test_accept_missing_returns_sentinel(self, svc_with_invitation):
        service, _, _ = svc_with_invitation
        result = await service.accept(999999)
        assert result == "missing"

    async def test_accept_already_declined_returns_closed(self, svc_with_invitation):
        service, inv_id, db = svc_with_invitation
        await db.update_invitation_status(inv_id, InvitationStatus.DECLINED.value)
        result = await service.accept(inv_id)
        assert result == "closed"


class TestCandidateInvitationServiceThinking:
    async def test_mark_thinking_changes_status(self, svc_with_invitation):
        service, inv_id, db = svc_with_invitation
        result = await service.mark_thinking(inv_id)
        assert result != "missing" and result != "closed"
        inv = await db.get_invitation(inv_id)
        assert inv["status"] == InvitationStatus.THINKING.value

    async def test_thinking_then_accept(self, svc_with_invitation):
        service, inv_id, db = svc_with_invitation
        await service.mark_thinking(inv_id)
        result = await service.accept(inv_id)
        assert isinstance(result, dict)
        inv = await db.get_invitation(inv_id)
        assert inv["status"] == InvitationStatus.ACCEPTED.value


class TestCandidateInvitationServiceDecline:
    async def test_decline_sets_status_and_reason(self, svc_with_invitation):
        service, inv_id, db = svc_with_invitation
        result = await service.decline_with_reason(inv_id, reason_code="date")
        assert isinstance(result, dict)
        inv = await db.get_invitation(inv_id)
        assert inv["status"] == InvitationStatus.DECLINED.value
        assert inv["decline_reason"] == "date"

    async def test_decline_with_comment(self, svc_with_invitation):
        service, inv_id, db = svc_with_invitation
        await service.decline_with_reason(
            inv_id, reason_code="other", decline_comment="Семейные обстоятельства"
        )
        inv = await db.get_invitation(inv_id)
        assert inv["decline_comment"] == "Семейные обстоятельства"

    async def test_decline_missing_returns_sentinel(self, svc_with_invitation):
        service, _, _ = svc_with_invitation
        result = await service.decline_with_reason(99999, reason_code="date")
        assert result == "missing"

    async def test_decline_reason_label(self):
        label = CandidateInvitationService.decline_reason_label("date")
        assert label == "Неудобная дата"

    async def test_decline_reason_label_unknown(self):
        label = CandidateInvitationService.decline_reason_label("nonexistent")
        assert label == "nonexistent"
