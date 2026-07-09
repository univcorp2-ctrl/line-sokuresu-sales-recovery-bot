# 初期設定ガイド

## 1. ローカル確認

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn line_revenue_bot.main:app --reload
```

## 2. LINE設定

LINE DevelopersでMessaging APIチャネルを作成し、以下を本番環境変数に設定します。

```text
BOT_LINE_CHANNEL_SECRET=チャネルシークレット
BOT_LINE_CHANNEL_ACCESS_TOKEN=チャネルアクセストークン
BOT_LINE_REPLY_DRY_RUN=false
BOT_LINE_SIGNATURE_VERIFICATION=true
```

Webhook URL:

```text
https://your-domain.example.com/webhook/line
```

## 3. 顧客情報登録

```bash
curl -X POST https://your-domain.example.com/intake/config \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: 本番のBOT_ADMIN_API_TOKEN" \
  -d '{"id":"demo","company_name":"デモ不動産","industry":"property","reservation_url":"https://example.com/reserve","document_url":"https://example.com/docs"}'
```

## 4. 追客ジョブ

```bash
curl -X POST https://your-domain.example.com/jobs/followups \
  -H "X-Admin-Token: 本番のBOT_ADMIN_API_TOKEN"
```

## 5. 本番に必要なもの

- HTTPS公開URL
- LINE Messaging APIチャネル
- 永続化ストレージ
- cron相当の定期実行
- 管理者通知Webhook
- 任意でOpenAI API Key
