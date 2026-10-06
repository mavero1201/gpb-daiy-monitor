from collector import collect_previous_week
from main import send_telegram

MAX_SNIPPET = 700


def compact(text: str) -> str:
    if len(text) <= MAX_SNIPPET:
        return text
    return text[: MAX_SNIPPET - 1].rstrip() + "…"


def chunks(lines: list[str], limit: int = 3800) -> list[str]:
    messages = []
    current = ""

    for line in lines:
        candidate = current + ("\n" if current else "") + line
        if len(candidate) > limit and current:
            messages.append(current)
            current = line
        else:
            current = candidate

    if current:
        messages.append(current)
    return messages


def main() -> None:
    start, end, found, errors = collect_previous_week()

    lines = [
        "🧪 ЧЕРНОВИК МОНИТОРИНГА DAILY BANKING",
        f"Период: {start:%d.%m.%Y} - {end:%d.%m.%Y}",
        "",
        "Первый автоматический слой: официальные Telegram-каналы банков.",
        "Это список кандидатов для проверки, а не финальный выпуск.",
        "",
    ]

    total = 0
    for bank, candidates in found.items():
        lines.append(f"🏦 {bank}")
        if not candidates:
            if bank in errors:
                lines.append(f"⚠️ Источник не удалось проверить: {errors[bank]}")
            else:
                lines.append("Кандидаты по Telegram за период не найдены.")
            lines.append("")
            continue

        total += len(candidates)
        for item in candidates:
            lines.append(f"• {item.published_at:%d.%m %H:%M} - {compact(item.text)}")
            lines.append(item.url)
        lines.append("")

    lines.insert(3, f"Найдено кандидатов: {total}")

    for message in chunks(lines):
        send_telegram(message)


if __name__ == "__main__":
    main()
