from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse, urljoin
import re

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from collector import RawItem, clean_text, _fetch_document
from sources import official_link_priority

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
    # Только явные клиентские действия по продукту/транзакции.
    # Нельзя использовать существительные вроде "покупки"/"перевод" или
    # общее "участвовать": иначе в Daily Banking попадают конкурсы и
    # нефинансовые промо, где эти слова встречаются лишь в описании приза.
    "оформ", "закаж", "соверш", "оплат", "покупайт", "купит",
    "попол", "снимайт", "снять", "перевед", "подключ", "активир",
    "откро",
)

ACTION_PATTERNS = (
    r"\b(?:зайдите|заходите)\s+в\s+(?:мобильное\s+)?(?:приложение|интернет-банк)",
    r"\bзарегистриру\w*\s+(?:в|на)\s+(?:акци\w*|программ\w*)",
    r"\bвыберите\s+(?:категори\w*|предложени\w*|кешбэк\w*|кэшбэк\w*)",
    r"\bиспользуйте\s+промокод",
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
    # Узкие сегменты вне mass-market Daily Banking.
    "военная пенсия", "военной пенсии", "военную пенсию", "военных пенсион",
)

RULE_LINK_HINTS = (
    "правил", "услов", "rule", "rules", "terms", "promo", "action",
    "cashback", "bonus", "offer", "document", "docs", ".pdf",
)

EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]")


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


def tidy(text: str) -> str:
    text = EMOJI_RE.sub("", text)
    text = clean_text(text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip(" -–—")


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", tidy(text))
    return [p.strip() for p in parts if p.strip()]


def has_customer_action(text: str) -> bool:
    low = tidy(text).lower()
    if any(signal in low for signal in ACTION_SIGNALS):
        return True
    return any(re.search(pattern, low, re.IGNORECASE) for pattern in ACTION_PATTERNS)


def is_external_link(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return bool(host) and "t.me" not in host and "telegram.me" not in host


def fetch_page_text(url: str) -> str:
    try:
        kwargs = {
            "timeout": 20,
            "headers": {"User-Agent": "Mozilla/5.0 GPB-Daily-Monitor/3.1"},
            "allow_redirects": True,
        }
        try:
            response = requests.get(url, **kwargs)
        except requests.exceptions.SSLError:
            response = requests.get(url, verify=False, **kwargs)
        response.raise_for_status()
        if "text/html" not in response.headers.get("content-type", "").lower():
            return ""
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return clean_text(soup.get_text(" ", strip=True))[:40000]
    except Exception:
        try:
            response = requests.get(
                "https://r.jina.ai/" + url,
                timeout=45,
                headers={
                    "User-Agent": "Mozilla/5.0 GPB-Daily-Monitor/3.2",
                    "Accept": "text/plain",
                },
            )
            response.raise_for_status()
            return clean_text(response.text)[:40000]
        except Exception:
            return ""


def build_evidence(item: RawItem) -> tuple[str, str]:
    parts = [item.text]
    evidence_url = item.url
    checked = 0
    links = [
        link for link in item.external_links
        if is_external_link(link)
    ]
    links.sort(key=lambda link: official_link_priority(item.bank, link))

    for link in links:
        page_text = fetch_page_text(link)
        if page_text:
            parts.append(page_text)
            evidence_url = link
            checked += 1
        if checked >= 3:
            break
    return clean_text(" ".join(parts)), evidence_url


def _rule_link_priority(bank: str, url: str) -> tuple[int, int]:
    low = (url or "").lower()
    has_rule_hint = any(hint in low for hint in RULE_LINK_HINTS)
    return (0 if has_rule_hint else 1, official_link_priority(bank, url))


def recheck_exact_period(
    item: RawItem,
    base_evidence: str,
    base_url: str,
) -> tuple[tuple[date, date] | None, str, str]:
    """Targeted second pass for promo-like posts without a confirmed full period.

    We follow more external/rules links than the normal evaluator and one nested
    level of likely rules/documents. A promo remains excluded unless an exact
    start and end date are found in the official evidence.
    """
    queue = [
        link for link in item.external_links
        if is_external_link(link)
    ]
    queue = sorted(dict.fromkeys(queue), key=lambda url: _rule_link_priority(item.bank, url))

    seen: set[str] = set()
    checked = 0
    evidence = base_evidence
    evidence_url = base_url

    while queue and checked < 8:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)

        try:
            page_text, soup, final_url = _fetch_document(url)
        except Exception:
            continue

        checked += 1
        if page_text:
            combined = clean_text(f"{evidence} {page_text}")
            period = extract_period(combined, item.published_at.date())
            if period:
                return period, combined, final_url or url
            evidence = combined
            evidence_url = final_url or url

        nested_links: list[str] = []
        if soup is not None:
            for tag in soup.select("a[href]"):
                href = tag.get("href") or ""
                if not href:
                    continue
                nested_links.append(urljoin(final_url or url, href))
        elif page_text:
            nested_links.extend(
                href.rstrip(".,;")
                for _, href in re.findall(
                    r"\[([^\]]*)\]\((https?://[^)\s]+)\)",
                    page_text,
                )
            )

        for link in nested_links:
            if not is_external_link(link) or link in seen or link in queue:
                continue
            low = link.lower()
            if any(hint in low for hint in RULE_LINK_HINTS):
                queue.append(link)

        queue.sort(key=lambda link: _rule_link_priority(item.bank, link))

    return None, evidence, evidence_url


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


def find_amount(text: str) -> str:
    match = re.search(r"\b\d[\d\s]{0,12}\s*(?:₽|руб(?:лей|ля|ль|\.)?)", text, re.IGNORECASE)
    return tidy(match.group(0)) if match else ""


def make_title(post_text: str, bank: str) -> str:
    text = tidy(post_text)
    low = text.lower()

    if "золот" in low and "яблок" in low and "50%" in low.replace(" ", ""):
        return "50% кешбэка в «Золотом Яблоке»"

    if "steam" in low and ("розыгрыш" in low or "разыгрыв" in low):
        amount = find_amount(text)
        return f"Розыгрыш {amount} за пополнение Steam" if amount else "Розыгрыш за пополнение Steam"

    if "apple id" in low and ("скидк" in low or "промокод" in low):
        pct = re.search(r"\b\d{1,3}\s*%", text)
        return f"Скидка {tidy(pct.group(0))} на пополнение Apple ID" if pct else "Скидка на пополнение Apple ID"

    for sentence in sentences(text):
        if any(x in sentence.lower() for x in PROMO_SIGNALS):
            sentence = re.sub(r"^(дарим|получайте|получите)\s+", "", sentence, flags=re.IGNORECASE)
            return tidy(sentence)

    return f"Акция {bank}"


def extract_reward(post_text: str, evidence_text: str, bank: str) -> str:
    post = tidy(post_text)
    low = post.lower()

    if "золот" in low and "яблок" in low:
        pct = re.search(r"\b\d{1,3}\s*%", post)
        cap = re.search(r"максимальн\w*[^\d]{0,50}(\d[\d\s]*\s*₽)", post, re.IGNORECASE)
        if pct:
            result = f"{tidy(pct.group(0))} кешбэка"
            if cap:
                result += f", максимум {tidy(cap.group(1))}"
            return result

    if "steam" in low and ("розыгрыш" in low or "разыгрыв" in low):
        if bank == "МТС Банк":
            main_prize = re.search(r"главн\w*\s+приз[^\d]{0,40}(\d[\d\s]*\s*₽)", post, re.IGNORECASE)
            if main_prize:
                return f"Главный приз - {tidy(main_prize.group(1))}"
        prize_fund = re.search(r"призов\w*\s+фонд\w*[^\d]{0,30}(\d[\d\s]*\s*₽)", post, re.IGNORECASE)
        if prize_fund:
            return f"Призовой фонд {tidy(prize_fund.group(1))}"
        amount = find_amount(post)
        if amount:
            return f"Приз {amount}"

    if "apple id" in low:
        pct = re.search(r"\b\d{1,3}\s*%", post)
        if pct:
            return f"Скидка {tidy(pct.group(0))}"

    for source in (post, evidence_text):
        for sentence in sentences(source):
            low_sentence = sentence.lower()
            if any(x in low_sentence for x in ("кешбэк", "кэшбэк", "бонус", "розыгрыш", "подар", "приз", "скидк")):
                if re.search(r"\d|%|₽|руб|балл", sentence, re.IGNORECASE):
                    return tidy(sentence)
    return ""


def extract_conditions(post_text: str, evidence_text: str, bank: str) -> str:
    post = tidy(post_text)
    low = post.lower()

    if "золот" in low and "яблок" in low:
        amount = re.search(r"от\s+(\d[\d\s]*\s*₽)", post, re.IGNORECASE)
        result = "Оплатить покупку в «Золотом Яблоке» картой «Мир» Газпромбанка"
        if amount:
            result += f" на сумму {tidy(amount.group(0))}"
        return result + "."

    if "steam" in low:
        amount = re.search(r"от\s+(\d[\d\s]*\s*₽)", post, re.IGNORECASE)
        if bank == "Т-Банк":
            result = "Пополнить Steam через приложение Т-Банка"
            if amount:
                result += f" на сумму {tidy(amount.group(0))} одной транзакцией"
            return result + "."
        if bank == "МТС Банк":
            result = "Пополнить Steam через МТС Оплату"
            if amount:
                result += f" на сумму {tidy(amount.group(0))}"
            return result + "."

    if "apple id" in low:
        result = "Оплатить пополнение Apple ID ОТП Картой"
        if "промокод" in low:
            result += " с промокодом из условий акции"
        return result + "."

    for pattern in (
        r"(Чтобы участвовать[^.!?]*[.!?]?)",
        r"(Оплатите[^.!?]*[.!?]?)",
        r"(Оплатить[^.!?]*[.!?]?)",
        r"(Совершите[^.!?]*[.!?]?)",
        r"(Оформите[^.!?]*[.!?]?)",
        r"(Пополните[^.!?]*[.!?]?)",
        r"(Снимите[^.!?]*[.!?]?)",
        r"(Активируйте[^.!?]*[.!?]?)",
        r"(Зарегистрируйтесь[^.!?]*[.!?]?)",
        r"(Зайдите[^.!?]*[.!?]?)",
        r"(Заходите[^.!?]*[.!?]?)",
        r"(Выберите[^.!?]*[.!?]?)",
        r"(Используйте\s+промокод[^.!?]*[.!?]?)",
    ):
        match = re.search(pattern, post, re.IGNORECASE)
        if match:
            return tidy(match.group(1))

    for sentence in sentences(evidence_text):
        if has_customer_action(sentence):
            return tidy(sentence)
    return ""


def classify_goal(post_text: str) -> str:
    low = tidy(post_text).lower()
    if any(x in low for x in ("новым клиент", "новые клиенты", "новым владельц", "впервые оформ")):
        return "привлечение новых клиентов"
    return "транзакционная активность текущих клиентов"


def classify_mechanic(post_text: str) -> str:
    low = tidy(post_text).lower()
    if "розыгрыш" in low or "разыгрыв" in low:
        return "розыгрыш"
    if "кешбэк" in low or "кэшбэк" in low:
        return "кешбэк"
    if "скидк" in low or "промокод" in low:
        return "скидка / промокод"
    if "реферал" in low or "пригласите друга" in low or "рекомендац" in low:
        return "реферальная программа"
    if "бонус" in low or "балл" in low:
        return "бонусы"
    return "промо-механика"


def evaluate(item: RawItem) -> Evaluation:
    post_low = item.text.lower()

    if any(x in post_low for x in EXCLUDE_KEYWORDS):
        return Evaluation(False, "excluded_segment")
    if not any(x in post_low for x in PROMO_SIGNALS):
        return Evaluation(False, "no_promo_signal")
    if not any(x in post_low for x in BANKING_CONTEXT):
        return Evaluation(False, "no_banking_context")
    if not has_customer_action(item.text):
        return Evaluation(False, "no_customer_action")

    evidence, evidence_url = build_evidence(item)

    period = extract_period(evidence, item.published_at.date())

    # Однодневная акция с формулировкой "сегодня/только сегодня" имеет
    # однозначный срок, так как дата публикации известна.
    if not period and re.search(
        r"\b(?:только\s+)?сегодня\b|\bдо\s+конца\s+дня\b",
        item.text,
        re.IGNORECASE,
    ):
        period = (item.published_at.date(), item.published_at.date())

    if not period:
        period, evidence, evidence_url = recheck_exact_period(
            item,
            evidence,
            evidence_url,
        )

    if not period:
        return Evaluation(
            False,
            "no_exact_period_after_recheck",
            evidence_url=evidence_url,
        )

    reward = extract_reward(item.text, evidence, item.bank)
    if not reward:
        return Evaluation(False, "no_reward", evidence_url=evidence_url)

    conditions = extract_conditions(item.text, evidence, item.bank)
    if not conditions:
        return Evaluation(False, "no_conditions", evidence_url=evidence_url)

    start, end = period
    if end < item.published_at.date():
        return Evaluation(False, "period_ended_before_publication", evidence_url=evidence_url)

    return Evaluation(
        True,
        "included",
        title=make_title(item.text, item.bank),
        goal=classify_goal(item.text),
        mechanic=classify_mechanic(item.text),
        reward=reward,
        conditions=conditions,
        promo_start=start,
        promo_end=end,
        evidence_url=evidence_url,
    )
