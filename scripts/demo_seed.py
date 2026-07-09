from line_revenue_bot.classifier import classify_message
from line_revenue_bot.config import get_settings
from line_revenue_bot.db import Repository, utcnow
from line_revenue_bot.schemas import MessageRecord


def main() -> None:
    settings = get_settings()
    repo = Repository(settings)
    tenant = repo.get_tenant("demo")
    samples = [
        ("user-001", "新宿の物件を内見したいです。明日空いていますか？"),
        ("user-002", "資料を送ってください。価格も知りたいです。"),
        ("user-003", "売却査定をお願いできますか？"),
    ]
    for user_id, text in samples:
        classification = classify_message(text, tenant.industry)
        lead = repo.upsert_lead(tenant, user_id, text, classification)
        repo.save_message(MessageRecord(tenant_id=tenant.id, lead_id=lead.id, line_user_id=user_id, direction="inbound", text=text, category=classification.category, score=classification.score, raw_json={"source": "demo-seed"}, created_at=utcnow()))
    print("seeded demo leads")


if __name__ == "__main__":
    main()
