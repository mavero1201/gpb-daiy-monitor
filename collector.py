from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from html import unescape
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import re

import requests
from bs4 import BeautifulSoup

from sources import SOURCES

MOSCOW = ZoneInfo("Europe/Moscow")

PROMO_SIGNALS = (
    "акци",
    "кешбэк",
    "кэшбэк",
    "бонус",
    "розыгрыш",
    "подар",
    "скидк",
    "промокод",
    "выигра",
    "приз",
    "вернем",
    "вернём",
    "возвращаем",
)

ACTION_SIGNALS = (
    "оформ",
    "закаж",
    "соверш",
    "оплат",
    "покуп",
    "попол",
    "сняти",
    "снять",
    "перевод",
    "подключ",
    "активир",
    "зарегистр",
    "участв",
    "получите",
    "получайте",
)

BANKING_CONTEXT = (
    "карт",
    "дебетов",
    "счет",
    "счёт",
    "платеж",
    "оплат",
    "покуп",
    "перевод",
    "попол",
    "сняти",
    "банкомат",
    "кешбэк",
    "кэшбэк",
    "балл",
    "кошелек",
    "кошелёк",
    "вклад",
    "страхован",
    "осаго",
    "каско",
    "pay",
    "пэй",
)

EXCLUDE_KEYWORDS = (
    "детская карта",
    "детской карт",
    "детских карт",
    "для детей",
    "альфа-картах для детей",
    "premium",
    "private banking",
    "премиальн",
)

REWARD_RE = re.compile(
    r"(?:\b\d{1,3}\s?%\b|\b\d[\d\s]{2,}\s?(?:₽|руб(?:лей|ля|ль|\.)?)\b|"
    r"\b\d[\d\s]{0,}\s?(?:балл(?:ов|а)?|бонус(?:ов|а)?)\b)",
    re.IGNORECASE,
)


@dataclass
class Candidate:
    bank: str
    published_at: datetime
    text: str
    url: str
    external_links: list[str]
    validation_text: str = ""


def previous_calendar_week(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(MOSCOW)
    today = now.date()
    this_monday = today - timedelta(days=today.weekday())
    start_date = this_monday - timedelta(days=7)
    end_date = this_monday - timedelta(days=1)
    start = datetime.combine(start_date, datetime.min.time(), tzinfo=MOSCOW)
    end = datetime.combine(end_date, datetime.max.time(), tzinfo=MOSCOW)
    return start, end


def looks_relevant(text: str) -> bool:
    low = text.lower()

    if any(term in low for term in EXCLUDE_KEYWORDS):
        return False

    has_promo = any(term in low for term in PROMO_SIGNALS)
    has_action = any(term in low for term in ACTION_SIGNALS)
    has_banking_context = any(term in low for term in BANKING_CONTEXT)
    has_reward = bool(REWARD_RE.search(text))
    has_strong_promo = any(term in low for term in ("розыгрыш", "промокод", "подар"))

    return has_promo and has_banking_context and has_action and (has_reward or has_strong_promo)


def clean_text(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_external_link(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return bool(host) and "t.me" not in host and "telegram.me" not in host


def fetch_page_text(url: str) -> str:
    try:
        response = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 GPB-Daily-Monitor/1.0"},
            allow_redirects=True,
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            return ""
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return clean_text(soup.get_text(" ", strip=True))[:30000]
    except Exception:
        return ""


def enrich_validation_text(post_text: str, external_links: list[str]) -> str:
    parts = [post_text]
    checked = 0
    for link in external_links:
        if not is_external_link(link):
            continue
        page_text = fetch_page_text(link)
        if page_text:
            parts.append(page_text)
            checked += 1
        if checked >= 3:
            break
    return clean_text(" ".join(parts))


def fetch_telegram_candidates(bank: str, channel: str, start: datetime, end: datetime) -> list[Candidate]:
    url = f"https://t.me/s/{channel}"
    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 GPB-Daily-Monitor/1.0"},
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    items: list[Candidate] = []

    for wrap in soup.select(".tgme_widget_message_wrap"):
        time_tag = wrap.select_one("time[datetime]")
        text_tag = wrap.select_one(".tgme_widget_message_text")
        link_tag = wrap.select_one("a.tgme_widget_message_date")

        if not time_tag or not text_tag or not link_tag:
            continue

        raw_dt = time_tag.get("datetime")
        if not raw_dt:
            continue

        try:
            published = datetime.fromisoformat(raw_dt.replace("Z", "+00:00")).astimezone(MOSCOW)
        except ValueError:
            continue

        if not (start <= published <= end):
            continue

        text = clean_text(text_tag.get_text(" ", strip=True))
        if not text or not looks_relevant(text):
            continue

        links = []
        for a in wrap.select("a[href]"):
            href = a.get("href")
            if href and href not in links:
                links.append(href)

        validation_text = enrich_validation_text(text, links)

        items.append(
            Candidate(
                bank=bank,
                published_at=published,
                text=text,
                url=link_tag.get("href", url),
                external_links=links,
                validation_text=validation_text,
            )
        )

    return items


def collect_previous_week() -> tuple[datetime, datetime, dict[str, list[Candidate]], dict[str, str]]:
    start, end = previous_calendar_week()
    found: dict[str, list[Candidate]] = {}
    errors: dict[str, str] = {}

    for source in SOURCES:
        bank = source["bank"]
        channel = source.get("telegram")
        found[bank] = []

        if not channel:
            continue

        try:
            found[bank] = fetch_telegram_candidates(bank, channel, start, end)
        except Exception as exc:
            errors[bank] = f"{type(exc).__name__}: {exc}"

    return start, end, found, errors
