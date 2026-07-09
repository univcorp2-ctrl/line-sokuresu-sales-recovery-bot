# Architecture

## 目的

LINE公式アカウントに来た問い合わせへ即返信し、予約・資料請求・無料相談まで自動で進めます。最初から大規模SaaSにせず、1社ごとの受託導入で初期費用を回収し、同じ型を横展開できる構成です。

## コンポーネント

| コンポーネント | 内容 |
|---|---|
| LINE公式アカウント | 見込み客との入口 |
| LINE Messaging API | Webhook受信、Reply API、Push API |
| FastAPI | Webhook、管理API、追客ジョブ |
| Classifier | 問い合わせ分類、見込み度スコアリング |
| ReplyGenerator | OpenAI APIまたはテンプレで返信生成 |
| SQLite | リード、メッセージ、追客予定の保存 |
| AdminNotifier | 高スコア・緊急案件をSlack/Make/Zapier等へ通知 |
| Scheduler | `/jobs/followups` を定期実行 |

## Mermaid構成図

```mermaid
flowchart LR
    C1[見込み客 LINEメッセージ] --> L1[LINE Webhook]
    L1 --> A1[FastAPI /webhook/line]
    A1 --> A2[署名検証]
    A2 --> A3[分類・スコア]
    A3 --> A4[AI/テンプレ返信]
    A4 --> L2[LINE Reply API]
    L2 --> C1
    A3 --> D1[(SQLite)]
    A4 --> D1
    A3 --> O1[管理者Webhook通知]
    S1[Scheduler] --> A5[/jobs/followups]
    A5 --> D1
    A5 --> L3[LINE Push API]
```

## 注意点

- Reply APIはWebhookへの返信に使うため、返信可能時間内に処理を終える必要があります。
- Push APIを使う追客は配信通数やプラン条件の影響を受ける可能性があります。
- 融資、法律、医療、保険の断定回答は避け、必ず担当者確認へ誘導します。
