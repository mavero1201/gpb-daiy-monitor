from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from html import unescape
from zoneinfo import ZoneInfo
import re

import requests
from bs4 import BeautifulSoup

from sources import BANK_SOURCES

MOSCOW = ZoneInfo("Europe/Moscow")


@dataclass
class RawItem:
    bank: str
    source_id: str
    source_type: str
    published_at: datetime
    text: str
    url: str
    external_links: list[str]


@dataclass
class SourceCheck:
    bank: str
    source_id: str
    source_type: str
    source_value: str
    status: str
    item_count: int = 0
    error: str = ""


def previous_calendar_week(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(MOSCOW)
    today = now.date()
    this_monday = today - timedelta(days=today.weekday())
    start_date = this_monday - timedelta(days=7)
    end_date = this_monday - timedelta(days=1)
    start = datetime.combine(start_date, datetime.min.time(), tzinfo=MOSCOW)
    end = datetime.combine(end_date, datetime.max.time(), tzinfo=MOSCOW)
    return start, end


def clean_text(text: str) -> str:
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_telegram_source(bank: str, source: dict, start: datetime, end: datetime) -> tuple[list[RawItem], SourceCheck]:
    channel = source["value"]
    base_url = f"https://t.me/s/{channel}"
    page_url = base_url
    items: list[RawItem] = []
    seen_urls: set[str] = set()
    seen_page_markers: set[int] = set()

    # Telegram web preview показывает ограниченное число последних постов.
    # Идём назад по страницам, пока не дошли до начала нужной недели.
    for _ in range(20):
        try:
            response = requests.get(
                page_url,
                timeout=30,
                headers={"User-Agent": "Mozilla/5.0 GPB-Daily-Monitor/2.0"},
            )
            response.raise_for_status()
        except Exception as exc:
            return items, SourceCheck(
                bank=bank,
                source_id=source["id"],
                source_type="telegram",
                source_value=channel,
                status="error",
                item_count=len(items),
                error=f"{type(exc).__name__}: {exc}",
            )

        soup = BeautifulSoup(response.text, "html.parser")
        wraps = soup.select(".tgme_widget_message_wrap")
        if not wraps:
            break

        oldest_seen: datetime | None = None
        message_ids: list[int] = []

        for wrap in wraps:
            message_tag = wrap.select_one(".tgme_widget_message[data-post]")
            if message_tag:
                data_post = message_tag.get("data-post", "")
                match = re.search(r"/(\d+)$", data_post)
                if match:
                    message_ids.append(int(match.group(1)))

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

            if oldest_seen is None or published < oldest_seen:
                oldest_seen = published

            if not (start <= published <= end):
                continue

            text = clean_text(text_tag.get_text(" ", strip=True))
            if not text:
                continue

            post_url = link_tag.get("href", base_url)
            if post_url in seen_urls:
                continue
            seen_urls.add(post_url)

            links = []
            for a in wrap.select("a[href]"):
                href = a.get("href")
                if href and href not in links:
                    links.append(href)

            items.append(
                RawItem(
                    bank=bank,
                    source_id=source["id"],
                    source_type="telegram",
                    published_at=published,
                    text=text,
                    url=post_url,
                    external_links=links,
                )
            )

        if oldest_seen and oldest_seen <= start:
            break
        if not message_ids:
            break

        before_id = min(message_ids)
        if before_id in seen_page_markers:
            break
        seen_page_markers.add(before_id)
        page_url = f"{base_url}?before={before_id}"

    return items, SourceCheck(
        bank=bank,
        source_id=source["id"],
        source_type="telegram",
        source_value=channel,
        status="ok",
        item_count=len(items),
    )

def collect_previous_week() -> tuple[datetime, datetime, list[RawItem], list[SourceCheck]]:
    start, end = previous_calendar_week()
    items: list[RawItem] = []
    checks: list[SourceCheck] = []

    for bank_entry in BANK_SOURCES:
        bank = bank_entry["bank"]
        for source in bank_entry["sources"]:
            if source["type"] == "telegram":
                source_items, check = fetch_telegram_source(bank, source, start, end)
                items.extend(source_items)
                checks.append(check)
            else:
                checks.append(
                    SourceCheck(
                        bank=bank,
                        source_id=source["id"],
                        source_type=source["type"],
                        source_value=source["value"],
                        status="not_implemented",
                    )
                )

    return start, end, items, checks
