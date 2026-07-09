from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .classifier import classify_message
from .config import Settings, get_settings
from .db import Repository, utcnow
from .line_client import LineClient
from .notifier import AdminNotifier
from .reply_generator import ReplyGenerator
from .schemas import (
    FollowupRunResponse,
    HealthResponse,
    IntakeRequest,
    LeadListResponse,
    MessageRecord,
    TestMessageRequest,
    TestMessageResponse,
)

app = FastAPI(title="LINE即レス売上回収Bot", version="0.1.0")

static_dir = Path(__file__).resolve().parents[2] / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


def settings_dep() -> Settings:
    return get_settings()


def repo_dep(settings: Annotated[Settings, Depends(settings_dep)]) -> Repository:
    return Repository(settings)


def require_admin(settings: Annotated[Settings, Depends(settings_dep)], x_admin_token: Annotated[str | None, Header()] = None) -> None:
    if x_admin_token != settings.admin_api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")


@app.get("/")
def root() -> FileResponse | dict[str, str]:
    index = static_dir / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"status": "ok", "app": "LINE即レス売上回収Bot"}


@app.get("/health", response_model=HealthResponse)
def health(settings: Annotated[Settings, Depends(settings_dep)]) -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name, env=settings.env, database=str(settings.sqlite_path))


@app.post("/intake/config", dependencies=[Depends(require_admin)])
def intake_config(payload: IntakeRequest, repo: Annotated[Repository, Depends(repo_dep)]) -> dict[str, Any]:
    tenant = repo.upsert_tenant(payload)
    return {"ok": True, "tenant": tenant.model_dump()}


@app.post("/admin/test-message", response_model=TestMessageResponse, dependencies=[Depends(require_admin)])
async def admin_test_message(payload: TestMessageRequest, settings: Annotated[Settings, Depends(settings_dep)], repo: Annotated[Repository, Depends(repo_dep)]) -> TestMessageResponse:
    tenant = repo.get_tenant(payload.tenant_id)
    classification = classify_message(payload.text, tenant.industry)
    generator = ReplyGenerator(settings)
    reply = await generator.generate(tenant, payload.text, classification)
    lead = repo.upsert_lead(tenant, payload.user_id, payload.text, classification)
    repo.save_message(MessageRecord(tenant_id=tenant.id, lead_id=lead.id, line_user_id=payload.user_id, direction="inbound", text=payload.text, category=classification.category, score=classification.score, raw_json={"source": "admin-test"}, created_at=utcnow()))
    repo.save_message(MessageRecord(tenant_id=tenant.id, lead_id=lead.id, line_user_id=payload.user_id, direction="outbound", text=reply, category=classification.category, score=classification.score, raw_json={"source": "admin-test"}, created_at=utcnow()))
    return TestMessageResponse(tenant=tenant, classification=classification, reply=reply)


@app.get("/admin/leads", response_model=LeadListResponse, dependencies=[Depends(require_admin)])
def list_leads(repo: Annotated[Repository, Depends(repo_dep)], tenant_id: str | None = None, limit: int = 100) -> LeadListResponse:
    return LeadListResponse(leads=repo.list_leads(tenant_id=tenant_id, limit=limit))


@app.post("/webhook/line")
async def line_webhook(request: Request, settings: Annotated[Settings, Depends(settings_dep)], repo: Annotated[Repository, Depends(repo_dep)]) -> JSONResponse:
    body = await request.body()
    signature = request.headers.get("x-line-signature")
    line = LineClient(settings)
    if not line.verify_signature(body, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid LINE signature")

    payload = await request.json()
    tenant_id = payload.get("destination") or settings.default_tenant_id
    tenant = repo.get_tenant(tenant_id)
    generator = ReplyGenerator(settings)
    notifier = AdminNotifier(settings)
    processed: list[dict[str, Any]] = []

    for event in payload.get("events", []):
        if event.get("type") != "message" or event.get("message", {}).get("type") != "text":
            continue
        text = event["message"].get("text", "")
        user_id = event.get("source", {}).get("userId") or "unknown-user"
        reply_token = event.get("replyToken")
        classification = classify_message(text, tenant.industry)
        reply = await generator.generate(tenant, text, classification)
        lead = repo.upsert_lead(tenant, user_id, text, classification)
        repo.save_message(MessageRecord(tenant_id=tenant.id, lead_id=lead.id, line_user_id=user_id, direction="inbound", text=text, category=classification.category, score=classification.score, raw_json=event, created_at=utcnow()))
        if reply_token:
            await line.reply_text(reply_token, reply)
            repo.save_message(MessageRecord(tenant_id=tenant.id, lead_id=lead.id, line_user_id=user_id, direction="outbound", text=reply, category=classification.category, score=classification.score, raw_json={"replyToken": reply_token}, created_at=utcnow()))
        await notifier.notify_if_needed(tenant, user_id, text, classification)
        processed.append({"user_id": user_id, "category": classification.category, "score": classification.score, "priority": classification.priority})

    return JSONResponse({"ok": True, "processed": processed})


@app.post("/jobs/followups", response_model=FollowupRunResponse, dependencies=[Depends(require_admin)])
async def run_followups(settings: Annotated[Settings, Depends(settings_dep)], repo: Annotated[Repository, Depends(repo_dep)]) -> FollowupRunResponse:
    line = LineClient(settings)
    generator = ReplyGenerator(settings)
    due = list(repo.due_followups(now=datetime.now(UTC)))
    sent = 0
    for item in due:
        text = generator.followup_text(company_name=item["company_name"], reservation_url=item.get("reservation_url"), stage=int(item["stage"]))
        await line.push_text(item["line_user_id"], text)
        repo.mark_followup_sent(item["id"])
        sent += 1
    return FollowupRunResponse(checked=len(due), sent=sent, dry_run=settings.line_reply_dry_run)
