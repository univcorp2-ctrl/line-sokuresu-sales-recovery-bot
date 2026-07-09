from typing import Any

import httpx

from .config import Settings
from .schemas import Classification, TenantConfig


class AdminNotifier:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def notify_if_needed(self, tenant: TenantConfig, user_id: str, text: str, classification: Classification) -> dict[str, Any] | None:
        if classification.score < 80 and classification.priority != "urgent":
            return None
        payload = {
            "title": "LINE即レスBot 重要問い合わせ",
            "tenant_id": tenant.id,
            "company_name": tenant.company_name,
            "line_user_id": user_id,
            "text": text,
            "category": classification.category,
            "score": classification.score,
            "priority": classification.priority,
            "reservation_url": tenant.reservation_url,
        }
        if not self.settings.admin_webhook_url:
            return {"dry_run": True, "payload": payload}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(self.settings.admin_webhook_url, json=payload)
            response.raise_for_status()
            return {"ok": True, "status_code": response.status_code}
