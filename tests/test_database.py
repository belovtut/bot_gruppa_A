"""Tests for database/db.py — async Database class with a temporary SQLite file."""
import json
import pytest
import pytest_asyncio
from database.db import Database
from database.models import InvitationStatus


@pytest_asyncio.fixture
async def db(in_memory_db_path):
    """Initialised Database backed by a temporary file."""
    instance = Database(in_memory_db_path)
    await instance.init_db()
    return instance


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

class TestInitDb:
    async def test_creates_tables(self, db):
        import aiosqlite
        async with aiosqlite.connect(db.db_path) as conn:
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) as cur:
                tables = {row[0] for row in await cur.fetchall()}
        expected = {
            "users", "controllers", "events",
            "invitations", "event_history",
            "staff_applications", "staff_application_messages",
        }
        assert expected.issubset(tables)

    async def test_idempotent_second_call(self, db):
        """Calling init_db twice must not raise."""
        await db.init_db()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class TestUsers:
    async def test_add_and_count(self, db):
        assert await db.get_user_count() == 0
        await db.add_user(111, "alice", "Alice", "Smith")
        assert await db.get_user_count() == 1

    async def test_upsert_same_user(self, db):
        await db.add_user(111, "alice", "Alice", "Smith")
        await db.add_user(111, "alice_new", "Alice", "Smith")
        assert await db.get_user_count() == 1

    async def test_get_all_user_ids(self, db):
        await db.add_user(10)
        await db.add_user(20)
        ids = await db.get_all_user_ids()
        assert set(ids) == {10, 20}


# ---------------------------------------------------------------------------
# Controllers
# ---------------------------------------------------------------------------

class TestControllers:
    async def _add_sample(self, db, **kwargs):
        defaults = dict(
            telegram_id=None,
            username=None,
            name="Иванов Иван Иванович",
            specializations=["entrance"],
            experience_types=["concerts"],
            rating=4.0,
            preferred_areas=["nn_sovetsky"],
            languages=["russian"],
        )
        defaults.update(kwargs)
        return await db.add_controller(**defaults)

    async def test_add_returns_id(self, db):
        cid = await self._add_sample(db)
        assert isinstance(cid, int)
        assert cid > 0

    async def test_search_no_filters_returns_all(self, db):
        await self._add_sample(db, name="Иванов Иван Иванович")
        await self._add_sample(db, name="Петров Пётр Петрович")
        results, total = await db.search_controllers()
        assert total == 2

    async def test_search_by_min_rating(self, db):
        await self._add_sample(db, rating=3.0, name="Низкий рейтинг")
        await self._add_sample(db, rating=4.5, name="Высокий рейтинг")
        results, total = await db.search_controllers(min_rating=4.0)
        assert total == 1
        assert results[0]["name"] == "Высокий рейтинг"

    async def test_search_by_specialization(self, db):
        await self._add_sample(db, specializations=["entrance"], name="Входной")
        await self._add_sample(db, specializations=["hall"], name="Зальный")
        results, total = await db.search_controllers(specializations=["entrance"])
        assert total == 1
        assert results[0]["name"] == "Входной"

    async def test_search_inactive_excluded(self, db):
        cid = await self._add_sample(db)
        await db.update_controller(cid, is_active=0)
        _, total = await db.search_controllers()
        assert total == 0

    async def test_upsert_same_telegram_id(self, db):
        tid = 999
        await db.add_controller(telegram_id=tid, username=None, name="Первый")
        await db.add_controller(telegram_id=tid, username=None, name="Обновлённый")
        _, total = await db.search_controllers()
        assert total == 1


# ---------------------------------------------------------------------------
# Events and invitations
# ---------------------------------------------------------------------------

class TestEventsAndInvitations:
    async def _create_event_with_controller(self, db):
        cid = await db.add_controller(
            telegram_id=12345,
            username="tester",
            name="Тестов Тест Тестович",
            specializations=["entrance"],
        )
        await db.add_user(12345)
        event_id, delivery = await db.create_event_with_invitations(
            title="Тест-событие",
            event_date="2025-09-01",
            location="Нижний Новгород",
            controller_ids=[cid],
            created_by=12345,
        )
        return event_id, cid, delivery

    async def test_create_event_returns_id(self, db):
        event_id, _, _ = await self._create_event_with_controller(db)
        assert event_id > 0

    async def test_delivery_list_has_telegram_id(self, db):
        _, _, delivery = await self._create_event_with_controller(db)
        assert len(delivery) == 1
        assert delivery[0]["telegram_id"] == 12345

    async def test_update_invitation_status_accepted(self, db):
        _, _, delivery = await self._create_event_with_controller(db)
        inv_id = delivery[0]["invitation_id"]
        await db.update_invitation_status(inv_id, InvitationStatus.ACCEPTED.value)
        inv = await db.get_invitation(inv_id)
        assert inv["status"] == InvitationStatus.ACCEPTED.value

    async def test_update_invitation_status_declined_with_reason(self, db):
        _, _, delivery = await self._create_event_with_controller(db)
        inv_id = delivery[0]["invitation_id"]
        await db.update_invitation_status(
            inv_id,
            InvitationStatus.DECLINED.value,
            decline_reason="date",
        )
        inv = await db.get_invitation(inv_id)
        assert inv["status"] == InvitationStatus.DECLINED.value
        assert inv["decline_reason"] == "date"

    async def test_unique_invitation_per_controller_per_event(self, db):
        """Only one invitation row per (event, controller) pair must exist."""
        await db.add_user(88888)
        cid = await db.add_controller(
            telegram_id=88888, username=None, name="Дублёр"
        )
        event_id, delivery = await db.create_event_with_invitations(
            title="Событие",
            event_date="2025-09-01",
            location="НН",
            controller_ids=[cid],
            created_by=88888,
        )
        assert len(delivery) == 1
        import aiosqlite
        async with aiosqlite.connect(db.db_path) as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM invitations WHERE event_id=? AND controller_id=?",
                (event_id, cid),
            ) as cur:
                count = (await cur.fetchone())[0]
        assert count == 1


# ---------------------------------------------------------------------------
# Reminder logic
# ---------------------------------------------------------------------------

class TestReminders:
    async def test_no_reminders_when_fresh(self, db):
        pending = await db.get_pending_reminders(hours=0)
        assert pending == []

    async def test_reminder_marked_sent(self, db):
        cid = await db.add_controller(
            telegram_id=77777, username=None, name="Напоминаемый"
        )
        await db.add_user(77777)
        event_id, delivery = await db.create_event_with_invitations(
            title="Матч",
            event_date="2025-10-01",
            location="НН",
            controller_ids=[cid],
            created_by=77777,
        )
        inv_id = delivery[0]["invitation_id"]
        await db.update_invitation_status(inv_id, InvitationStatus.THINKING.value)
        await db.mark_reminder_sent(inv_id)

        import aiosqlite
        async with aiosqlite.connect(db.db_path) as conn:
            async with conn.execute(
                "SELECT reminder_sent FROM invitations WHERE id=?", (inv_id,)
            ) as cur:
                row = await cur.fetchone()
        assert row[0] == 1
