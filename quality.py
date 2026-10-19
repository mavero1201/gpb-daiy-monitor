"""Conservative final gate for Daily Banking cards.

Ambiguous offers remain in the audit with a rejection reason, never in Telegram.
This is a deterministic safeguard, not a substitute for source review.
"""
from __future__ import annotations
import re
from urllib.parse import urlparse

REWARD_WORDS = ("кешбэк", "кэшбэк", "скидк", "бонус", "балл", "приз", "розыгрыш", "подар")
MECHANICS = {
    "кешбэк": ("кешбэк", "кэшбэк"),
    "скидка / промокод": ("скидк", "промокод"),
    "розыгрыш": ("розыгрыш", "разыгрыв", "приз"),
    "бонусы": ("бонус", "балл"),
    "реферальная программа": ("реферал", "пригласите", "рекомендац"),
}
NOISE = ("этот пост можно", "подробности посмотрите", "вместе и помогите",
         "максимально рядом", "если вы потратили деньги с карты",
         "каждый месяц банк выставляет", "в мессенджере max")
BANK_LINK = {
    "ВТБ": ("втб", "vtb"),
    "Ozon Банк": ("ozon банк", "озон банк", "ozon карт", "озон карт"),
    "Газпромбанк": ("газпромбанк", "газпромбанка", "гпб"),
}

def validate_card(item, result) -> str | None:
    if not result.included:
        return None
    title = (result.title or "").strip()
    reward = (result.reward or "").strip()
    conditions = (result.conditions or "").strip()
    mechanic = (result.mechanic or "").strip()
    source = result.evidence_url or item.url
    if not all((title, reward, conditions, mechanic, result.goal,
                result.promo_start, result.promo_end, source)):
        return "quality_missing_required_field"
    if result.promo_start > result.promo_end:
        return "quality_invalid_period"
    if len(title) > 110 or len(reward) > 180 or len(conditions) > 250:
        return "quality_unstructured_card"
    combined = (title + " " + reward + " " + conditions).lower()
    if any(fragment in combined for fragment in NOISE):
        return "quality_irrelevant_text"
    if not any(x in reward.lower() for x in REWARD_WORDS) and not re.search(r"\\d+\\s*[%₽]", reward):
        return "quality_unverified_reward"
    if mechanic not in MECHANICS:
        return "quality_unknown_mechanic"
    if not any(x in (title + " " + reward).lower() for x in MECHANICS[mechanic]):
        return "quality_mechanic_mismatch"
    if item.bank in BANK_LINK and not any(x in (item.text + " " + conditions).lower() for x in BANK_LINK[item.bank]):
        return "quality_no_bank_product_link"
    if item.bank == "Ozon Банк" and "зелён" in (item.text or "").lower() and "цен" in (item.text or "").lower():
        return "quality_marketplace_offer"
    if result.promo_start == result.promo_end:
        return "quality_single_day_requires_review"
    parsed = urlparse(source)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "quality_invalid_source"
    return None
