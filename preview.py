from __future__ import annotations

from datetime import date
from html import escape
import re

from collector import Candidate, collect_previous_week
from main import send_telegram

MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def compact(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def classify_goal(text: str) -> str:
    low = text.lower()

    if any(x in low for x in ("новым клиент", "новые клиенты", "впервые", "оформите карту", "закажите карту")):
        return "привлечение новых клиентов"

    if any(x in low for x in ("осаго", "каско", "страхован", "подключите", "оформите ")) and "карт" not in low:
        return "cross-sell"

    return "транзакционная активность текущих клиентов"


def extract_reward(text: str) -> str:
    for sentence in sentences(text):
        low = sentence.lower()
        if any(x in low for x in ("кешбэк", "кэшбэк", "бонус", "розыгрыш", "подар", "приз", "скидк", "промокод")):
            if re.search(r"\d|%|₽|руб|балл", sentence, re.IGNORECASE):
                return compact(sentence, 190)
    return ""


def extract_mechanics(text: str) -> str:
    selected = []
    for sentence in sentences(text):
        low = sentence.lower()
        if any(
            x in low
            for x in (
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
                "чтобы",
            )
        ):
            selected.append(sentence)
        if len(selected) == 2:
            break
    return compact(" ".join(selected), 230) if selected else ""


def parse_numeric_date(day: str, month: str, year: str) -> date | None:
    try:
        y = int(year)
        if y < 100:
            y += 2000
        return date(y, int(month), int(day))
    except ValueError:
        return None


def format_period(start: date, end: date) -> str:
    return f"{start:%d.%m.%Y} - {end:%d.%m.%Y}"


def extract_promo_period(text: str) -> str | None:
    # 01.10.2026 - 31.10.2026 / с 01.10.2026 по 31.10.2026
    numeric = re.search(
        r"(?:с\s*)?(\d{1,2})[./](\d{1,2})[./](\d{2,4})\s*(?:-|–|—|по)\s*"
        r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})",
        text,
        re.IGNORECASE,
    )
    if numeric:
        start = parse_numeric_date(numeric.group(1), numeric.group(2), numeric.group(3))
        end = parse_numeric_date(numeric.group(4), numeric.group(5), numeric.group(6))
        if start and end and start <= end:
            return format_period(start, end)

    month_names = "|".join(MONTHS.keys())

    # с 1 октября 2026 по 31 октября 2026
    full_words = re.search(
        rf"с\s+(\d{{1,2}})\s+({month_names})\s+(\d{{4}})\s+по\s+"
        rf"(\d{{1,2}})\s+({month_names})\s+(\d{{4}})",
        text,
        re.IGNORECASE,
    )
    if full_words:
        start = date(int(full_words.group(3)), MONTHS[full_words.group(2).lower()], int(full_words.group(1)))
        end = date(int(full_words.group(6)), MONTHS[full_words.group(5).lower()], int(full_words.group(4)))
        if start <= end:
            return format_period(start, end)

    # с 1 октября по 31 октября 2026
    shared_year = re.search(
        rf"с\s+(\d{{1,2}})\s+({month_names})\s+по\s+"
        rf"(\d{{1,2}})\s+({month_names})\s+(\d{{4}})",
        text,
        re.IGNORECASE,
    )
    if shared_year:
        year = int(shared_year.group(5))
        start = date(year, MONTHS[shared_year.group(2).lower()], int(shared_year.group(1)))
        end = date(year, MONTHS[shared_year.group(4).lower()], int(shared_year.group(3)))
        if start <= end:
            return format_period(start, end)

    # с 1 по 4 октября 2026 / 1-4 октября 2026
    same_month = re.search(
        rf"(?:с\s+)?(\d{{1,2}})\s*(?:-|–|—|по)\s*(\d{{1,2}})\s+({month_names})\s+(\d{{4}})",
        text,
        re.IGNORECASE,
    )
    if same_month:
        year = int(same_month.group(4))
        month = MONTHS[same_month.group(3).lower()]
        start = date(year, month, int(same_month.group(1)))
        end = date(year, month, int(same_month.group(2)))
        if start <= end:
            return format_period(start, end)

    return None


def make_title(item: Candidate) -> str:
    for sentence in sentences(item.text):
        low = sentence.lower()
        if any(x in low for x in ("кешбэк", "кэшбэк", "розыгрыш", "бонус", "скидк", "промокод", "подар", "приз")):
            title = re.sub(r"^[^\wА-Яа-яЁё0-9]+", "", sentence)
            return compact(title, 90)
    return compact(sentences(item.text)[0] if sentences(item.text) else "Новая акция", 90)


def verified_card(item: Candidate) -> str | None:
    evidence = item.validation_text or item.text
    period = extract_promo_period(evidence)
    reward = extract_reward(evidence)
    mechanics = extract_mechanics(evidence)

    # Жёсткое правило мониторинга:
    # без подтверждённого полного срока акции, вознаграждения и механики
    # акция в Telegram-выпуск не попадает.
    if not period or not reward or not mechanics:
        return None

    return (
        f"<b>{escape(item.bank)} - {escape(make_title(item))}</b>\n"
        f"<b>Опубликовано:</b> {item.published_at:%d.%m.%Y}\n"
        f"<b>Цель:</b> {escape(classify_goal(evidence))}\n"
        f"<b>Вознаграждение:</b> {escape(reward)}\n"
        f"<b>Механика:</b> {escape(mechanics)}\n"
        f"<b>Срок акции:</b> {period}\n"
        f"<b>Источник:</b> <a href=\"{escape(item.url, quote=True)}\">ссылка на акцию</a>"
    )


def main() -> None:
    start, end, found, errors = collect_previous_week()

    cards = []
    no_actions = []
    manual_check = []

    for bank, candidates in found.items():
        verified = []
        for item in candidates:
            card = verified_card(item)
            if card:
                verified.append(card)
            else:
                print(f"REJECTED (insufficient verification): {bank} | {item.url}")

        if verified:
            cards.extend(verified)
        elif bank in errors:
            manual_check.append(bank)
        else:
            no_actions.append(bank)

    blocks = [
        "📌 <b>Мониторинг акций Daily Banking</b>",
        f"<b>Публикации за неделю:</b> {start:%d.%m.%Y} - {end:%d.%m.%Y}",
        "",
    ]

    if cards:
        blocks.append("\n\n".join(cards))
    else:
        blocks.append("Подтверждённых новых акций за неделю не найдено.")

    if no_actions:
        blocks.extend([
            "",
            "<b>Подходящих подтверждённых акций не найдено:</b>",
            ", ".join(escape(x) for x in no_actions),
        ])

    if manual_check:
        blocks.extend([
            "",
            "<b>Не удалось проверить автоматически:</b>",
            ", ".join(escape(x) for x in manual_check),
        ])

    message = "\n".join(blocks)

    # Telegram ограничивает одно сообщение 4096 символами.
    # Стремимся к одному посту; если лимит превышен, делим только по карточкам.
    if len(message) <= 4000:
        send_telegram(message)
        return

    header = "\n".join(blocks[:3])
    footer_parts = []
    if no_actions:
        footer_parts.append(
            "<b>Подходящих подтверждённых акций не найдено:</b> "
            + ", ".join(escape(x) for x in no_actions)
        )
    if manual_check:
        footer_parts.append(
            "<b>Не удалось проверить автоматически:</b> "
            + ", ".join(escape(x) for x in manual_check)
        )

    parts = []
    current = header
    for card in cards:
        candidate = current + "\n\n" + card
        if len(candidate) > 3900 and current != header:
            parts.append(current)
            current = card
        else:
            current = candidate

    if footer_parts:
        footer = "\n\n" + "\n".join(footer_parts)
        if len(current + footer) <= 4000:
            current += footer
        else:
            parts.append(current)
            current = "\n".join(footer_parts)

    if current:
        parts.append(current)

    for i, part in enumerate(parts, start=1):
        prefix = "" if len(parts) == 1 else f"<b>Часть {i}/{len(parts)}</b>\n"
        send_telegram(prefix + part)


if __name__ == "__main__":
    main()
