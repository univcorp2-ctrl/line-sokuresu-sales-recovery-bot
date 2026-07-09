from fastapi.testclient import TestClient

from line_revenue_bot.main import app, classify_message

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_classifier_property_viewing() -> None:
    result = classify_message("新宿の物件を内見したいです。明日空いていますか？", "property")
    assert result.category == "内見希望"
    assert result.score >= 80


def test_admin_test_message() -> None:
    response = client.post(
        "/admin/test-message",
        headers={"X-Admin-Token": "dev-token-change-me"},
        json={"tenant_id": "demo", "user_id": "pytest-user", "text": "この物件を内見したいです。明日空いてますか？"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["classification"]["category"] == "内見希望"
    assert "希望日時" in data["reply"] or "予約" in data["reply"]


def test_line_webhook_dry_run() -> None:
    payload = {"destination": "demo", "events": [{"type": "message", "replyToken": "reply-token-1", "source": {"userId": "line-user-1", "type": "user"}, "message": {"id": "1", "type": "text", "text": "資料を送ってください"}}]}
    response = client.post("/webhook/line", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["processed"][0]["category"] == "資料請求"


def test_admin_leads_requires_token() -> None:
    response = client.get("/admin/leads")
    assert response.status_code == 401
