import httpx

from .config import Settings
from .schemas import Classification, TenantConfig

BASE_SAFETY = """
- 断定的な保証、法的・医療的・金融的な確定判断はしない。
- 不明点は担当者確認に回す。
- クレーム、緊急、個人情報が多い相談は管理者確認に誘導する。
- 返信は自然な日本語で、長すぎず、次の行動を1つ提示する。
""".strip()

CATEGORY_ACTIONS: dict[str, str] = {
    "内見希望": "内見希望日、物件名、人数を確認し、予約リンクを案内してください。",
    "物件問い合わせ": "対象物件、購入/賃貸/投資の目的、予算、希望エリアを確認してください。",
    "資料請求": "資料リンクを案内し、送付先や希望物件を確認してください。",
    "売却相談": "所在地、物件種別、売却希望時期を確認し、無料査定へ誘導してください。",
    "融資相談": "融資の可否は断定せず、担当者相談予約へ誘導してください。",
    "新規予約": "予約リンクを案内し、希望日時とメニューを確認してください。",
    "予約変更": "現在の予約日時と変更希望日時を確認してください。",
    "キャンセル": "キャンセル希望を受け付け、再予約リンクも案内してください。",
    "料金質問": "料金ページや目安を案内し、詳細は予約または相談へ誘導してください。",
    "アクセス質問": "住所、アクセス、駐車場などの案内に誘導してください。",
    "無料相談": "相談内容を簡単に確認し、無料相談予約リンクを案内してください。",
    "必要書類": "個別判断は避け、一般的な必要書類と担当者確認を案内してください。",
    "緊急相談": "担当者確認を優先し、電話または緊急連絡先へ誘導してください。",
    "見積依頼": "希望内容、現地調査可否、希望日時を確認してください。",
    "現地調査": "住所、希望日時、対象箇所を確認してください。",
    "査定依頼": "品目や物件情報、写真の有無、希望日時を確認してください。",
    "出張希望": "訪問エリア、希望日時、対象品を確認してください。",
    "持込相談": "持込可能時間と必要情報を案内してください。",
    "予約希望": "希望日時を確認し、予約リンクを案内してください。",
    "クレーム・緊急": "謝意を伝え、担当者が確認する旨を案内し、詳細を聞きすぎないでください。",
    "その他": "問い合わせ内容を受け止め、必要情報を1つだけ聞き返してください。",
}


class ReplyGenerator:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def generate(self, tenant: TenantConfig, text: str, classification: Classification) -> str:
        if self.settings.openai_api_key:
            try:
                return await self._generate_with_openai(tenant, text, classification)
            except Exception:
                return self._fallback_reply(tenant, classification)
        return self._fallback_reply(tenant, classification)

    async def _generate_with_openai(self, tenant: TenantConfig, text: str, classification: Classification) -> str:
        action = CATEGORY_ACTIONS.get(classification.category, CATEGORY_ACTIONS["その他"])
        system_prompt = f"""
あなたは{tenant.company_name}のLINE問い合わせ一次対応Botです。
業種: {tenant.industry}
分類: {classification.category}
見込み度: {classification.score}/100
対応方針: {action}
予約リンク: {tenant.reservation_url or '未設定'}
資料リンク: {tenant.document_url or '未設定'}
電話: {tenant.phone or '未設定'}
FAQ: {tenant.faq or '未設定'}
禁止事項: {tenant.prohibited_text or '未設定'}
安全ルール:
{BASE_SAFETY}
""".strip()
        payload = {
            "model": self.settings.openai_model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.4,
            "max_output_tokens": 320,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        output_text = data.get("output_text")
        if output_text:
            return self._sanitize(output_text, tenant)
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    return self._sanitize(content["text"], tenant)
        return self._fallback_reply(tenant, classification)

    def _fallback_reply(self, tenant: TenantConfig, classification: Classification) -> str:
        name = tenant.company_name
        reservation = tenant.reservation_url
        document = tenant.document_url
        phone = tenant.phone

        if classification.category == "クレーム・緊急":
            return f"お問い合わせありがとうございます。{name}です。ご不便をおかけしている可能性があるため、担当者が内容を確認します。差し支えなければ、お名前とご連絡先、状況を簡単にお送りください。"

        if classification.category in {"内見希望", "新規予約", "予約希望", "無料相談", "緊急相談"}:
            link = f"\n予約はこちら: {reservation}" if reservation else ""
            return f"お問い合わせありがとうございます。{name}です。ご希望内容を確認しました。希望日時を第2希望までお送りください。{link}\n担当者にも共有します。"

        if classification.category in {"資料請求"}:
            link = f"\n資料はこちら: {document}" if document else ""
            return f"お問い合わせありがとうございます。{name}です。資料請求を受け付けました。どのサービス・物件の資料をご希望かお知らせください。{link}"

        if classification.category in {"料金質問", "物件問い合わせ", "見積依頼", "査定依頼"}:
            link = f"\n相談予約: {reservation}" if reservation else ""
            return f"お問い合わせありがとうございます。{name}です。詳細を確認して最適な案内をします。ご希望内容・予算・希望時期を簡単にお送りください。{link}"

        if classification.category in {"予約変更", "キャンセル"}:
            return f"お問い合わせありがとうございます。{name}です。現在の予約日時とお名前をお送りください。確認後、担当者からご案内します。"

        extra = ""
        if reservation:
            extra += f"\n予約・相談はこちら: {reservation}"
        if phone:
            extra += f"\nお急ぎの場合: {phone}"
        return f"お問い合わせありがとうございます。{name}です。内容を確認しました。担当者が確認しやすいように、ご希望内容をもう少し詳しくお送りください。{extra}"

    def followup_text(self, company_name: str, reservation_url: str | None, stage: int) -> str:
        if stage == 1:
            link = f"\n予約・相談はこちら: {reservation_url}" if reservation_url else ""
            return f"{company_name}です。昨日のお問い合わせについて、追加で確認したい点やご希望日時はありますか？{link}"
        link = f"\nこちらから再開できます: {reservation_url}" if reservation_url else ""
        return f"{company_name}です。先日のお問い合わせについて、まだご案内可能です。必要でしたらこのままご返信ください。{link}"

    @staticmethod
    def _sanitize(text: str, tenant: TenantConfig) -> str:
        cleaned = text.strip()
        if tenant.prohibited_text:
            for word in [part.strip() for part in tenant.prohibited_text.split("、") if part.strip()]:
                cleaned = cleaned.replace(word, "")
        return cleaned[:900]
