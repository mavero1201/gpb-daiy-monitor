from __future__ import annotations

from calendar import monthrange
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

PROMO_WORDS = (
    "кешбэк", "кэшбэк", "розыгрыш", "бонус", "скидк", "промокод",
    "подар", "приз", "вернём", "вернем",
)

ACTION_WORDS = (
    "оформ", "закаж", "соверш", "оплат", "покуп", "попол", "сняти", "снять",
    "перевод", "подключ", "активир", "зарегистр", "участв", "чтобы",
)


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [re.sub(r"\s+", " ", p).strip() for p in parts if p.strip()]


def classify_goal(text: str) -> str:
    low = text.lower()
    if any(x in low for x in ("новым клиент", "новые клиенты", "новым владельц", "впервые оформ")):
        return "привлечение новых клиентов"
    if any(x in low for x in ("осаго", "каско", "страхован", "подписк", "накопительн")):
        return "cross-sell / развитие использования продуктов"
    return "транзакционная активность текущих клиентов"


def classify_mechanic(text: str) -> str:
    low = text.lower()
    mechanics = []
    if "розыгрыш" in low or "разыгрыв" in low:
        mechanics.append("розыгрыш")
    if "реферал" in low or "пригласите друга" in low or "рекомендац" in low:
        mechanics.append("реферальная программа")
    if "кешбэк" in low or "кэшбэк" in low:
        mechanics.append("кешбэк")
    if "скидк" in low or "промокод" in low:
        mechanics.append("скидка / промокод")
    if "бонус" in low or "балл" in low:
        mechanics.append("бонусы")
    return ", ".join(dict.fromkeys(mechanics)) or "промо-механика"


def make_title(item: Candidate) -> str:
    # Заголовок не обрезаем: пользователь должен видеть полное название/суть акции.
    for sentence in sentences(item.text):
        if any(word in sentence.lower() for word in PROMO_WORDS):
            return re.sub(r"^[^\wА-Яа-яЁё0-9]+", "", sentence).strip()
    return sentences(item.text)[0] if sentences(item.text) else "Новая акция"


def reward_sentence(text: str) -> str:
    ranked = []
    for sentence in sentences(text):
        low = sentence.lower()
        if any(x in low for x in PROMO_WORDS) and re.search(r"\d|%|₽|руб|балл", sentence, re.IGNORECASE):
            score = 0
            if "%" in sentence or "₽" in sentence or "руб" in low:
                score += 2
            if "максим" in low or "призовой фонд" in low:
                score += 1
            ranked.append((score, sentence))
    if not ranked:
        return ""
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1]


def conditions_sentence(text: str, excluded: set[str]) -> str:
    picked = []
    for sentence in sentences(text):
        if sentence in excluded:
            continue
        low = sentence.lower()
        if any(word in low for word in ACTION_WORDS):
            picked.append(sentence)
        if len(picked) == 2:
            break
    return " ".join(picked)


def description_sentence(text: str, excluded: set[str]) -> str:
    # Описание отвечает на "что это за предложение / для кого", а не повторяет выгоду.
    for sentence in sentences(text):
        if sentence in excluded:
            continue
        low = sentence.lower()
        if any(
            marker in low
            for marker in (
                "для новых", "для действующих", "все владельцы", "владельц",
                "клиент", "участник", "карта", "сервис", "предложение",
            )
        ):
            return sentence

    for sentence in sentences(text):
        if sentence not in excluded:
            return sentence
    return ""


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


def extract_promo_period(text: str, publication_date: date) -> tuple[date, date] | None:
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
            return start, end

    month_names = "|".join(MONTHS.keys())

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
            return start, end

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
            return start, end

    # "с 28 сентября по 4 октября" - год берём из даты публикации.
    cross_month_no_year = re.search(
        rf"с\s+(\d{{1,2}})\s+({month_names})\s+по\s+"
        rf"(\d{{1,2}})\s+({month_names})(?!\s+\d{{4}})",
        text,
        re.IGNORECASE,
    )
    if cross_month_no_year:
        year = publication_date.year
        start = date(year, MONTHS[cross_month_no_year.group(2).lower()], int(cross_month_no_year.group(1)))
        end = date(year, MONTHS[cross_month_no_year.group(4).lower()], int(cross_month_no_year.group(3)))
        if start <= end:
            return start, end

    same_month = re.search(
        rf"(?:с\s+)?(\d{{1,2}})\s*(?:-|–|—|по)\s*(\d{{1,2}})\s+({month_names})(?:\s+(\d{{4}}))?",
        text,
        re.IGNORECASE,
    )
    if same_month:
        year = int(same_month.group(4)) if same_month.group(4) else publication_date.year
        month = MONTHS[same_month.group(3).lower()]
        start = date(year, month, int(same_month.group(1)))
        end = date(year, month, int(same_month.group(2)))
        if start <= end:
            return start, end

    # "весь октябрь" / "в течение октября" - нормализуем до календарных границ месяца.
    whole_month = re.search(
        rf"(?:весь|всю|в\s+течение)\s+({month_names})",
        text,
        re.IGNORECASE,
    )
    if whole_month:
        month = MONTHS[whole_month.group(1).lower()]
        year = publication_date.year
        return date(year, month, 1), date(year, month, monthrange(year, month)[1])

    return None


def verified_card(item: Candidate) -> str | None:
    evidence = item.validation_text or item.text
    period = extract_promo_period(evidence, item.published_at.date())
    reward = reward_sentence(evidence)

    if not period or not reward:
        return None

    start, end = period

    # Отсеиваем старые/нерелевантные страницы: акция не может уже закончиться
    # к моменту публикации, которая привела нас к ней.
    if end < item.published_at.date():
        return None

    title = make_title(item)
    excluded = {title, reward}
    conditions = conditions_sentence(evidence, excluded)
    if not conditions:
        return None
    excluded.add(conditions)
    description = description_sentence(evidence, excluded)

    return (
        f"<b>{escape(item.bank)} - {escape(title)}</b>\n"
        f"<b>Опубликовано:</b> {item.published_at:%d.%m.%Y}\n"
        f"<b>Описание:</b> {escape(description) if description else 'Промо-предложение банка.'}\n"
        f"<b>Цель:</b> {escape(classify_goal(evidence))}\n"
        f"<b>Механика:</b> {escape(classify_mechanic(evidence))}\n"
        f"<b>Вознаграждение:</b> {escape(reward)}\n"
        f"<b>Условия:</b> {escape(conditions)}\n"
        f"<b>Срок акции:</b> {format_period(start, end)}\n"
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

    header = (
        "📌 <b>Мониторинг акций Daily Banking</b>\n"
        f"<b>Новые акции, опубликованные за неделю:</b> {start:%d.%m.%Y} - {end:%d.%m.%Y}"
    )

    footer = []
    if no_actions:
        footer.append(
            "<b>Подходящих подтверждённых акций не найдено:</b> "
            + ", ".join(escape(x) for x in no_actions)
        )
    if manual_check:
        footer.append(
            "<b>Не удалось проверить автоматически:</b> "
            + ", ".join(escape(x) for x in manual_check)
        )

    blocks = [header]
    if cards:
        blocks.extend(cards)
    else:
        blocks.append("Подтверждённых новых акций за неделю не найдено.")
    blocks.extend(footer)

    # Одно полотно - приоритет. Telegram допускает 4096 символов.
    full_message = "\n\n".join(blocks)
    if len(full_message) <= 4000:
        send_telegram(full_message)
        return

    # Если физически не помещается, делим только по карточкам, не по банкам.
    parts = []
    current = header
    for block in blocks[1:]:
        candidate = current + "\n\n" + block
        if len(candidate) > 3900 and current != header:
            parts.append(current)
            current = block
        else:
            current = candidate
    if current:
        parts.append(current)

    for i, part in enumerate(parts, start=1):
        prefix = "" if len(parts) == 1 else f"<b>Часть {i}/{len(parts)}</b>\n"
        send_telegram(prefix + part)


if __name__ == "__main__":
    main()
