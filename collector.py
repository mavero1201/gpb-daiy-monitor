from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from html import unescape
from io import BytesIO
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo
import json
import re

import requests
import urllib3
from bs4 import BeautifulSoup
from pypdf import PdfReader

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from sources import BANK_SOURCES

MOSCOW = ZoneInfo("Europe/Moscow")

PROMO_HINTS = (
    "акци", "кешбэк", "кэшбэк", "бонус", "розыгрыш", "подар",
    "скидк", "промокод", "выигра", "спецпредлож", "предложение",
    "cashback", "promo",
)

BANKING_HINTS = (
    "карт", "дебет", "плат", "покуп", "перевод", "попол", "сняти",
    "кошелек", "кошелёк", "pay", "кешбэк", "кэшбэк", "бонус",
)

DATE_PATTERNS = (
    re.compile(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b"),
    re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b"),
)

MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


@dataclass
class RawItem:
    bank: str
    source_id: str
    source_type: str
    published_at: datetime | None
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
    required: bool = True
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
    required = source.get("required", True)

    for _ in range(20):
        try:
            response = requests.get(
                page_url,
                timeout=30,
                headers={"User-Agent": "Mozilla/5.0 GPB-Daily-Monitor/3.0"},
            )
            response.raise_for_status()
        except Exception as exc:
            return items, SourceCheck(
                bank=bank,
                source_id=source["id"],
                source_type="telegram",
                source_value=channel,
                status="error",
                required=required,
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
        required=required,
        item_count=len(items),
    )


def _base_domain(url: str) -> str:
    host = urlparse(url).hostname or ""
    parts = host.lower().split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host.lower()


def _same_domain(url: str, root_url: str) -> bool:
    return _base_domain(url) == _base_domain(root_url)


def _looks_like_candidate_link(label: str, href: str) -> bool:
    value = f"{label} {href}".lower()
    return (
        any(x in value for x in PROMO_HINTS)
        and any(x in value for x in BANKING_HINTS + ("акци", "promo"))
    ) or (
        any(x in value for x in ("правила акции", "условия акции", "promotion", "/promo/", "/actions/", ".pdf"))
        and not any(x in value for x in ("privacy", "политика конфиденциальности"))
    )


def _parse_datetime_value(value: str) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=MOSCOW)
        return dt.astimezone(MOSCOW)
    except ValueError:
        pass

    for pattern in DATE_PATTERNS:
        match = pattern.search(value)
        if not match:
            continue
        try:
            if pattern is DATE_PATTERNS[0]:
                year, month, day = map(int, match.groups())
            else:
                day, month, year = map(int, match.groups())
            return datetime(year, month, day, 12, 0, tzinfo=MOSCOW)
        except ValueError:
            continue

    month_names = "|".join(MONTHS)
    match = re.search(rf"\b(\d{{1,2}})\s+({month_names})\s+(20\d{{2}})\b", value, re.IGNORECASE)
    if match:
        try:
            return datetime(
                int(match.group(3)),
                MONTHS[match.group(2).lower()],
                int(match.group(1)),
                12,
                0,
                tzinfo=MOSCOW,
            )
        except ValueError:
            return None
    return None


def _extract_jsonld_dates(soup: BeautifulSoup) -> list[datetime]:
    result = []
    for tag in soup.select('script[type="application/ld+json"]'):
        raw = tag.string or tag.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue

        stack = data if isinstance(data, list) else [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for key in ("datePublished", "dateCreated"):
                    dt = _parse_datetime_value(str(node.get(key, "")))
                    if dt:
                        result.append(dt)
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(node, list):
                stack.extend(node)
    return result


def _extract_published_at_html(soup: BeautifulSoup, url: str) -> datetime | None:
    candidates: list[datetime] = []

    for dt in _extract_jsonld_dates(soup):
        candidates.append(dt)

    selectors = [
        'meta[property="article:published_time"]',
        'meta[name="date"]',
        'meta[name="pubdate"]',
        'meta[itemprop="datePublished"]',
        'time[datetime]',
    ]
    for selector in selectors:
        for tag in soup.select(selector):
            raw = tag.get("content") or tag.get("datetime") or tag.get_text(" ", strip=True)
            dt = _parse_datetime_value(raw or "")
            if dt:
                candidates.append(dt)

    visible = clean_text(soup.get_text(" ", strip=True))
    for marker in ("Опубликовано", "Дата публикации", "Дата размещения", "Публикация"):
        match = re.search(
            rf"{marker}\s*[:\-]?\s*(\d{{1,2}}[./]\d{{1,2}}[./]20\d{{2}}|\d{{1,2}}\s+[а-яё]+\s+20\d{{2}})",
            visible,
            re.IGNORECASE,
        )
        if match:
            dt = _parse_datetime_value(match.group(1))
            if dt:
                candidates.append(dt)

    path_dt = _parse_datetime_value(url)
    if path_dt:
        candidates.append(path_dt)

    if not candidates:
        return None
    return min(candidates)


def _pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content))
        text = " ".join((page.extract_text() or "") for page in reader.pages[:40])
        return clean_text(text)[:60000]
    except Exception:
        return ""


def _http_get(url: str):
    kwargs = {
        "timeout": 30,
        "headers": {"User-Agent": "Mozilla/5.0 GPB-Daily-Monitor/3.1"},
        "allow_redirects": True,
    }
    try:
        return requests.get(url, **kwargs)
    except requests.exceptions.SSLError:
        # Часть российских банков использует цепочки сертификатов,
        # которые GitHub-hosted runner не доверяет. Повторяем запрос без
        # проверки TLS только для публичных страниц из фиксированного реестра.
        return requests.get(url, verify=False, **kwargs)


def _reader_fetch(url: str) -> tuple[str, BeautifulSoup | None, str]:
    reader_url = "https://r.jina.ai/" + url
    response = requests.get(
        reader_url,
        timeout=45,
        headers={
            "User-Agent": "Mozilla/5.0 GPB-Daily-Monitor/3.2",
            "Accept": "text/plain",
        },
    )
    response.raise_for_status()
    text = clean_text(response.text)
    if len(text) < 100:
        raise RuntimeError("Reader returned too little readable content")
    return text[:60000], None, url


def _fetch_document(url: str) -> tuple[str, BeautifulSoup | None, str]:
    try:
        response = _http_get(url)
        response.raise_for_status()
        final_url = response.url
        content_type = response.headers.get("content-type", "").lower()

        if "pdf" in content_type or final_url.lower().endswith(".pdf"):
            text = _pdf_text(response.content)
            if len(text) >= 100:
                return text, None, final_url
            return _reader_fetch(url)

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text = clean_text(soup.get_text(" ", strip=True))
        if len(text) >= 100:
            return text[:60000], soup, final_url
    except Exception:
        pass

    # Fallback для сайтов с WAF/JS-защитой: Jina Reader только рендерит
    # тот же официальный URL. Источником в карточке остаётся адрес банка.
    return _reader_fetch(url)


def fetch_web_source(bank: str, source: dict, start: datetime, end: datetime) -> tuple[list[RawItem], SourceCheck]:
    root_url = source["value"]
    required = source.get("required", True)
    items: list[RawItem] = []
    seen_urls: set[str] = set()

    try:
        root_text, root_soup, final_root = _fetch_document(root_url)
    except Exception as exc:
        return [], SourceCheck(
            bank=bank,
            source_id=source["id"],
            source_type="web",
            source_value=root_url,
            status="error",
            required=required,
            error=f"{type(exc).__name__}: {exc}",
        )

    if not root_text or len(root_text) < 100:
        return [], SourceCheck(
            bank=bank,
            source_id=source["id"],
            source_type="web",
            source_value=root_url,
            status="limited",
            required=required,
            error="Source returned too little readable content",
        )

    candidate_urls: list[str] = []

    if root_soup is not None:
        for a in root_soup.select("a[href]"):
            href = a.get("href") or ""
            if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            absolute = urljoin(final_root, href)
            if not _same_domain(absolute, final_root):
                continue
            label = clean_text(a.get_text(" ", strip=True))
            if _looks_like_candidate_link(label, absolute) and absolute not in candidate_urls:
                candidate_urls.append(absolute)
    else:
        # Jina Reader возвращает Markdown. Извлекаем ссылки из него и
        # продолжаем обход официальных карточек/правил банка.
        for label, href in re.findall(r"\[([^\]]*)\]\((https?://[^)\s]+)\)", root_text):
            href = href.rstrip(".,;")
            if not _same_domain(href, final_root):
                continue
            if _looks_like_candidate_link(clean_text(label), href) and href not in candidate_urls:
                candidate_urls.append(href)

    # Каталоги просматриваются независимо от даты публикации. На карточке
    # акции дата может отсутствовать; её период проверяется позднее по правилам.
    # Срез в 35 ссылок не может служить доказательством полного охвата.
    link_limit = 35
    exhausted_limit = len(candidate_urls) > link_limit
    fetch_errors = 0
    for url in candidate_urls[:link_limit]:
        if url in seen_urls:
            continue
        seen_urls.add(url)

        try:
            text, soup, final_url = _fetch_document(url)
        except Exception:
            fetch_errors += 1
            continue

        if len(text) < 100:
            fetch_errors += 1
            continue

        low = text.lower()
        if not any(x in low for x in PROMO_HINTS):
            continue
        if not any(x in low for x in BANKING_HINTS):
            continue

        if soup is not None:
            published = _extract_published_at_html(soup, final_url)
        else:
            explicit = re.search(
                r"(?:Дата публикации|Дата размещения|Опубликовано)\s*[:\-]?\s*"
                r"(\d{1,2}[./]\d{1,2}[./]20\d{2}|\d{1,2}\s+[а-яё]+\s+20\d{2})",
                text[:8000],
                re.IGNORECASE,
            )
            published = _parse_datetime_value(explicit.group(1)) if explicit else _parse_datetime_value(final_url)

        # Сроки акции определяет evaluator. published_at=None честно
        # обозначает отсутствие подтверждённой даты публикации на сайте.
        # НЕ заменяем эту дату временем сканирования или началом недели.
        links = []
        if soup is not None:
            for a in soup.select("a[href]"):
                href = a.get("href")
                if href:
                    absolute = urljoin(final_url, href)
                    if absolute not in links:
                        links.append(absolute)

        items.append(
            RawItem(
                bank=bank,
                source_id=source["id"],
                source_type="web",
                published_at=published,
                text=text,
                url=final_url,
                external_links=links,
            )
        )

    # Даже HTTP 200 и извлечённые карточки не означают полного охвата.
    # Ошибки части карточек и ограничение обхода считаются неполной проверкой.
    if exhausted_limit or fetch_errors:
        status = "limited"
        error = f"Catalog traversal incomplete: {fetch_errors} failed pages; {len(candidate_urls)} links (cap {link_limit})"
    elif not items:
        status = "unverified_zero"
        error = "No campaign candidates extracted; coverage cannot be certified"
    else:
        status = "ok"
        error = ""
    return items, SourceCheck(
        bank=bank,
        source_id=source["id"],
        source_type="web",
        source_value=root_url,
        status=status,
        required=required,
        item_count=len(items),
        error=error,
    )


def collect_previous_week(recovery_days: int = 7) -> tuple[datetime, datetime, list[RawItem], list[SourceCheck]]:
    start, end = previous_calendar_week()
    scan_start = start - timedelta(days=recovery_days)
    items: list[RawItem] = []
    checks: list[SourceCheck] = []

    for bank_entry in BANK_SOURCES:
        bank = bank_entry["bank"]
        for source in bank_entry["sources"]:
            if source["type"] == "telegram":
                source_items, check = fetch_telegram_source(bank, source, scan_start, end)
            elif source["type"] == "web":
                source_items, check = fetch_web_source(bank, source, scan_start, end)
            else:
                source_items = []
                check = SourceCheck(
                    bank=bank,
                    source_id=source["id"],
                    source_type=source["type"],
                    source_value=source["value"],
                    status="unsupported",
                    required=source.get("required", True),
                )

            items.extend(source_items)
            checks.append(check)

    return start, end, items, checks
