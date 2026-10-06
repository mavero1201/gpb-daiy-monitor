from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse
import re

import requests
from bs4 import BeautifulSoup

from collector import RawItem, clean_text

MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

PROMO_SIGNALS = (
    "акци", "кешбэк", "кэшбэк", "бонус", "розыгрыш", "подар",
    "скидк", "промокод", "выигра", "приз", "вернем", "вернём",
)
ACTION_SIGNALS = (
    "оформ", "закаж", "соверш", "оплат", "покуп", "попол", "сняти",
    "снять", "перевод", "подключ", "активир", "зарегистр", "участв",
)
BANKING_CONTEXT = (
    "карт", "дебетов", "счет", "счёт", "платеж", "оплат", "покуп",
    "перевод", "попол", "сняти", "банкомат", "кешбэк", "кэшбэк",
    "балл", "кошелек", "кошелёк", "вклад", "страхован", "осаго",
    "каско", "pay", "пэй",
)
EXCLUDE_KEYWORDS = (
    "детская карта", "детской карт", "детских карт", "для детей",
    "альфа-картах для детей", "premium", "private banking", "премиальн",
)


@dataclass
class Evaluation:
    included: bool
    reason: str
    title: str = ""
    goal: str = ""
    mechanic: str = ""
    reward: str = ""
    conditions: str = ""
    promo_start: date | None = None
    promo_end: date | None = None
    evidence_url: str = ""


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", clean_text(text))
    return [p.strip() for p in parts if p.strip()]


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
            headers={"User-Agent": "Mozilla/5.0 GPB-Daily-Monitor/2.0"},
            allow_redirects=True,
        )
        response.raise_for_status()
        if "text/html" not in response.headers.get("content-type", "").lower():
            return ""
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return clean_text(soup.get_text(" ", strip=True))[:40000]
    except Exception:
        return ""


def build_evidence(item: RawItem) -> tuple[str, str]:
    parts = [item.text]
    evidence_url = item.url
    checked = 0
    for link in item.external_links:
        if not is_external_link(link):
            continue
        page_text = fetch_page_text(link)
        if page_text:
            parts.append(page_text)
            evidence_url = link
            checked += 1
        if checked >= 3:
            break
    return clean_text(" ".join(parts)), evidence_url


def parse_numeric_date(day: str, month: str, year: str) -> date | None:
    try:
        y = int(year)
        if y < 100:
            y += 2000
        return date(y, int(month), int(day))
    except ValueError:
        return None


def extract_period(text: str, publication_date: date) -> tuple[date, date] | None:
    numeric = re.search(
        r"(?:с\s*)?(\d{1,2})[./](\d{1,2})[./](\d{2,4})\s*(?:-|–|—|по)\s*"
        r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})",
        text, re.IGNORECASE,
    )
    if numeric:
        start = parse_numeric_date(numeric.group(1), numeric.group(2), numeric.group(3))
        end = parse_numeric_date(numeric.group(4), numeric.group(5), numeric.group(6))
        if start and end and start <= end:
            return start, end

    month_names = "|".join(MONTHS.keys())

    full_words = re.search(
        rf"с\s+(\d{{1,2}})\s+({month_names})\s+(\d{{4}})\s+по\s+"
        rf"(\d{{1,2}})\s+({month_names})\s+(\d{{4}})",
        text, re.IGNORECASE,
    )
    if full_words:
        start = date(int(full_words.group(3)), MONTHS[full_words.group(2).lower()], int(full_words.group(1)))
        end = date(int(full_words.group(6)), MONTHS[full_words.group(5).lower()], int(full_words.group(4)))
        if start <= end:
            return start, end

    shared_year = re.search(
        rf"с\s+(\d{{1,2}})\s+({month_names})\s+по\s+"
        rf"(\d{{1,2}})\s+({month_names})\s+(\d{{4}})",
        text, re.IGNORECASE,
    )
    if shared_year:
        year = int(shared_year.group(5))
        start = date(year, MONTHS[shared_year.group(2).lower()], int(shared_year.group(1)))
        end = date(year, MONTHS[shared_year.group(4).lower()], int(shared_year.group(3)))
        if start <= end:
            return start, end

    cross_month = re.search(
        rf"с\s+(\d{{1,2}})\s+({month_names})\s+по\s+"
        rf"(\d{{1,2}})\s+({month_names})(?!\s+\d{{4}})",
        text, re.IGNORECASE,
    )
    if cross_month:
        year = publication_date.year
        start = date(year, MONTHS[cross_month.group(2).lower()], int(cross_month.group(1)))
        end = date(year, MONTHS[cross_month.group(4).lower()], int(cross_month.group(3)))
        if start <= end:
            return start, end

    same_month = re.search(
        rf"(?:с\s+)?(\d{{1,2}})\s*(?:-|–|—|по)\s*(\d{{1,2}})\s+"
        rf"({month_names})(?:\s+(\d{{4}}))?",
        text, re.IGNORECASE,
    )
    if same_month:
        year = int(same_month.group(4)) if same_month.group(4) else publication_date.year
        month = MONTHS[same_month.group(3).lower()]
        start = date(year, month, int(same_month.group(1)))
        end = date(year, month, int(same_month.group(2)))
        if start <= end:
            return start, end

    whole_month = re.search(
        rf"(?:весь|всю|в\s+течение)\s+({month_names})",
        text, re.IGNORECASE,
    )
    if whole_month:
        month = MONTHS[whole_month.group(1).lower()]
        year = publication_date.year
        return date(year, month, 1), date(year, month, monthrange(year, month)[1])

    return None


def extract_reward(text: str) -> str:
    for sentence in sentences(text):
        low = sentence.lower()
        if any(x in low for x in ("кешбэк", "кэшбэк", "бонус", "розыгрыш", "подар", "приз", "скидк", "промокод")):
            if re.search(r"\d|%|₽|руб|балл", sentence, re.IGNORECASE):
                return sentence
    return ""


def extract_conditions(text: str) -> str:
    picked = []
    for sentence in sentences(text):
        low = sentence.lower()
        if any(x in low for x in ACTION_SIGNALS):
            picked.append(sentence)
        if len(picked) == 2:
            break
    return " ".join(picked)


def make_title(text: str) -> str:
    steam = re.search(r"(розыгрыш[^.!?]{0,120}Steam|Steam[^.!?]{0,120}розыгрыш)", text, re.IGNORECASE)
    if steam:
        reward = re.search(r"\d[\d\s]*\s*₽", steam.group(0))
        return f"Розыгрыш {reward.group(0)} за пополнение Steam" if reward else "Розыгрыш за пополнение Steam"
    for sentence in sentences(text):
        if any(x in sentence.lower() for x in PROMO_SIGNALS):
            return sentence
    return "Новая акция"


def classify_goal(text: str) -> str:
    low = text.lower()
    if any(x in low for x in ("новым клиент", "новые клиенты", "новым владельц", "впервые оформ")):
        return "привлечение новых клиентов"
    if any(x in low for x in ("осаго", "каско", "страхован", "подписк", "накопительн")):
        return "cross-sell / развитие использования продуктов"
    return "транзакционная активность текущих клиентов"


def classify_mechanic(text: str) -> str:
    low = text.lower()
    result = []
    if "розыгрыш" in low or "разыгрыв" in low:
        result.append("розыгрыш")
    if "реферал" in low or "пригласите друга" in low or "рекомендац" in low:
        result.append("реферальная программа")
    if "кешбэк" in low or "кэшбэк" in low:
        result.append("кешбэк")
    if "скидк" in low or "промокод" in low:
        result.append("скидка / промокод")
    if "бонус" in low or "балл" in low:
        result.append("бонусы")
    return ", ".join(dict.fromkeys(result)) or "промо-механика"


def evaluate(item: RawItem) -> Evaluation:
    low = item.text.lower()

    if any(x in low for x in EXCLUDE_KEYWORDS):
        return Evaluation(False, "excluded_segment")
    if not any(x in low for x in PROMO_SIGNALS):
        return Evaluation(False, "no_promo_signal")
    if not any(x in low for x in BANKING_CONTEXT):
        return Evaluation(False, "no_banking_context")
    if not any(x in low for x in ACTION_SIGNALS):
        return Evaluation(False, "no_customer_action")

    evidence, evidence_url = build_evidence(item)

    period = extract_period(evidence, item.published_at.date())
    if not period:
        return Evaluation(False, "no_exact_period", evidence_url=evidence_url)

    reward = extract_reward(evidence)
    if not reward:
        return Evaluation(False, "no_reward", evidence_url=evidence_url)

    conditions = extract_conditions(evidence)
    if not conditions:
        return Evaluation(False, "no_conditions", evidence_url=evidence_url)

    start, end = period
    if end < item.published_at.date():
        return Evaluation(False, "period_ended_before_publication", evidence_url=evidence_url)

    return Evaluation(
        True,
        "included",
        title=make_title(item.text),
        goal=classify_goal(evidence),
        mechanic=classify_mechanic(evidence),
        reward=reward,
        conditions=conditions,
        promo_start=start,
        promo_end=end,
        evidence_url=evidence_url,
    )
