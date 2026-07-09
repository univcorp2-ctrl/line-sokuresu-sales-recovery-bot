from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, field_validator

Industry = Literal[
    "property",
    "salon",
    "clinic",
    "school",
    "professional",
    "renovation",
    "purchase",
    "insurance",
    "generic",
]


class TenantConfig(BaseModel):
    id: str = Field(default="demo", min_length=1, max_length=80)
    company_name: str = Field(default="デモ会社", max_length=120)
    industry: Industry = "property"
    service_url: str | None = None
    reservation_url: str | None = None
    document_url: str | None = None
    phone: str | None = None
    faq: str | None = None
    prohibited_text: str | None = None
    notification_target: str | None = None

    @field_validator("id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        return value.strip().replace(" ", "-")


class Classification(BaseModel):
    category: str
    score: int = Field(ge=0, le=100)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    reason: str


class Lead(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    line_user_id: str
    display_name: str | None = None
    last_message: str
    category: str
    score: int
    status: str = "open"
    followup_due_at: datetime | None = None
    second_followup_due_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class MessageRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    lead_id: str
    line_user_id: str
    direction: Literal["inbound", "outbound"]
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


class HealthResponse(BaseModel):
    status: str
    app: str
    env: str
    database: str


class LeadListResponse(BaseModel):
    leads: list[dict[str, Any]]


class FollowupRunResponse(BaseModel):
    checked: int
    sent: int
    dry_run: bool


class AdminWebhookPayload(BaseModel):
    tenant_id: str
    company_name: str
    line_user_id: str
    text: str
    category: str
    score: int
    priority: str
    reservation_url: HttpUrl | None = None
