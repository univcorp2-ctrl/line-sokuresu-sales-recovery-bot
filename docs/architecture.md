# Architecture

## 目的

LINE公式アカウントに来た問い合わせへ即返信し、予約・資料請求・無料相談まで自動で進めます。最初から大規模SaaSにせず、1社ごとの受託導入で初期費用を回収し、同じ型を横展開できる構成です。

## 構成図

```mermaid
flowchart LR
    C[見込み客] --> L[LINE Messaging API]
    L --> W[FastAPI Webhook]
    W --> S[署名検証]
    S --> C1[分類・スコアリング]
    C1 --> R[AI/テンプレ返信]
    R --> L2[LINE Reply API]
    L2 --> C
    C1 --> DB[(SQLite)]
    C1 --> N[管理者Webhook]
    Cron[Scheduler] --> F[/jobs/followups]
    F --> DB
    F --> P[LINE Push API]
```

## GPT Image向けプロンプト

```text
日本語のSaaS導入説明図を作成してください。タイトルは「LINE即レス売上回収Bot」。見込み客、LINE Messaging API、FastAPI Webhook、問い合わせ分類、AI返信生成、SQLite、管理者通知、翌日・3日後追客を左から右に描いてください。緑と青を基調に、初心者にも分かるビジネス資料風にしてください。
```

## 安全運用

- 融資、法律、医療、保険の断定回答は避け、担当者確認へ誘導します。
- クレーム、返金、緊急、契約直前は人間に通知します。
- API KeyやLINEトークンはGitHubにコミットしません。
