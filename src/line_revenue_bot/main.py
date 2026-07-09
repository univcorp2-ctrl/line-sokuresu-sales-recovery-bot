import base64
import hashlib
import hmac
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    env: str = "development"
    app_name: str = "LINE即レス売上回収Bot"
    database_url: str = "sqlite:///./data/app.db"
    line_channel_secret: str | None = None
    line_channel_access_token: str | None = None
    line_signature_verification: bool = True
    line_reply_dry_run: bool = True
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    admin_api_token: str = Field(default="dev-token-change-me", min_length=8)
    admin_webhook_url: str | None = None
    public_base_url: str = "http://localhost:8000"
    default_tenant_id: str = "demo"
    followup_after_hours: int = 24
    followup_second_after_hours: int = 72
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BOT_", extra="ignore")

    @property
    def sqlite_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            msg = "Only sqlite:/// URLs are supported in this starter."
            raise ValueError(msg)
        return Path(self.database_url.removeprefix("sqlite:///"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


class TenantConfig(BaseModel):
    id: str = Field(default="demo", min_length=1, max_length=80)
    company_name: str = "デモ不動産"
    industry: str = "property"
    service_url: str | None = None
    reservation_url: str | None = "https://example.com/reserve"
    document_url: str | None = "https://example.com/docs"
    phone: str | None = "03-0000-0000"
    faq: str | None = None
    prohibited_text: str | None = "融資承認保証、値引き保証、契約成立保証"
    notification_target: str | None = None

    @field_validator("id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        return value.strip().replace(" ", "-")


class Classification(BaseModel):
    category: str
    score: int = Field(ge=0, le=100)
    priority: str
    reason: str


class MessageRecord(BaseModel):
    tenant_id: str
    lead_id: str
    line_user_id: str
    direction: str
    text: str
    category: str | None = None
    score: int | None = None
    raw_json: dict[str, Any] | None = None
    created_at: datetime


class IntakeRequest(TenantConfig):
    pass


class TestMessageRequest(BaseModel):
    tenant_id: str = "demo"
    user_id: str = "demo-user"
    text: str = Field(min_length=1, max_length=3000)


class TestMessageResponse(BaseModel):
    tenant: TenantConfig
    classification: Classification
    reply: str


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
  id TEXT PRIMARY KEY, company_name TEXT NOT NULL, industry TEXT NOT NULL, service_url TEXT,
  reservation_url TEXT, document_url TEXT, phone TEXT, faq TEXT, prohibited_text TEXT,
  notification_target TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS leads (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, line_user_id TEXT NOT NULL, last_message TEXT NOT NULL,
  category TEXT NOT NULL, score INTEGER NOT NULL, status TEXT NOT NULL, followup_due_at TEXT,
  second_followup_due_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, line_user_id)
);
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, lead_id TEXT NOT NULL, line_user_id TEXT NOT NULL,
  direction TEXT NOT NULL, text TEXT NOT NULL, category TEXT, score INTEGER, raw_json TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS followups (
  id TEXT PRIMARY KEY, lead_id TEXT NOT NULL, tenant_id TEXT NOT NULL, line_user_id TEXT NOT NULL,
  stage INTEGER NOT NULL, due_at TEXT NOT NULL, sent_at TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(lead_id, stage)
);
"""


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
        self.upsert_tenant(TenantConfig(id="demo", faq="営業時間は10:00-18:00。内見は前日までに予約。"))

    def upsert_tenant(self, tenant: TenantConfig) -> TenantConfig:
        now = iso(utcnow())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO tenants VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET company_name=excluded.company_name, industry=excluded.industry,
                service_url=excluded.service_url, reservation_url=excluded.reservation_url,
                document_url=excluded.document_url, phone=excluded.phone, faq=excluded.faq,
                prohibited_text=excluded.prohibited_text, notification_target=excluded.notification_target, updated_at=excluded.updated_at
                """,
                (tenant.id, tenant.company_name, tenant.industry, tenant.service_url, tenant.reservation_url, tenant.document_url, tenant.phone, tenant.faq, tenant.prohibited_text, tenant.notification_target, now, now),
            )
            conn.commit()
        return tenant

    def get_tenant(self, tenant_id: str | None) -> TenantConfig:
        lookup_id = tenant_id or self.settings.default_tenant_id
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM tenants WHERE id = ?", (lookup_id,)).fetchone()
            if not row:
                row = conn.execute("SELECT * FROM tenants WHERE id = ?", (self.settings.default_tenant_id,)).fetchone()
        if not row:
            return TenantConfig()
        return TenantConfig(**{key: row[key] for key in row.keys() if key in TenantConfig.model_fields})

    def upsert_lead(self, tenant: TenantConfig, user_id: str, text: str, classification: Classification) -> str:
        now_dt = utcnow()
        now = iso(now_dt)
        first_due = iso(now_dt + timedelta(hours=self.settings.followup_after_hours))
        second_due = iso(now_dt + timedelta(hours=self.settings.followup_second_after_hours))
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM leads WHERE tenant_id=? AND line_user_id=?", (tenant.id, user_id)).fetchone()
            lead_id = row["id"] if row else str(uuid4())
            conn.execute(
                """
                INSERT INTO leads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, line_user_id) DO UPDATE SET last_message=excluded.last_message,
                category=excluded.category, score=excluded.score, status='open', followup_due_at=excluded.followup_due_at,
                second_followup_due_at=excluded.second_followup_due_at, updated_at=excluded.updated_at
                """,
                (lead_id, tenant.id, user_id, text, classification.category, classification.score, "open", first_due, second_due, now, now),
            )
            for stage, due in [(1, first_due), (2, second_due)]:
                conn.execute(
                    """
                    INSERT INTO followups VALUES (?, ?, ?, ?, ?, ?, NULL, 'pending', ?)
                    ON CONFLICT(lead_id, stage) DO UPDATE SET due_at=excluded.due_at, status='pending'
                    """,
                    (str(uuid4()), lead_id, tenant.id, user_id, stage, due, now),
                )
            conn.commit()
        return lead_id

    def save_message(self, message: MessageRecord) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid4()), message.tenant_id, message.lead_id, message.line_user_id, message.direction, message.text, message.category, message.score, json.dumps(message.raw_json, ensure_ascii=False) if message.raw_json else None, iso(message.created_at)),
            )
            conn.commit()

    def list_leads(self, tenant_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT * FROM leads"
        params: list[Any] = []
        if tenant_id:
            sql += " WHERE tenant_id=?"
            params.append(tenant_id)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def due_followups(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT f.*, t.company_name, t.reservation_url FROM followups f
                JOIN tenants t ON t.id=f.tenant_id WHERE f.status='pending' AND f.due_at <= ? ORDER BY f.due_at ASC LIMIT 100
                """,
                (iso(utcnow()),),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_followup_sent(self, followup_id: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE followups SET status='sent', sent_at=? WHERE id=?", (iso(utcnow()), followup_id))
            conn.commit()


INDUSTRY_KEYWORDS = {
    "property": {"内見希望": ["内見", "見学", "案内"], "資料請求": ["資料", "パンフレット", "図面"], "売却相談": ["売却", "査定"], "融資相談": ["ローン", "融資"], "物件問い合わせ": ["物件", "家賃", "価格"]},
    "salon": {"新規予約": ["予約", "空き", "カット", "カラー"], "予約変更": ["変更"], "キャンセル": ["キャンセル"], "料金質問": ["料金", "いくら"], "アクセス質問": ["場所", "アクセス"]},
    "generic": {"予約希望": ["予約", "相談", "面談"], "資料請求": ["資料"], "料金質問": ["料金", "費用"]},
}
URGENT = ["クレーム", "返金", "苦情", "緊急", "至急"]
HIGH = ["予約", "内見", "相談", "申し込み", "査定", "見積", "明日", "今日"]
MEDIUM = ["資料", "料金", "空き", "詳細", "電話", "リンク"]


def classify_message(text: str, industry: str = "generic") -> Classification:
    normalized = text.strip().lower()
    if any(word.lower() in normalized for word in URGENT):
        return Classification(category="クレーム・緊急", score=95, priority="urgent", reason="緊急語を検知")
    rules = INDUSTRY_KEYWORDS.get(industry, INDUSTRY_KEYWORDS["generic"])
    category = "その他"
    hits: list[str] = []
    for name, keywords in rules.items():
        hits = [word for word in keywords if word.lower() in normalized]
        if hits:
            category = name
            break
    score = 35 + (20 if category != "その他" else 0)
    score += 30 if any(word.lower() in normalized for word in HIGH) else 0
    score += 15 if any(word.lower() in normalized for word in MEDIUM) else 0
    score = min(score, 100)
    priority = "high" if score >= 80 else "normal" if score >= 55 else "low"
    return Classification(category=category, score=score, priority=priority, reason="キーワード分類" + (f": {', '.join(hits)}" if hits else ""))


class ReplyGenerator:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def generate(self, tenant: TenantConfig, text: str, classification: Classification) -> str:
        if self.settings.openai_api_key:
            try:
                return await self._openai_reply(tenant, text, classification)
            except Exception:
                pass
        return self._template_reply(tenant, classification)

    async def _openai_reply(self, tenant: TenantConfig, text: str, classification: Classification) -> str:
        prompt = f"{tenant.company_name}のLINE一次対応。分類={classification.category}。禁止={tenant.prohibited_text}。予約={tenant.reservation_url}。断定保証を避け、短く自然に次の行動へ誘導。問い合わせ: {text}"
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post("https://api.openai.com/v1/responses", headers={"Authorization": f"Bearer {self.settings.openai_api_key}"}, json={"model": self.settings.openai_model, "input": prompt, "max_output_tokens": 300})
            res.raise_for_status()
            data = res.json()
        return str(data.get("output_text") or self._template_reply(tenant, classification))[:900]

    def _template_reply(self, tenant: TenantConfig, classification: Classification) -> str:
        if classification.category == "クレーム・緊急":
            return f"お問い合わせありがとうございます。{tenant.company_name}です。内容を担当者が確認します。お名前と状況を簡単にお送りください。"
        if classification.category in {"内見希望", "新規予約", "予約希望", "無料相談"}:
            link = f"\n予約はこちら: {tenant.reservation_url}" if tenant.reservation_url else ""
            return f"お問い合わせありがとうございます。{tenant.company_name}です。希望日時を第2希望までお送りください。{link}\n担当者にも共有します。"
        if classification.category == "資料請求":
            link = f"\n資料はこちら: {tenant.document_url}" if tenant.document_url else ""
            return f"お問い合わせありがとうございます。{tenant.company_name}です。資料請求を受け付けました。ご希望のサービス・物件をお知らせください。{link}"
        link = f"\n相談予約: {tenant.reservation_url}" if tenant.reservation_url else ""
        return f"お問い合わせありがとうございます。{tenant.company_name}です。内容を確認しました。ご希望内容・時期・予算を簡単にお送りください。{link}"

    def followup_text(self, company_name: str, reservation_url: str | None, stage: int) -> str:
        link = f"\n予約・相談はこちら: {reservation_url}" if reservation_url else ""
        if stage == 1:
            return f"{company_name}です。昨日のお問い合わせについて、追加のご希望はありますか？{link}"
        return f"{company_name}です。先日のお問い合わせについて、まだご案内可能です。必要でしたらこのままご返信ください。{link}"


class LineClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def verify_signature(self, body: bytes, signature: str | None) -> bool:
        if not self.settings.line_signature_verification or not self.settings.line_channel_secret:
            return True
        if not signature:
            return False
        digest = hmac.new(self.settings.line_channel_secret.encode(), body, hashlib.sha256).digest()
        expected = base64.b64encode(digest).decode()
        return hmac.compare_digest(expected, signature)

    async def reply_text(self, reply_token: str, text: str) -> dict[str, Any]:
        if self.settings.line_reply_dry_run or not self.settings.line_channel_access_token:
            return {"dry_run": True, "reply_token": reply_token, "text": text}
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post("https://api.line.me/v2/bot/message/reply", headers={"Authorization": f"Bearer {self.settings.line_channel_access_token}"}, json={"replyToken": reply_token, "messages": [{"type": "text", "text": text[:5000]}]})
            res.raise_for_status()
            return {"ok": True}

    async def push_text(self, user_id: str, text: str) -> dict[str, Any]:
        if self.settings.line_reply_dry_run or not self.settings.line_channel_access_token:
            return {"dry_run": True, "user_id": user_id, "text": text}
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post("https://api.line.me/v2/bot/message/push", headers={"Authorization": f"Bearer {self.settings.line_channel_access_token}"}, json={"to": user_id, "messages": [{"type": "text", "text": text[:5000]}]})
            res.raise_for_status()
            return {"ok": True}


async def notify_if_needed(settings: Settings, tenant: TenantConfig, user_id: str, text: str, classification: Classification) -> None:
    if not settings.admin_webhook_url or (classification.score < 80 and classification.priority != "urgent"):
        return
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(settings.admin_webhook_url, json={"title": "LINE即レスBot 重要問い合わせ", "tenant_id": tenant.id, "company_name": tenant.company_name, "line_user_id": user_id, "text": text, "category": classification.category, "score": classification.score, "priority": classification.priority})


app = FastAPI(title="LINE即レス売上回収Bot", version="0.1.0")


def settings_dep() -> Settings:
    return get_settings()


def repo_dep(settings: Annotated[Settings, Depends(settings_dep)]) -> Repository:
    return Repository(settings)


def require_admin(settings: Annotated[Settings, Depends(settings_dep)], x_admin_token: Annotated[str | None, Header()] = None) -> None:
    if x_admin_token != settings.admin_api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "app": "LINE即レス売上回収Bot", "docs": "/docs"}


@app.get("/health")
def health(settings: Annotated[Settings, Depends(settings_dep)]) -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "env": settings.env, "database": str(settings.sqlite_path)}


@app.post("/intake/config", dependencies=[Depends(require_admin)])
def intake_config(payload: IntakeRequest, repo: Annotated[Repository, Depends(repo_dep)]) -> dict[str, Any]:
    tenant = repo.upsert_tenant(payload)
    return {"ok": True, "tenant": tenant.model_dump()}


@app.post("/admin/test-message", response_model=TestMessageResponse, dependencies=[Depends(require_admin)])
async def admin_test_message(payload: TestMessageRequest, settings: Annotated[Settings, Depends(settings_dep)], repo: Annotated[Repository, Depends(repo_dep)]) -> TestMessageResponse:
    tenant = repo.get_tenant(payload.tenant_id)
    classification = classify_message(payload.text, tenant.industry)
    reply = await ReplyGenerator(settings).generate(tenant, payload.text, classification)
    lead_id = repo.upsert_lead(tenant, payload.user_id, payload.text, classification)
    repo.save_message(MessageRecord(tenant_id=tenant.id, lead_id=lead_id, line_user_id=payload.user_id, direction="inbound", text=payload.text, category=classification.category, score=classification.score, raw_json={"source": "admin-test"}, created_at=utcnow()))
    repo.save_message(MessageRecord(tenant_id=tenant.id, lead_id=lead_id, line_user_id=payload.user_id, direction="outbound", text=reply, category=classification.category, score=classification.score, raw_json={"source": "admin-test"}, created_at=utcnow()))
    return TestMessageResponse(tenant=tenant, classification=classification, reply=reply)


@app.get("/admin/leads", dependencies=[Depends(require_admin)])
def list_leads(repo: Annotated[Repository, Depends(repo_dep)], tenant_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    return {"leads": repo.list_leads(tenant_id=tenant_id, limit=limit)}


@app.post("/webhook/line")
async def line_webhook(request: Request, settings: Annotated[Settings, Depends(settings_dep)], repo: Annotated[Repository, Depends(repo_dep)]) -> JSONResponse:
    body = await request.body()
    line = LineClient(settings)
    if not line.verify_signature(body, request.headers.get("x-line-signature")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid LINE signature")
    payload = await request.json()
    tenant = repo.get_tenant(payload.get("destination") or settings.default_tenant_id)
    generator = ReplyGenerator(settings)
    processed: list[dict[str, Any]] = []
    for event in payload.get("events", []):
        if event.get("type") != "message" or event.get("message", {}).get("type") != "text":
            continue
        text = event["message"].get("text", "")
        user_id = event.get("source", {}).get("userId") or "unknown-user"
        classification = classify_message(text, tenant.industry)
        reply = await generator.generate(tenant, text, classification)
        lead_id = repo.upsert_lead(tenant, user_id, text, classification)
        repo.save_message(MessageRecord(tenant_id=tenant.id, lead_id=lead_id, line_user_id=user_id, direction="inbound", text=text, category=classification.category, score=classification.score, raw_json=event, created_at=utcnow()))
        if event.get("replyToken"):
            await line.reply_text(event["replyToken"], reply)
            repo.save_message(MessageRecord(tenant_id=tenant.id, lead_id=lead_id, line_user_id=user_id, direction="outbound", text=reply, category=classification.category, score=classification.score, raw_json={"replyToken": event["replyToken"]}, created_at=utcnow()))
        await notify_if_needed(settings, tenant, user_id, text, classification)
        processed.append({"user_id": user_id, "category": classification.category, "score": classification.score, "priority": classification.priority})
    return JSONResponse({"ok": True, "processed": processed})


@app.post("/jobs/followups", dependencies=[Depends(require_admin)])
async def run_followups(settings: Annotated[Settings, Depends(settings_dep)], repo: Annotated[Repository, Depends(repo_dep)]) -> dict[str, Any]:
    line = LineClient(settings)
    generator = ReplyGenerator(settings)
    due = repo.due_followups()
    sent = 0
    for item in due:
        text = generator.followup_text(item["company_name"], item.get("reservation_url"), int(item["stage"]))
        await line.push_text(item["line_user_id"], text)
        repo.mark_followup_sent(item["id"])
        sent += 1
    return {"checked": len(due), "sent": sent, "dry_run": settings.line_reply_dry_run}
