# 初期設定ガイド

## 1. ローカル確認

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn line_revenue_bot.main:app --reload
```

ブラウザで開きます。

```text
http://localhost:8000
```

## 2. 顧客情報を登録

```bash
curl -X POST http://localhost:8000/intake/config \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: dev-token-change-me" \
  -d @examples/intake-property.json
```

## 3. LINE Developersで必要な値を取得

```text
BOT_LINE_CHANNEL_SECRET=チャネルシークレット
BOT_LINE_CHANNEL_ACCESS_TOKEN=チャネルアクセストークン
BOT_LINE_REPLY_DRY_RUN=false
BOT_LINE_SIGNATURE_VERIFICATION=true
```

## 4. Webhook URLを設定

```text
https://your-bot.example.com/webhook/line
```

## 5. AI返信を有効化

テンプレ返信だけでも稼働します。AI返信を使う場合のみ設定します。

```text
BOT_OPENAI_API_KEY=OpenAI API Key
BOT_OPENAI_MODEL=gpt-4.1-mini
```

## 6. 管理者通知を有効化

```text
BOT_ADMIN_WEBHOOK_URL=https://example.com/webhook
```

## 7. 追客ジョブ

```bash
curl -X POST https://your-bot.example.com/jobs/followups \
  -H "X-Admin-Token: 本番のBOT_ADMIN_API_TOKEN"
```

## 8. 本番デプロイで必要なもの

- HTTPS公開URL
- 永続化ストレージ
- 環境変数設定
- cron相当の定期実行
- ログ確認手段
