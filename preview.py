from __future__ import annotations

import re

from collector import Candidate, collect_previous_week
from main import send_telegram

MAX_SUMMARY = 340


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def clean_piece(text: str, limit: int = MAX_SUMMARY) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def classify_goal(text: str) -> str:
    low = text.lower()

    if any(x in low for x in ("новым клиент", "новые клиенты", "впервые", "оформите карту", "закажите карту")):
        return "Привлечение новых клиентов"

    if any(x in low for x in ("осаго", "каско", "страхован", "подключите", "оформите ")) and "карт" not in low:
        return "Cross-sell"

    return "Транзакционная активность текущих клиентов"


def extract_reward(text: str) -> str:
    for sentence in sentences(text):
        low = sentence.lower()
        if any(x in low for x in ("кешбэк", "кэшбэк", "бонус", "розыгрыш", "подар", "приз", "скидк", "промокод")):
            if re.search(r"\d|%|₽|руб|балл", sentence, re.IGNORECASE):
                return clean_piece(sentence, 240)

    return "Вознаграждение есть, точный размер в публикации не выделен."


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

    if selected:
        return clean_piece(" ".join(selected))

    return clean_piece(sentences(text)[0] if sentences(text) else text)


def extract_dates(text: str) -> str:
    patterns = [
        r"\bс\s+\d{1,2}(?:\.\d{1,2}(?:\.\d{2,4})?)?\s+по\s+\d{1,2}(?:\.\d{1,2}(?:\.\d{2,4})?)?\b",
        r"\bдо\s+\d{1,2}\s+[а-яё]+(?:\s+\d{4})?\b",
        r"\bс\s+\d{1,2}\s+[а-яё]+(?:\s+по\s+\d{1,2}\s+[а-яё]+)?(?:\s+\d{4})?\b",
        r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\s*[-–—]\s*\d{1,2}\.\d{1,2}\.\d{2,4}\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)

    return "Не указан в публикации"


def make_title(item: Candidate) -> str:
    for sentence in sentences(item.text):
        low = sentence.lower()
        if any(x in low for x in ("кешбэк", "кэшбэк", "розыгрыш", "бонус", "скидк", "промокод", "подар", "приз")):
            title = re.sub(r"^[^\wА-Яа-яЁё0-9]+", "", sentence)
            return clean_piece(title, 105)

    return clean_piece(sentences(item.text)[0] if sentences(item.text) else "Новая акция", 105)


def card(item: Candidate) -> str:
    return (
        f"<b>{item.bank} - {make_title(item)}</b>\n\n"
        f"<b>Цель:</b> {classify_goal(item.text)}\n"
        f"<b>Вознаграждение:</b> {extract_reward(item.text)}\n"
        f"<b>Механика:</b> {extract_mechanics(item.text)}\n"
        f"<b>Срок акции:</b> {extract_dates(item.text)}\n"
        f"<b>Источник:</b> <a href=\"{item.url}\">официальная публикация</a>"
    )


def main() -> None:
    start, end, found, errors = collect_previous_week()

    send_telegram(
        f"📌 <b>Мониторинг акций Daily Banking</b>\n"
        f"<b>Период:</b> {start:%d.%m.%Y} - {end:%d.%m.%Y}\n\n"
        "В выпуск включены новые промо-механики за прошедшую календарную неделю."
    )

    for bank, candidates in found.items():
        if candidates:
            for item in candidates:
                send_telegram(card(item))
        elif bank in errors:
            send_telegram(
                f"<b>{bank}</b>\n"
                "Источник не удалось проверить автоматически. "
                "Банк требует ручной проверки в этом выпуске."
            )
        else:
            send_telegram(
                f"<b>{bank}</b>\n"
                f"За период {start:%d.%m} - {end:%d.%m.%Y} "
                "подходящих новых акций для мониторинга не найдено."
            )


if __name__ == "__main__":
    main()
