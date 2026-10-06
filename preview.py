from __future__ import annotations

from html import escape

from main import send_telegram
from pipeline import run_pipeline, write_audit
from sources import BANKS


def card(item, result) -> str:
    return (
        f"<b>{escape(result.title)}</b>\n"
        f"<b>Вознаграждение</b> - {escape(result.reward)}\n"
        f"<b>Условия</b> - {escape(result.conditions)}\n"
        f"<b>Механика</b> - {escape(result.mechanic)}\n"
        f"<b>Цель</b> - {escape(result.goal)}\n"
        f"<b>Срок акции</b> - {result.promo_start:%d.%m.%Y} - {result.promo_end:%d.%m.%Y}\n"
        f"<a href=\"{escape(result.evidence_url or item.url, quote=True)}\">Источник</a>"
    )


def main() -> None:
    start, end, evaluated, source_checks = run_pipeline()
    write_audit(start, end, evaluated, source_checks)

    included_by_bank = {bank: [] for bank in BANKS}
    for item, result in evaluated:
        if result.included:
            included_by_bank[item.bank].append(card(item, result))

    blocks = [
        "<b>Мониторинг акций Daily Banking</b>",
        f"{start:%d.%m.%Y} - {end:%d.%m.%Y}",
    ]

    for bank in BANKS:
        cards = included_by_bank[bank]
        if not cards:
            continue

        bank_block = [f"<b>{escape(bank)}</b>"]
        bank_block.extend(cards)
        blocks.append("\n\n".join(bank_block))

    fully_checked = []
    for bank in BANKS:
        checks = [check for check in source_checks if check.bank == bank]
        if checks and all(check.status == "ok" for check in checks):
            fully_checked.append(bank)

    no_actions = [
        bank for bank in fully_checked
        if not included_by_bank[bank]
    ]
    if no_actions:
        blocks.append(
            "<i>Без новых подтверждённых акций за неделю: "
            + ", ".join(escape(bank) for bank in no_actions)
            + ".</i>"
        )

    if len(blocks) == 2:
        blocks.append("Подтверждённых новых акций за неделю не найдено.")

    full = "\n\n".join(blocks)

    if len(full) <= 4000:
        send_telegram(full)
        return

    parts = []
    current = blocks[0] + "\n" + blocks[1]
    for block in blocks[2:]:
        candidate = current + "\n\n" + block
        if len(candidate) > 3900:
            parts.append(current)
            current = block
        else:
            current = candidate
    if current:
        parts.append(current)

    for i, part in enumerate(parts, 1):
        prefix = "" if len(parts) == 1 else f"<b>{i}/{len(parts)}</b>\n"
        send_telegram(prefix + part)


if __name__ == "__main__":
    main()
