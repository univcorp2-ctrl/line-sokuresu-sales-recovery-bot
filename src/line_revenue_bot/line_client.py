import base64
import hashlib
import hmac
from typing import Any

import httpx

from .config import Settings


class LineClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def verify_signature(self, body: bytes, signature: str | None) -> bool:
        if not self.settings.line_signature_verification:
            return True
        if not self.settings.line_channel_secret:
            return True
        if not signature:
            return False
        digest = hmac.new(
            self.settings.line_channel_secret.encode("utf-8"), body, hashlib.sha256
        ).digest()
        expected = base64.b64encode(digest).decode("utf-8")
        return hmac.compare_digest(expected, signature)

    async def reply_text(self, reply_token: str, text: str) -> dict[str, Any]:
        if self.settings.line_reply_dry_run or not self.settings.line_channel_access_token:
            return {"dry_run": True, "reply_token": reply_token, "text": text}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://api.line.me/v2/bot/message/reply",
                headers={"Authorization": f"Bearer {self.settings.line_channel_access_token}"},
                json={"replyToken": reply_token, "messages": [{"type": "text", "text": text[:5000]}]},
            )
            response.raise_for_status()
            return response.json() if response.content else {"ok": True}

    async def push_text(self, user_id: str, text: str) -> dict[str, Any]:
        if self.settings.line_reply_dry_run or not self.settings.line_channel_access_token:
            return {"dry_run": True, "user_id": user_id, "text": text}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://api.line.me/v2/bot/message/push",
                headers={"Authorization": f"Bearer {self.settings.line_channel_access_token}"},
                json={"to": user_id, "messages": [{"type": "text", "text": text[:5000]}]},
            )
            response.raise_for_status()
            return response.json() if response.content else {"ok": True}
