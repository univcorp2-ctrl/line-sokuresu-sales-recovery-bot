import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from .config import Settings
from .schemas import Classification, Lead, MessageRecord, TenantConfig

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    industry TEXT NOT NULL,
    service_url TEXT,
    reservation_url TEXT,
    document_url TEXT,
    phone TEXT,
    faq TEXT,
    prohibited_text TEXT,
    notification_target TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    line_user_id TEXT NOT NULL,
    display_name TEXT,
    last_message TEXT NOT NULL,
    category TEXT NOT NULL,
    score INTEGER NOT NULL,
    status TEXT NOT NULL,
    followup_due_at TEXT,
    second_followup_due_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, line_user_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    lead_id TEXT NOT NULL,
    line_user_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    text TEXT NOT NULL,
    category TEXT,
    score INTEGER,
    raw_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS followups (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    line_user_id TEXT NOT NULL,
    stage INTEGER NOT NULL,
    due_at TEXT NOT NULL,
    sent_at TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(lead_id, stage)
);
"""


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


class Repository:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db_path = settings.sqlite_path
        self.init()

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()
        self.ensure_demo_tenant()

    def ensure_demo_tenant(self) -> None:
        demo = TenantConfig(
            id="demo",
            company_name="デモ不動産",
            industry="property",
            service_url="https://example.com",
            reservation_url="https://example.com/reserve",
            document_url="https://example.com/docs",
            phone="03-0000-0000",
            faq="営業時間は10:00-18:00。内見は前日までに予約。",
            prohibited_text="確定的な融資承認、値引き保証、法的断定はしない。",
            notification_target="owner@example.com",
        )
        self.upsert_tenant(demo)

    def upsert_tenant(self, tenant: TenantConfig) -> TenantConfig:
        now = iso(utcnow())
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM tenants WHERE id = ?", (tenant.id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE tenants SET company_name=?, industry=?, service_url=?, reservation_url=?,
                        document_url=?, phone=?, faq=?, prohibited_text=?, notification_target=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        tenant.company_name,
                        tenant.industry,
                        tenant.service_url,
                        tenant.reservation_url,
                        tenant.document_url,
                        tenant.phone,
                        tenant.faq,
                        tenant.prohibited_text,
                        tenant.notification_target,
                        now,
                        tenant.id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO tenants (
                        id, company_name, industry, service_url, reservation_url, document_url, phone,
                        faq, prohibited_text, notification_target, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tenant.id,
                        tenant.company_name,
                        tenant.industry,
                        tenant.service_url,
                        tenant.reservation_url,
                        tenant.document_url,
                        tenant.phone,
                        tenant.faq,
                        tenant.prohibited_text,
                        tenant.notification_target,
                        now,
                        now,
                    ),
                )
            conn.commit()
        return tenant

    def get_tenant(self, tenant_id: str | None) -> TenantConfig:
        lookup_id = tenant_id or self.settings.default_tenant_id
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM tenants WHERE id = ?", (lookup_id,)).fetchone()
            if not row and lookup_id != self.settings.default_tenant_id:
                row = conn.execute(
                    "SELECT * FROM tenants WHERE id = ?", (self.settings.default_tenant_id,)
                ).fetchone()
        if not row:
            self.ensure_demo_tenant()
            return self.get_tenant(self.settings.default_tenant_id)
        return TenantConfig(
            id=row["id"],
            company_name=row["company_name"],
            industry=row["industry"],
            service_url=row["service_url"],
            reservation_url=row["reservation_url"],
            document_url=row["document_url"],
            phone=row["phone"],
            faq=row["faq"],
            prohibited_text=row["prohibited_text"],
            notification_target=row["notification_target"],
        )

    def upsert_lead(self, tenant: TenantConfig, line_user_id: str, text: str, classification: Classification, display_name: str | None = None) -> Lead:
        now_dt = utcnow()
        now = iso(now_dt)
        followup_due = now_dt + timedelta(hours=self.settings.followup_after_hours)
        second_followup_due = now_dt + timedelta(hours=self.settings.followup_second_after_hours)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM leads WHERE tenant_id = ? AND line_user_id = ?",
                (tenant.id, line_user_id),
            ).fetchone()
            if row:
                lead_id = row["id"]
                created_at = row["created_at"]
                conn.execute(
                    """
                    UPDATE leads SET display_name=?, last_message=?, category=?, score=?, status=?,
                        followup_due_at=?, second_followup_due_at=?, updated_at=?
                    WHERE id=?
                    """,
                    (display_name, text, classification.category, classification.score, "open", iso(followup_due), iso(second_followup_due), now, lead_id),
                )
            else:
                lead_id = str(uuid4())
                created_at = now
                conn.execute(
                    """
                    INSERT INTO leads (
                        id, tenant_id, line_user_id, display_name, last_message, category, score,
                        status, followup_due_at, second_followup_due_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (lead_id, tenant.id, line_user_id, display_name, text, classification.category, classification.score, "open", iso(followup_due), iso(second_followup_due), created_at, now),
                )
            self._ensure_followup_rows(conn, lead_id, tenant.id, line_user_id, followup_due, second_followup_due)
            conn.commit()
        return Lead(
            id=lead_id,
            tenant_id=tenant.id,
            line_user_id=line_user_id,
            display_name=display_name,
            last_message=text,
            category=classification.category,
            score=classification.score,
            status="open",
            followup_due_at=followup_due,
            second_followup_due_at=second_followup_due,
            created_at=parse_dt(created_at) or now_dt,
            updated_at=now_dt,
        )

    def _ensure_followup_rows(self, conn: sqlite3.Connection, lead_id: str, tenant_id: str, line_user_id: str, first_due: datetime, second_due: datetime) -> None:
        now = iso(utcnow())
        for stage, due in [(1, first_due), (2, second_due)]:
            conn.execute(
                """
                INSERT INTO followups (id, lead_id, tenant_id, line_user_id, stage, due_at, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lead_id, stage) DO UPDATE SET due_at=excluded.due_at, status='pending'
                """,
                (str(uuid4()), lead_id, tenant_id, line_user_id, stage, iso(due), "pending", now),
            )

    def save_message(self, message: MessageRecord) -> MessageRecord:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (
                    id, tenant_id, lead_id, line_user_id, direction, text, category, score, raw_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (message.id, message.tenant_id, message.lead_id, message.line_user_id, message.direction, message.text, message.category, message.score, json.dumps(message.raw_json, ensure_ascii=False) if message.raw_json else None, iso(message.created_at)),
            )
            conn.commit()
        return message

    def list_leads(self, tenant_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT * FROM leads"
        params: list[Any] = []
        if tenant_id:
            sql += " WHERE tenant_id = ?"
            params.append(tenant_id)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def due_followups(self, now: datetime | None = None, limit: int = 100) -> Iterable[dict[str, Any]]:
        now_iso = iso(now or utcnow())
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT f.*, l.last_message, l.category, l.score, t.company_name, t.reservation_url, t.industry
                FROM followups f
                JOIN leads l ON l.id = f.lead_id
                JOIN tenants t ON t.id = f.tenant_id
                WHERE f.status = 'pending' AND f.due_at <= ?
                ORDER BY f.due_at ASC
                LIMIT ?
                """,
                (now_iso, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_followup_sent(self, followup_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE followups SET status = 'sent', sent_at = ? WHERE id = ?",
                (iso(utcnow()), followup_id),
            )
            conn.commit()
