from line_revenue_bot.classifier import classify_message


def test_property_viewing_is_high_intent() -> None:
    result = classify_message("新宿の物件を内見したいです。明日空いていますか？", "property")
    assert result.category == "内見希望"
    assert result.score >= 80
    assert result.priority == "high"


def test_complaint_is_urgent() -> None:
    result = classify_message("返金してほしい。クレームです。", "salon")
    assert result.category == "クレーム・緊急"
    assert result.score == 95
    assert result.priority == "urgent"
