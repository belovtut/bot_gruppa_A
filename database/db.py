"""Database module for user, controller, event, and invitation data.

Uses aiosqlite with WAL journal mode, foreign keys, and parameterized queries
to ensure data integrity and safety.

Consistency note (Telegram vs SQLite)
-------------------------------------
Operations that touch both the database and the Telegram Bot API are not a
single distributed transaction: a row may be committed before a message is
delivered, or delivery may fail after commit. Callers should treat Telegram
send failures as observable delivery errors, not as automatic DB rollbacks.
Multi-row writes that must succeed or fail together use a single SQLite
connection (see :meth:`Database.connection` and batch helpers).
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import aiosqlite

logger = logging.getLogger(__name__)


class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Open one SQLite connection with WAL + foreign keys (commits on exit).

        Use for multiple statements that should share one transaction boundary.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    async def _ensure_column(
        self,
        db: aiosqlite.Connection,
        table: str,
        column: str,
        ddl_fragment: str,
    ) -> None:
        """Add column if it is missing (lightweight migration)."""
        async with db.execute(f"PRAGMA table_info({table})") as cur:
            columns = [row[1] for row in await cur.fetchall()]
        if column not in columns:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_fragment}")

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    async def init_db(self) -> None:
        """Create all tables and indexes if they don't exist."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")

            # Telegram users who have interacted with the bot
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id    INTEGER PRIMARY KEY,
                    username   TEXT,
                    first_name TEXT,
                    last_name  TEXT,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Staff database (controllers / stewards)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS controllers (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id     INTEGER UNIQUE,
                    username        TEXT,
                    name            TEXT NOT NULL,
                    birth_date      TEXT,
                    phone           TEXT,
                    specializations TEXT DEFAULT '[]',
                    experience_types TEXT DEFAULT '[]',
                    rating          REAL DEFAULT 0.0,
                    location        TEXT,
                    preferred_areas TEXT DEFAULT '[]',
                    languages       TEXT DEFAULT '[]',
                    is_active       INTEGER DEFAULT 1,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Events (invitations are sent for specific events)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    title            TEXT NOT NULL,
                    description      TEXT,
                    event_date       TEXT NOT NULL,
                    event_time       TEXT,
                    location         TEXT NOT NULL,
                    rate             TEXT,
                    dress_code       TEXT,
                    task_description TEXT,
                    created_by       INTEGER,
                    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status           TEXT DEFAULT 'active',
                    FOREIGN KEY (created_by) REFERENCES users(user_id)
                )
            """)

            # Individual invitations linking events ↔ controllers
            await db.execute("""
                CREATE TABLE IF NOT EXISTS invitations (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id        INTEGER NOT NULL,
                    controller_id   INTEGER NOT NULL,
                    status          TEXT DEFAULT 'sent',
                    decline_reason  TEXT,
                    decline_comment TEXT,
                    sent_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    responded_at    TIMESTAMP,
                    reminder_sent   INTEGER DEFAULT 0,
                    FOREIGN KEY (event_id)      REFERENCES events(id),
                    FOREIGN KEY (controller_id) REFERENCES controllers(id)
                )
            """)

            # Completed participation records
            await db.execute("""
                CREATE TABLE IF NOT EXISTS event_history (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    controller_id   INTEGER NOT NULL,
                    event_id        INTEGER NOT NULL,
                    role            TEXT,
                    admin_rating    REAL,
                    admin_comment   TEXT,
                    completed_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (controller_id) REFERENCES controllers(id),
                    FOREIGN KEY (event_id)      REFERENCES events(id)
                )
            """)

            # Incoming candidates applying for staff positions
            await db.execute("""
                CREATE TABLE IF NOT EXISTS staff_applications (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id          INTEGER NOT NULL,
                    username         TEXT,
                    first_name       TEXT,
                    last_name        TEXT,
                    full_name        TEXT NOT NULL,
                    birth_date       TEXT,
                    phone            TEXT,
                    specializations  TEXT DEFAULT '[]',
                    experience_types TEXT DEFAULT '[]',
                    preferred_areas  TEXT DEFAULT '[]',
                    languages        TEXT DEFAULT '[]',
                    status           TEXT DEFAULT 'new',
                    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS staff_application_messages (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    application_id  INTEGER NOT NULL,
                    sender_id       INTEGER NOT NULL,
                    sender_role     TEXT NOT NULL,
                    message_text    TEXT NOT NULL,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (application_id) REFERENCES staff_applications(id)
                )
            """)

            # Performance indexes
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ctrl_tg     ON controllers(telegram_id)")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ctrl_rating ON controllers(rating)")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ctrl_active ON controllers(is_active)")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_inv_event   ON invitations(event_id)")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_inv_ctrl    ON invitations(controller_id)")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_inv_status  ON invitations(status)")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_eh_ctrl     ON event_history(controller_id)")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_sa_status   ON staff_applications(status)")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_sa_user     ON staff_applications(user_id)")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_sam_app     ON staff_application_messages(application_id)")

            # Unique constraint: one invitation per controller per event.
            # Wrapped to survive existing databases that already have duplicate rows.
            try:
                await db.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_inv_unique "
                    "ON invitations(event_id, controller_id)"
                )
            except Exception:
                logger.warning(
                    "Could not create unique index on invitations(event_id, controller_id) — "
                    "duplicate rows may already exist in the database."
                )

            # Migrations for existing databases
            await self._ensure_column(db, "controllers", "username", "TEXT")
            await self._ensure_column(db, "controllers", "birth_date", "TEXT")
            await self._ensure_column(db, "staff_applications", "birth_date", "TEXT")

            await db.commit()

    # ------------------------------------------------------------------
    # User operations
    # ------------------------------------------------------------------

    async def add_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> None:
        """Insert or update a Telegram user record."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username   = excluded.username,
                    first_name = excluded.first_name,
                    last_name  = excluded.last_name
                """,
                (user_id, username, first_name, last_name),
            )
            await db.commit()

    async def get_all_user_ids(self) -> List[int]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id FROM users") as cur:
                return [row[0] for row in await cur.fetchall()]

    async def get_user_count(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cur:
                row = await cur.fetchone()
                return row[0] if row else 0

    # ------------------------------------------------------------------
    # Controller operations
    # ------------------------------------------------------------------

    async def add_controller(
        self,
        telegram_id: Optional[int],
        username: Optional[str],
        name: str,
        birth_date: Optional[str] = None,
        phone: Optional[str] = None,
        specializations: Optional[List[str]] = None,
        experience_types: Optional[List[str]] = None,
        rating: float = 0.0,
        location: Optional[str] = None,
        preferred_areas: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
    ) -> int:
        """Add or upsert a controller record. Returns row id."""
        async with aiosqlite.connect(self.db_path) as db:
            if telegram_id is not None:
                cur = await db.execute(
                    """
                    INSERT INTO controllers
                        (telegram_id, username, name, birth_date, phone, specializations,
                         experience_types, rating, location, preferred_areas, languages)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(telegram_id) DO UPDATE SET
                        username         = COALESCE(excluded.username, controllers.username),
                        name             = excluded.name,
                        birth_date       = COALESCE(excluded.birth_date, controllers.birth_date),
                        phone            = COALESCE(excluded.phone, controllers.phone),
                        specializations  = excluded.specializations,
                        experience_types = excluded.experience_types,
                        rating           = CASE WHEN excluded.rating > 0
                                                THEN excluded.rating
                                                ELSE controllers.rating END,
                        location         = COALESCE(excluded.location, controllers.location),
                        preferred_areas  = excluded.preferred_areas,
                        languages        = excluded.languages,
                        updated_at       = CURRENT_TIMESTAMP
                    """,
                    (
                        telegram_id,
                        username,
                        name,
                        birth_date,
                        phone,
                        json.dumps(specializations or []),
                        json.dumps(experience_types or []),
                        rating,
                        location,
                        json.dumps(preferred_areas or []),
                        json.dumps(languages or []),
                    ),
                )
            else:
                cur = await db.execute(
                    """
                    INSERT INTO controllers
                        (telegram_id, username, name, birth_date, phone, specializations,
                         experience_types, rating, location, preferred_areas, languages)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        None,
                        username,
                        name,
                        birth_date,
                        phone,
                        json.dumps(specializations or []),
                        json.dumps(experience_types or []),
                        rating,
                        location,
                        json.dumps(preferred_areas or []),
                        json.dumps(languages or []),
                    ),
                )
            await db.commit()
            return cur.lastrowid  # type: ignore[return-value]

    async def get_controller_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM controllers WHERE telegram_id = ? AND is_active = 1",
                (telegram_id,),
            ) as cur:
                row = await cur.fetchone()
                return self._parse_controller(row) if row else None

    async def link_controller_telegram_by_username(
        self,
        telegram_id: int,
        username: Optional[str],
    ) -> bool:
        """Bind telegram_id to controller record by username if missing."""
        if not username:
            return False

        uname = username.strip().lstrip("@").lower()
        if not uname:
            return False

        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                UPDATE controllers
                SET telegram_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE LOWER(username) = ?
                  AND is_active = 1
                  AND (telegram_id IS NULL OR telegram_id = ?)
                """,
                (telegram_id, uname, telegram_id),
            )
            await db.commit()
            return (cur.rowcount or 0) > 0

    async def get_controller_by_id(self, controller_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM controllers WHERE id = ?", (controller_id,)
            ) as cur:
                row = await cur.fetchone()
                return self._parse_controller(row) if row else None

    async def update_controller(self, controller_id: int, **kwargs: Any) -> bool:
        """Update specific fields of a controller. Returns True if updated."""
        _allowed = {
            "username", "name", "birth_date", "phone", "specializations", "experience_types",
            "rating", "location", "preferred_areas", "languages", "is_active",
        }
        _json_fields = {"specializations", "experience_types", "preferred_areas", "languages"}

        updates: Dict[str, Any] = {}
        for key, value in kwargs.items():
            if key not in _allowed:
                continue
            if key in _json_fields and isinstance(value, list):
                updates[key] = json.dumps(value)
            else:
                updates[key] = value

        if not updates:
            return False

        updates["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [controller_id]

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE controllers SET {set_clause} WHERE id = ?", values
            )
            await db.commit()
        return True

    async def search_controllers(
        self,
        specializations: Optional[List[str]] = None,
        min_rating: float = 0.0,
        experience_types: Optional[List[str]] = None,
        location: Optional[str] = None,
        areas: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        available_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Search controllers with filters. Returns (results, total_count)."""
        conditions: List[str] = ["c.is_active = 1"]
        params: List[Any] = []

        if specializations:
            placeholders = []
            for spec in specializations:
                placeholders.append("c.specializations LIKE ?")
                params.append(f'%"{spec}"%')
            conditions.append(f"({' OR '.join(placeholders)})")

        if min_rating > 0:
            conditions.append("c.rating >= ?")
            params.append(min_rating)

        if experience_types:
            placeholders = []
            for exp in experience_types:
                placeholders.append("c.experience_types LIKE ?")
                params.append(f'%"{exp}"%')
            conditions.append(f"({' OR '.join(placeholders)})")

        if location:
            conditions.append("c.location LIKE ?")
            params.append(f"%{location}%")

        if areas:
            placeholders = []
            for area in areas:
                placeholders.append("c.preferred_areas LIKE ?")
                params.append(f'%"{area}"%')
            conditions.append(f"({' OR '.join(placeholders)})")

        if languages:
            placeholders = []
            for lang in languages:
                placeholders.append("c.languages LIKE ?")
                params.append(f'%"{lang}"%')
            conditions.append(f"({' OR '.join(placeholders)})")

        if available_date:
            conditions.append("""
                c.id NOT IN (
                    SELECT inv.controller_id
                    FROM invitations inv
                    JOIN events ev ON inv.event_id = ev.id
                    WHERE ev.event_date = ? AND inv.status = 'accepted'
                )
            """)
            params.append(available_date)

        where = " AND ".join(conditions)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                f"SELECT COUNT(*) FROM controllers c WHERE {where}", params
            ) as cur:
                total = (await cur.fetchone())[0]  # type: ignore[index]

            async with db.execute(
                f"""SELECT c.* FROM controllers c
                    WHERE {where}
                    ORDER BY c.rating DESC, c.name ASC
                    LIMIT ? OFFSET ?""",
                params + [limit, offset],
            ) as cur:
                rows = await cur.fetchall()
                controllers = [self._parse_controller(row) for row in rows]

        return controllers, total

    async def get_controller_count(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM controllers WHERE is_active = 1"
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else 0

    async def get_controller_ids(
        self,
        specializations: Optional[List[str]] = None,
        min_rating: float = 0.0,
        experience_types: Optional[List[str]] = None,
        location: Optional[str] = None,
        areas: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        available_date: Optional[str] = None,
    ) -> List[int]:
        """Return only the IDs of active controllers matching the given filters.

        Lighter alternative to :meth:`search_controllers` when full records are
        not needed (e.g. 'select all' and random-pick flows).
        """
        conditions: List[str] = ["c.is_active = 1"]
        params: List[Any] = []

        if specializations:
            placeholders = [f"c.specializations LIKE ?" for _ in specializations]
            params.extend(f'%"{s}"%' for s in specializations)
            conditions.append(f"({' OR '.join(placeholders)})")

        if min_rating > 0:
            conditions.append("c.rating >= ?")
            params.append(min_rating)

        if experience_types:
            placeholders = [f"c.experience_types LIKE ?" for _ in experience_types]
            params.extend(f'%"{e}"%' for e in experience_types)
            conditions.append(f"({' OR '.join(placeholders)})")

        if location:
            conditions.append("c.location LIKE ?")
            params.append(f"%{location}%")

        if areas:
            placeholders = [f"c.preferred_areas LIKE ?" for _ in areas]
            params.extend(f'%"{a}"%' for a in areas)
            conditions.append(f"({' OR '.join(placeholders)})")

        if languages:
            placeholders = [f"c.languages LIKE ?" for _ in languages]
            params.extend(f'%"{l}"%' for l in languages)
            conditions.append(f"({' OR '.join(placeholders)})")

        if available_date:
            conditions.append("""
                c.id NOT IN (
                    SELECT inv.controller_id
                    FROM invitations inv
                    JOIN events ev ON inv.event_id = ev.id
                    WHERE ev.event_date = ? AND inv.status = 'accepted'
                )
            """)
            params.append(available_date)

        where = " AND ".join(conditions)
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                f"SELECT c.id FROM controllers c WHERE {where} ORDER BY c.rating DESC, c.name ASC",
                params,
            ) as cur:
                return [row[0] for row in await cur.fetchall()]

    # ------------------------------------------------------------------
    # Event operations
    # ------------------------------------------------------------------

    async def create_event(
        self,
        title: str,
        event_date: str,
        location: str,
        event_time: Optional[str] = None,
        description: Optional[str] = None,
        rate: Optional[str] = None,
        dress_code: Optional[str] = None,
        task_description: Optional[str] = None,
        created_by: Optional[int] = None,
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO events
                    (title, event_date, location, event_time,
                     description, rate, dress_code, task_description, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (title, event_date, location, event_time, description,
                 rate, dress_code, task_description, created_by),
            )
            await db.commit()
            return cur.lastrowid  # type: ignore[return-value]

    async def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM events WHERE id = ?", (event_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def update_event_status(self, event_id: int, status: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE events SET status = ? WHERE id = ?",
                (status, event_id),
            )
            await db.commit()

    # ------------------------------------------------------------------
    # Invitation operations
    # ------------------------------------------------------------------

    async def create_invitation(self, event_id: int, controller_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "INSERT INTO invitations (event_id, controller_id) VALUES (?, ?)",
                (event_id, controller_id),
            )
            await db.commit()
            return cur.lastrowid  # type: ignore[return-value]

    async def create_event_with_invitations(
        self,
        *,
        title: str,
        event_date: str,
        location: str,
        event_time: Optional[str] = None,
        description: Optional[str] = None,
        rate: Optional[str] = None,
        dress_code: Optional[str] = None,
        task_description: Optional[str] = None,
        created_by: Optional[int],
        controller_ids: List[int],
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """Atomically create an event and invitation rows (single transaction).

        Mirrors the previous handler behaviour: invitations are only inserted
        for controllers that currently have a non-null ``telegram_id`` (same as
        skipping before insert in the old loop).

        Returns ``(event_id, delivery_rows)`` where each delivery row contains
        ``invitation_id``, ``telegram_id``, and ``controller_id``.
        """
        delivery: List[Dict[str, Any]] = []
        async with self.connection() as db:
            cur = await db.execute(
                """
                INSERT INTO events
                    (title, event_date, location, event_time,
                     description, rate, dress_code, task_description, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    event_date,
                    location,
                    event_time,
                    description,
                    rate,
                    dress_code,
                    task_description,
                    created_by,
                ),
            )
            event_id = int(cur.lastrowid)

            for cid in controller_ids:
                async with db.execute(
                    "SELECT telegram_id FROM controllers WHERE id = ?",
                    (cid,),
                ) as cursor:
                    row = await cursor.fetchone()
                if not row or row[0] is None:
                    continue
                tg_id = int(row[0])
                cur = await db.execute(
                    "INSERT INTO invitations (event_id, controller_id) VALUES (?, ?)",
                    (event_id, cid),
                )
                inv_id = int(cur.lastrowid)
                delivery.append(
                    {
                        "invitation_id": inv_id,
                        "telegram_id": tg_id,
                        "controller_id": cid,
                    }
                )
            await db.commit()
        return event_id, delivery

    async def get_invitation(self, invitation_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM invitations WHERE id = ?", (invitation_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_invitation_with_details(self, invitation_id: int) -> Optional[Dict[str, Any]]:
        """Return invitation joined with event and controller info."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT i.*,
                       e.title AS event_title, e.event_date, e.event_time,
                       e.location AS event_location, e.rate, e.dress_code,
                       e.task_description,
                       c.name AS controller_name, c.telegram_id
                FROM invitations i
                JOIN events e      ON i.event_id      = e.id
                JOIN controllers c ON i.controller_id  = c.id
                WHERE i.id = ?
                """,
                (invitation_id,),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def update_invitation_status(
        self,
        invitation_id: int,
        status: str,
        decline_reason: Optional[str] = None,
        decline_comment: Optional[str] = None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE invitations SET
                    status          = ?,
                    decline_reason  = COALESCE(?, decline_reason),
                    decline_comment = COALESCE(?, decline_comment),
                    responded_at    = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, decline_reason, decline_comment, invitation_id),
            )
            await db.commit()

    async def mark_reminder_sent(self, invitation_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE invitations SET reminder_sent = 1 WHERE id = ?",
                (invitation_id,),
            )
            await db.commit()

    async def get_pending_reminders(self, hours: int = 6) -> List[Dict[str, Any]]:
        """Get 'thinking' invitations older than *hours* that haven't been reminded."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT i.*, c.telegram_id, c.name AS controller_name,
                       e.title AS event_title, e.event_date, e.event_time
                FROM invitations i
                JOIN controllers c ON i.controller_id = c.id
                JOIN events e      ON i.event_id      = e.id
                WHERE i.status = 'thinking'
                  AND i.reminder_sent = 0
                  AND datetime(i.responded_at, '+' || ? || ' hours') <= datetime('now')
                """,
                (hours,),
            ) as cur:
                return [dict(row) for row in await cur.fetchall()]

    async def get_invitation_stats(self, event_id: int) -> Dict[str, int]:
        """Return {status: count} for all invitations of an event."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT status, COUNT(*) FROM invitations WHERE event_id = ? GROUP BY status",
                (event_id,),
            ) as cur:
                return {row[0]: row[1] for row in await cur.fetchall()}

    # ------------------------------------------------------------------
    # Event-history operations
    # ------------------------------------------------------------------

    async def add_event_history(
        self,
        controller_id: int,
        event_id: int,
        role: Optional[str] = None,
        admin_rating: Optional[float] = None,
        admin_comment: Optional[str] = None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO event_history
                    (controller_id, event_id, role, admin_rating, admin_comment)
                VALUES (?, ?, ?, ?, ?)
                """,
                (controller_id, event_id, role, admin_rating, admin_comment),
            )
            await db.commit()

    async def get_controller_history(self, controller_id: int) -> List[Dict[str, Any]]:
        """Return participation history (most recent first, max 20)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT eh.*, e.title, e.event_date, e.location
                FROM event_history eh
                JOIN events e ON eh.event_id = e.id
                WHERE eh.controller_id = ?
                ORDER BY eh.completed_at DESC
                LIMIT 20
                """,
                (controller_id,),
            ) as cur:
                return [dict(row) for row in await cur.fetchall()]

    async def get_controller_invitations(self, controller_id: int) -> List[Dict[str, Any]]:
        """Return all invitations for a controller (most recent first, max 20)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT i.*, e.title, e.event_date, e.event_time, e.location
                FROM invitations i
                JOIN events e ON i.event_id = e.id
                WHERE i.controller_id = ?
                ORDER BY i.sent_at DESC
                LIMIT 20
                """,
                (controller_id,),
            ) as cur:
                return [dict(row) for row in await cur.fetchall()]

    # ------------------------------------------------------------------
    # Staff application operations
    # ------------------------------------------------------------------

    async def create_staff_application(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        full_name: str,
        birth_date: Optional[str],
        phone: Optional[str],
        specializations: Optional[List[str]] = None,
        experience_types: Optional[List[str]] = None,
        preferred_areas: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO staff_applications
                    (user_id, username, first_name, last_name, full_name, birth_date, phone,
                     specializations, experience_types, preferred_areas, languages)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    username,
                    first_name,
                    last_name,
                    full_name,
                    birth_date,
                    phone,
                    json.dumps(specializations or []),
                    json.dumps(experience_types or []),
                    json.dumps(preferred_areas or []),
                    json.dumps(languages or []),
                ),
            )
            await db.commit()
            return cur.lastrowid  # type: ignore[return-value]

    async def get_active_staff_application_by_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM staff_applications
                WHERE user_id = ? AND status IN ('new', 'in_review')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id,),
            ) as cur:
                row = await cur.fetchone()
                return self._parse_staff_application(row) if row else None

    async def list_staff_applications(self, limit: int = 30) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM staff_applications
                WHERE status IN ('new', 'in_review')
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
                return [self._parse_staff_application(row) for row in rows]

    async def get_staff_application(self, application_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM staff_applications WHERE id = ?",
                (application_id,),
            ) as cur:
                row = await cur.fetchone()
                return self._parse_staff_application(row) if row else None

    async def set_staff_application_status(self, application_id: int, status: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE staff_applications
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, application_id),
            )
            await db.commit()

    async def add_staff_application_message(
        self,
        application_id: int,
        sender_id: int,
        sender_role: str,
        message_text: str,
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO staff_application_messages
                    (application_id, sender_id, sender_role, message_text)
                VALUES (?, ?, ?, ?)
                """,
                (application_id, sender_id, sender_role, message_text),
            )
            await db.execute(
                """
                UPDATE staff_applications
                SET status = CASE WHEN status = 'new' THEN 'in_review' ELSE status END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (application_id,),
            )
            await db.commit()
            return cur.lastrowid  # type: ignore[return-value]

    async def get_staff_application_messages(self, application_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM staff_application_messages
                WHERE application_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (application_id, limit),
            ) as cur:
                return [dict(row) for row in await cur.fetchall()]

    async def approve_staff_application(self, application_id: int) -> Optional[int]:
        """Convert staff application into controller and close the application."""
        app = await self.get_staff_application(application_id)
        if not app:
            return None

        from database.models import WorkArea

        areas = app.get("preferred_areas", []) or []
        area_labels: list[str] = []
        for val in areas:
            try:
                area_labels.append(WorkArea(val).label)
            except ValueError:
                area_labels.append(str(val))

        location = None
        if area_labels:
            location = ", ".join(area_labels)

        ctrl_id = await self.add_controller(
            telegram_id=app.get("user_id"),
            username=app.get("username"),
            name=app.get("full_name", ""),
            birth_date=app.get("birth_date"),
            phone=app.get("phone"),
            specializations=app.get("specializations", []),
            experience_types=app.get("experience_types", []),
            rating=0.0,
            location=location,
            preferred_areas=areas,
            languages=app.get("languages", []),
        )
        await self.set_staff_application_status(application_id, "closed")
        return ctrl_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_controller(row: Any) -> Dict[str, Any]:
        """Convert a database Row to a dict, deserialising JSON fields."""
        d = dict(row)
        for field in ("specializations", "experience_types", "preferred_areas", "languages"):
            raw = d.get(field)
            if raw:
                try:
                    d[field] = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    d[field] = []
            else:
                d[field] = []
        return d

    @staticmethod
    def _parse_staff_application(row: Any) -> Dict[str, Any]:
        d = dict(row)
        for field in ("specializations", "experience_types", "preferred_areas", "languages"):
            raw = d.get(field)
            if raw:
                try:
                    d[field] = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    d[field] = []
            else:
                d[field] = []
        return d
