# LINE即レス売上回収Bot

![LINE即レス売上回収Bot architecture](docs/assets/generated-readme-hero.png)

LINE公式アカウントに来た問い合わせへAIが即返信し、来店予約・内見予約・資料請求・無料相談まで自動で進めるFastAPI製Botです。既存のLINE公式アカウントにWebhookを接続するだけで、即レス、予約リンク案内、見込み度スコアリング、管理者通知、翌日・3日後の追客まで実行できます。

## 商品設計

| 商品 | 価格 |
|---|---:|
| 初期設定 | 29,800円 |
| 月額運用 | 9,800円 |
| 上位版 | 月19,800円 |
| 成果報酬オプション | 予約1件あたり500〜2,000円 |

## 実装済み機能

- LINE Messaging API Webhook受信
- X-Line-Signature署名検証
- 業種別問い合わせ分類
- 見込み度スコアリング
- OpenAI APIがある場合はAI返信、未設定でもテンプレ返信で稼働
- 予約リンク、資料リンク、電話案内の自動返信
- SQLiteへのリード・会話・追客予定保存
- 高スコア・緊急案件だけ管理者Webhook通知
- 翌日・3日後の追客ジョブ
- 管理API、テストAPI、CI、Docker、devcontainer

## 全体アーキテクチャ

```mermaid
flowchart TD
    A[見込み客<br>LINE問い合わせ] --> B[LINE Messaging API]
    B --> C[FastAPI Webhook<br>/webhook/line]
    C --> D{署名検証}
    D -->|OK| E[分類・スコアリング]
    D -->|NG| X[401拒否]
    E --> F{OpenAI API Keyあり?}
    F -->|あり| G[AI返信生成]
    F -->|なし| H[業種別テンプレ返信]
    G --> I[LINE Reply API]
    H --> I
    I --> A
    E --> J[(SQLite<br>leads/messages/followups)]
    E --> K[重要案件だけ<br>管理者Webhook通知]
    L[cron / scheduler] --> M[/jobs/followups]
    M --> N[LINE Push API<br>追客]
```

## ローカル起動

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn line_revenue_bot.main:app --reload
```

確認:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/admin/test-message \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: dev-token-change-me" \
  -d '{"tenant_id":"demo","user_id":"demo-user","text":"新宿の物件を内見したいです。明日空いていますか？"}'
```

## 本番に必要なもの

- HTTPS公開URL
- LINE DevelopersのMessaging APIチャネル
- `BOT_LINE_CHANNEL_SECRET`
- `BOT_LINE_CHANNEL_ACCESS_TOKEN`
- `BOT_LINE_REPLY_DRY_RUN=false`
- `BOT_ADMIN_API_TOKEN`
- 永続化されるSQLiteファイル、またはPostgreSQL等への移行
- cron相当の定期実行環境
- 任意: `BOT_OPENAI_API_KEY`
- 任意: `BOT_ADMIN_WEBHOOK_URL`

Webhook URL:

```text
https://your-domain.example.com/webhook/line
```

## 主要ファイル

| パス | 役割 |
|---|---|
| `src/line_revenue_bot/main.py` | FastAPIアプリ、LINE連携、分類、返信、DBを含む本体 |
| `tests/test_app.py` | APIと分類のテスト |
| `.github/workflows/ci.yml` | lint、test、artifact生成 |
| `docs/architecture.md` | 詳細アーキテクチャ |
| `docs/setup.md` | 初期設定ガイド |
| `CODEX.md` | 開発・安全運用ルール |

## GPT Imageで顧客説明資料を作る

README先頭の画像はGPT Image向けの説明ビジュアルとして使う想定です。詳細な生成指示は `docs/architecture.md` に含めています。商談時は「LINE問い合わせ → AI返信 → 予約回収 → 重要案件だけ通知 → 追客」の流れを1枚で説明してください。

## 初期営業文面

```text
LINEの問い合わせ、営業時間中に即返信できていますか？
AIがLINEに即返信して、予約・資料請求・相談まで自動で進めるBotを作っています。
初期29,800円、月9,800円で、まず1社だけテスト導入できます。
決済後、フォーム入力だけで設定できます。
```
