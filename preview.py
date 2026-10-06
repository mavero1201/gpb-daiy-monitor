from __future__ import annotations

from html import escape

from main import send_telegram
from pipeline import run_pipeline, write_audit
from sources import BANKS


def card(item, result) -> str:
    return (
        f"<b>{escape(item.bank)} - {escape(result.title)}</b>\n"
        f"<b>Вознаграждение:</b> {escape(result.reward)}\n"
        f"<b>Условия:</b> {escape(result.conditions)}\n"
        f"<b>Механика:</b> {escape(result.mechanic)}; {escape(result.goal)}\n"
        f"<b>Срок акции:</b> {result.promo_start:%d.%m.%Y} - {result.promo_end:%d.%m.%Y}\n"
        f"<b>Источник:</b> <a href=\"{escape(result.evidence_url or item.url, quote=True)}\">ссылка на акцию</a>"
    )


def main() -> None:
    start, end, evaluated, source_checks = run_pipeline()
    write_audit(start, end, evaluated, source_checks)

    included_by_bank = {bank: [] for bank in BANKS}
    for item, result in evaluated:
        if result.included:
            included_by_bank[item.bank].append(card(item, result))

    source_gaps = {}
    for check in source_checks:
        if check.status != "ok":
            source_gaps.setdefault(check.bank, []).append(check.source_id)

    blocks = [
        "📌 <b>Мониторинг акций Daily Banking</b>",
        f"<b>Новые акции, опубликованные за неделю:</b> {start:%d.%m.%Y} - {end:%d.%m.%Y}",
    ]

    for bank in BANKS:
        blocks.extend(included_by_bank[bank])

    fully_checked = []
    incomplete_check = []
    for bank in BANKS:
        bank_checks = [check for check in source_checks if check.bank == bank]
        if bank_checks and all(check.status == "ok" for check in bank_checks):
            fully_checked.append(bank)
        else:
            incomplete_check.append(bank)

    no_actions = [
        bank for bank in fully_checked
        if not included_by_bank[bank]
    ]
    if no_actions:
        blocks.append(
            "<b>Подходящих подтверждённых акций не найдено:</b> "
            + ", ".join(escape(x) for x in no_actions)
        )

    if source_gaps:
        affected = ", ".join(
            f"{escape(bank)} ({', '.join(escape(x) for x in ids)})"
            for bank, ids in source_gaps.items()
        )
        blocks.append(
            "<b>Проверка не завершена по всем источникам:</b> " + affected
        )

    full = "\n\n".join(blocks)

    if len(full) <= 4000:
        send_telegram(full)
        return

    parts = []
    current_part = blocks[0] + "\n" + blocks[1]
    for block in blocks[2:]:
        candidate = current_part + "\n\n" + block
        if len(candidate) > 3900:
            parts.append(current_part)
            current_part = block
        else:
            current_part = candidate
    if current_part:
        parts.append(current_part)

    for i, part in enumerate(parts, 1):
        prefix = "" if len(parts) == 1 else f"<b>Часть {i}/{len(parts)}</b>\n"
        send_telegram(prefix + part)


if __name__ == "__main__":
    main()
