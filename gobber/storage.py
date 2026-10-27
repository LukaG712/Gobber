"""SQLite storage backend for Gobber."""

import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from gobber.models import (
    AnalyticsEvent,
    CacheEntry,
    FeatureFlag,
    Role,
    UserRole,
    Webhook,
    WebhookDelivery,
)


def _default_db_path() -> str:
    """Return a writable default database path.

    Tries /app/data/gobber.db first, then falls back to a temp directory.
    """
    default = "/app/data/gobber.db"
    try:
        Path(default).parent.mkdir(parents=True, exist_ok=True)
        return default
    except (PermissionError, OSError):
        return os.path.join(tempfile.gettempdir(), "gobber.db")


class Storage:
    """SQLite-backed storage for all Gobber data."""

    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or _default_db_path())
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS webhooks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    events TEXT NOT NULL,
                    secret TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    delivery_count INTEGER DEFAULT 0,
                    last_delivery_at TEXT
                );

                CREATE TABLE IF NOT EXISTS webhook_deliveries (
                    id TEXT PRIMARY KEY,
                    webhook_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    response_status INTEGER,
                    error_message TEXT,
                    FOREIGN KEY (webhook_id) REFERENCES webhooks(id)
                );

                CREATE TABLE IF NOT EXISTS analytics_events (
                    id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    properties TEXT NOT NULL,
                    service TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS feature_flags (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    is_enabled INTEGER DEFAULT 0,
                    description TEXT,
                    targeting TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cache_entries (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    ttl_seconds INTEGER,
                    created_at TEXT NOT NULL,
                    expires_at TEXT
                );

                CREATE TABLE IF NOT EXISTS roles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    permissions TEXT NOT NULL,
                    description TEXT
                );

                CREATE TABLE IF NOT EXISTS user_roles (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    FOREIGN KEY (role_id) REFERENCES roles(id)
                );

                CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook ON webhook_deliveries(webhook_id);
                CREATE INDEX IF NOT EXISTS idx_analytics_events_type ON analytics_events(event_type);
                CREATE INDEX IF NOT EXISTS idx_analytics_events_created ON analytics_events(created_at);

                -- Knowledge Graph tables
                CREATE TABLE IF NOT EXISTS kg_notes (
                    id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    links TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kg_note_links (
                    source_note_id TEXT NOT NULL,
                    target_note_id TEXT NOT NULL,
                    PRIMARY KEY (source_note_id, target_note_id),
                    FOREIGN KEY (source_note_id) REFERENCES kg_notes(id),
                    FOREIGN KEY (target_note_id) REFERENCES kg_notes(id)
                );

                CREATE TABLE IF NOT EXISTS kg_note_embeddings (
                    note_id TEXT PRIMARY KEY,
                    embedding TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (note_id) REFERENCES kg_notes(id)
                );

                CREATE INDEX IF NOT EXISTS idx_kg_notes_title ON kg_notes(title);
                CREATE INDEX IF NOT EXISTS idx_kg_note_links_source ON kg_note_links(source_note_id);
                CREATE INDEX IF NOT EXISTS idx_kg_note_links_target ON kg_note_links(target_note_id);
            """)

    # ─── Webhooks ─────────────────────────────────────────────

    def create_webhook(self, webhook: Webhook) -> Webhook:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO webhooks (id, name, url, events, secret, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(webhook.id),
                    webhook.name,
                    webhook.url,
                    json.dumps(webhook.events),
                    webhook.secret,
                    int(webhook.is_active),
                    webhook.created_at.isoformat(),
                ),
            )
        return webhook

    def get_webhook(self, webhook_id: str) -> Webhook | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM webhooks WHERE id = ?", (webhook_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_webhook(row)

    def list_webhooks(self, active_only: bool = False) -> list[Webhook]:
        with self._get_conn() as conn:
            if active_only:
                rows = conn.execute(
                    "SELECT * FROM webhooks WHERE is_active = 1 ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM webhooks ORDER BY created_at DESC"
                ).fetchall()
            return [self._row_to_webhook(r) for r in rows]

    def update_webhook(self, webhook_id: str, **kwargs: Any) -> Webhook | None:
        if not kwargs:
            return self.get_webhook(webhook_id)
        # Whitelist allowed columns to prevent SQL injection
        allowed_columns = {"name", "url", "events", "secret", "is_active"}
        sets = []
        values = []
        for key, value in kwargs.items():
            if key not in allowed_columns:
                continue
            if key in ("events",):
                value = json.dumps(value)
            elif key in ("is_active",):
                value = int(value)
            sets.append(f"{key} = ?")
            values.append(value)
        if not sets:
            return self.get_webhook(webhook_id)
        values.append(webhook_id)
        with self._get_conn() as conn:
            conn.execute(f"UPDATE webhooks SET {', '.join(sets)} WHERE id = ?", values)
        return self.get_webhook(webhook_id)

    def delete_webhook(self, webhook_id: str) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
            return cursor.rowcount > 0

    def _row_to_webhook(self, row: sqlite3.Row) -> Webhook:
        return Webhook(
            id=UUID(row["id"]),
            name=row["name"],
            url=row["url"],
            events=json.loads(row["events"]),
            secret=row["secret"],
            is_active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ─── Webhook Deliveries ───────────────────────────────────

    def create_delivery(self, delivery: WebhookDelivery) -> WebhookDelivery:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO webhook_deliveries (id, webhook_id, event, payload, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(delivery.id),
                    str(delivery.webhook_id),
                    delivery.event,
                    json.dumps(delivery.payload),
                    delivery.status.value,
                    delivery.created_at.isoformat(),
                ),
            )
        return delivery

    def list_deliveries(
        self, webhook_id: str | None = None, limit: int = 50
    ) -> list[WebhookDelivery]:
        with self._get_conn() as conn:
            if webhook_id:
                rows = conn.execute(
                    "SELECT * FROM webhook_deliveries WHERE webhook_id = ? ORDER BY created_at DESC LIMIT ?",
                    (webhook_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM webhook_deliveries ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [self._row_to_delivery(r) for r in rows]

    def _row_to_delivery(self, row: sqlite3.Row) -> WebhookDelivery:
        from gobber.models import WebhookStatus

        return WebhookDelivery(
            id=UUID(row["id"]),
            webhook_id=UUID(row["webhook_id"]),
            event=row["event"],
            payload=json.loads(row["payload"]),
            status=WebhookStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ─── Analytics ────────────────────────────────────────────

    def record_event(self, event: AnalyticsEvent) -> AnalyticsEvent:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO analytics_events (id, event_type, properties, service, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    str(event.id),
                    event.event_type,
                    json.dumps(event.properties),
                    event.service,
                    event.created_at.isoformat(),
                ),
            )
        return event

    def query_events(
        self,
        event_type: str | None = None,
        service: str | None = None,
        limit: int = 100,
    ) -> list[AnalyticsEvent]:
        with self._get_conn() as conn:
            query = "SELECT * FROM analytics_events WHERE 1=1"
            params = []
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type)
            if service:
                query += " AND service = ?"
                params.append(service)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_event(r) for r in rows]

    def _row_to_event(self, row: sqlite3.Row) -> AnalyticsEvent:
        return AnalyticsEvent(
            id=UUID(row["id"]),
            event_type=row["event_type"],
            properties=json.loads(row["properties"]),
            service=row["service"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ─── Feature Flags ────────────────────────────────────────

    def create_feature_flag(self, flag: FeatureFlag) -> FeatureFlag:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO feature_flags (id, name, is_enabled, description, targeting, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(flag.id),
                    flag.name,
                    int(flag.is_enabled),
                    flag.description,
                    json.dumps(flag.targeting),
                    flag.created_at.isoformat(),
                ),
            )
        return flag

    def get_feature_flag(self, name: str) -> FeatureFlag | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM feature_flags WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_flag(row)

    def list_feature_flags(self) -> list[FeatureFlag]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM feature_flags ORDER BY name").fetchall()
            return [self._row_to_flag(r) for r in rows]

    def update_feature_flag(self, name: str, **kwargs: Any) -> FeatureFlag | None:
        if not kwargs:
            return self.get_feature_flag(name)
        # Whitelist allowed columns to prevent SQL injection
        allowed_columns = {"is_enabled", "description", "targeting"}
        sets = []
        values = []
        for key, value in kwargs.items():
            if key not in allowed_columns:
                continue
            if key == "targeting":
                value = json.dumps(value)
            elif key == "is_enabled":
                value = int(value)
            sets.append(f"{key} = ?")
            values.append(value)
        if not sets:
            return self.get_feature_flag(name)
        values.append(name)
        with self._get_conn() as conn:
            conn.execute(
                f"UPDATE feature_flags SET {', '.join(sets)} WHERE name = ?", values
            )
        return self.get_feature_flag(name)

    def delete_feature_flag(self, name: str) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM feature_flags WHERE name = ?", (name,))
            return cursor.rowcount > 0

    def _row_to_flag(self, row: sqlite3.Row) -> FeatureFlag:
        return FeatureFlag(
            id=UUID(row["id"]),
            name=row["name"],
            is_enabled=bool(row["is_enabled"]),
            description=row["description"],
            targeting=json.loads(row["targeting"]) if row["targeting"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ─── Cache ────────────────────────────────────────────────

    def set_cache(self, entry: CacheEntry) -> CacheEntry:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache_entries (key, value, ttl_seconds, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (
                    entry.key,
                    json.dumps(entry.value),
                    entry.ttl_seconds,
                    entry.created_at.isoformat(),
                    entry.expires_at.isoformat() if entry.expires_at else None,
                ),
            )
        return entry

    def get_cache(self, key: str) -> CacheEntry | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM cache_entries WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            entry = self._row_to_cache(row)
            if entry.is_expired():
                self.delete_cache(key)
                return None
            return entry

    def delete_cache(self, key: str) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
            return cursor.rowcount > 0

    def _row_to_cache(self, row: sqlite3.Row) -> CacheEntry:
        return CacheEntry(
            key=row["key"],
            value=json.loads(row["value"]),
            ttl_seconds=row["ttl_seconds"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ─── RBAC ─────────────────────────────────────────────────

    def create_role(self, role: Role) -> Role:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO roles (id, name, permissions, description) VALUES (?, ?, ?, ?)",
                (
                    str(role.id),
                    role.name,
                    json.dumps(role.permissions),
                    role.description,
                ),
            )
        return role

    def get_role(self, role_id: str) -> Role | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM roles WHERE id = ?", (role_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_role(row)

    def list_roles(self) -> list[Role]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM roles ORDER BY name").fetchall()
            return [self._row_to_role(r) for r in rows]

    def delete_role(self, role_id: str) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM roles WHERE id = ?", (role_id,))
            return cursor.rowcount > 0

    def _row_to_role(self, row: sqlite3.Row) -> Role:
        return Role(
            id=UUID(row["id"]),
            name=row["name"],
            permissions=json.loads(row["permissions"]),
            description=row["description"],
        )

    def assign_role(self, user_role: UserRole) -> UserRole:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO user_roles (id, user_id, role_id) VALUES (?, ?, ?)",
                (str(user_role.id), user_role.user_id, str(user_role.role_id)),
            )
        return user_role

    def get_user_roles(self, user_id: str) -> list[Role]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT r.* FROM roles r
                   INNER JOIN user_roles ur ON r.id = ur.role_id
                   WHERE ur.user_id = ?""",
                (user_id,),
            ).fetchall()
            return [self._row_to_role(r) for r in rows]

    def revoke_role(self, user_id: str, role_id: str) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM user_roles WHERE user_id = ? AND role_id = ?",
                (user_id, role_id),
            )
            return cursor.rowcount > 0
