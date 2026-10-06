from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from html import unescape
from zoneinfo import ZoneInfo
import re

import requests
from bs4 import BeautifulSoup

from sources import SOURCES

MOSCOW = ZoneInfo("Europe/Moscow")

POSITIVE_KEYWORDS = (
    "акци",
    "кешбэк",
    "кэшбэк",
    "бонус",
    "розыгрыш",
    "подар",
    "скидк",
    "промокод",
    "вернем",
    "вернём",
    "получите",
    "получайте",
    "100%",
    "50%",
    "25%",
    "20%",
    "15%",
    "10%",
    "5%",
    "друг",
    "реферал",
    "покупк",
    "оплат",
    "сняти",
    "перевод",
    "попол",
)

EXCLUDE_KEYWORDS = (
    "детская карта",
    "детской карт",
    "для детей",
    "premium",
    "private banking",
    "премиальн",
)


@dataclass
class Candidate:
    bank: str
    published_at: datetime
    text: str
    url: str


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
    return any(term in low for term in POSITIVE_KEYWORDS)


def clean_text(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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

        items.append(
            Candidate(
                bank=bank,
                published_at=published,
                text=text,
                url=link_tag.get("href", url),
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
