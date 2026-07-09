from .schemas import Classification, Industry

INDUSTRY_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "property": {
        "内見希望": ["内見", "見学", "案内", "現地", "部屋を見たい"],
        "物件問い合わせ": ["物件", "マンション", "戸建", "土地", "家賃", "賃料", "価格"],
        "資料請求": ["資料", "パンフレット", "送って", "図面", "詳細"],
        "売却相談": ["売却", "査定", "売りたい", "相続"],
        "融資相談": ["ローン", "融資", "住宅ローン", "審査"],
    },
    "salon": {
        "新規予約": ["予約", "空き", "今日", "明日", "カット", "カラー", "施術"],
        "予約変更": ["変更", "時間を変え", "日程変更"],
        "キャンセル": ["キャンセル", "取り消し"],
        "料金質問": ["料金", "価格", "いくら", "メニュー"],
        "アクセス質問": ["場所", "アクセス", "駐車場", "駅"],
    },
    "clinic": {
        "新規予約": ["予約", "空き", "初診", "相談"],
        "予約変更": ["変更", "日程変更"],
        "キャンセル": ["キャンセル"],
        "料金質問": ["料金", "費用", "いくら"],
        "症状相談": ["痛い", "症状", "不調", "治療"],
    },
    "school": {
        "無料相談": ["相談", "説明会", "体験", "見学"],
        "資料請求": ["資料", "パンフレット", "カリキュラム"],
        "料金質問": ["料金", "月謝", "費用"],
    },
    "professional": {
        "無料相談": ["相談", "面談", "依頼", "問い合わせ"],
        "必要書類": ["書類", "準備", "必要なもの"],
        "料金質問": ["料金", "報酬", "費用", "見積"],
        "緊急相談": ["至急", "今日中", "期限", "裁判", "税務署"],
    },
    "renovation": {
        "見積依頼": ["見積", "リフォーム", "修理", "工事"],
        "現地調査": ["現地", "調査", "見に来て"],
        "料金質問": ["料金", "費用", "概算"],
    },
    "purchase": {
        "査定依頼": ["買取", "査定", "売りたい", "いくら"],
        "出張希望": ["出張", "来て", "訪問"],
        "持込相談": ["持ち込み", "店舗"],
    },
    "insurance": {
        "無料相談": ["相談", "見直し", "保険"],
        "資料請求": ["資料", "パンフレット"],
        "予約希望": ["予約", "面談", "空き"],
    },
    "generic": {
        "予約希望": ["予約", "空き", "相談", "面談"],
        "資料請求": ["資料", "パンフレット"],
        "料金質問": ["料金", "費用", "価格", "いくら"],
    },
}

COMMON_URGENT = ["クレーム", "怒", "返金", "キャンセルしたい", "苦情", "至急", "緊急"]
HIGH_INTENT = ["予約", "内見", "見学", "相談", "申し込み", "申込", "査定", "見積", "明日", "今日"]
MEDIUM_INTENT = ["資料", "料金", "空き", "詳細", "電話", "URL", "リンク"]
LOW_INTENT = ["こんにちは", "教えて", "質問", "営業時間"]


def classify_message(text: str, industry: Industry | str = "generic") -> Classification:
    normalized = text.strip().lower()
    if not normalized:
        return Classification(category="その他", score=10, priority="low", reason="空メッセージ")

    if any(keyword.lower() in normalized for keyword in COMMON_URGENT):
        return Classification(category="クレーム・緊急", score=95, priority="urgent", reason="緊急語またはクレーム語を検知")

    rules = INDUSTRY_KEYWORDS.get(str(industry), INDUSTRY_KEYWORDS["generic"])
    matched_category = "その他"
    matched_keywords: list[str] = []
    for category, keywords in rules.items():
        hits = [keyword for keyword in keywords if keyword.lower() in normalized]
        if hits:
            matched_category = category
            matched_keywords = hits
            break

    score = 35
    if matched_category != "その他":
        score += 20
    if any(keyword.lower() in normalized for keyword in HIGH_INTENT):
        score += 30
    if any(keyword.lower() in normalized for keyword in MEDIUM_INTENT):
        score += 15
    if any(keyword.lower() in normalized for keyword in LOW_INTENT):
        score += 5

    score = min(score, 100)
    if score >= 80:
        priority = "high"
    elif score >= 55:
        priority = "normal"
    else:
        priority = "low"

    reason = "業種別キーワードで分類"
    if matched_keywords:
        reason += f": {', '.join(matched_keywords)}"
    return Classification(category=matched_category, score=score, priority=priority, reason=reason)
