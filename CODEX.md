# CODEX.md

## 開発方針

即金性の高い受託導入用LINE Botテンプレートです。最初の目的は大規模SaaSではなく、1社目から初期設定費を回収できる最小実用構成です。

## テスト

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```

## 安全要件

- 法律、医療、金融、保険、融資の確定判断をBotにさせない
- クレーム、返金、緊急、契約直前は人間に通知する
- 顧客のLINEチャネルアクセストークンやOpenAI API KeyをGitHubにコミットしない
