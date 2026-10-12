from __future__ import annotations

from html import escape
import os

from main import send_telegram
from collector import previous_calendar_week
from pipeline import (
    load_state,
    run_pipeline,
    save_state,
    update_state_after_publish,
    write_audit,
)
from sources import BANKS


def card(item, result, recovered: bool = False) -> str:
    prefix = "<i>Пропущено в прошлом выпуске</i>\n" if recovered else ""
    return (
        prefix
        + f"<b>{escape(result.title)}</b>\n"
        + f"<b>Вознаграждение</b> - {escape(result.reward)}\n"
        + f"<b>Условия</b> - {escape(result.conditions)}\n"
        + f"<b>Механика</b> - {escape(result.mechanic)}\n"
        + f"<b>Цель</b> - {escape(result.goal)}\n"
        + f"<b>Срок акции</b> - {result.promo_start:%d.%m.%Y} - {result.promo_end:%d.%m.%Y}\n"
        + f"<a href=\"{escape(result.evidence_url or item.url, quote=True)}\">Источник</a>"
    )


def main() -> None:
    # Scheduled backup runs are idempotent: if this weekly period has already
    # been published successfully, exit before collecting/sending anything.
    # Manual workflow_dispatch remains force-enabled for diagnostics/recovery.
    force_run = os.getenv("FORCE_RUN") == "1"
    if not force_run:
        check_start, check_end = previous_calendar_week()
        current_state = load_state()
        if (
            current_state.get("last_successful_period_start") == check_start.date().isoformat()
            and current_state.get("last_successful_period_end") == check_end.date().isoformat()
        ):
            print(
                "Weekly period already published successfully: "
                f"{check_start:%Y-%m-%d} - {check_end:%Y-%m-%d}. Skip duplicate run."
            )
            return

    (
        start,
        end,
        evaluated,
        source_checks,
        publish_items,
        recovered_items,
        state,
    ) = run_pipeline()

    write_audit(start, end, evaluated, source_checks)

    strict_sources = os.getenv("STRICT_SOURCES") == "1"
    incomplete_required_sources = [
        check for check in source_checks
        if check.required and check.status != "ok"
    ]
    if strict_sources and incomplete_required_sources:
        details = ", ".join(
            f"{check.bank}:{check.source_id}:{check.status}"
            for check in incomplete_required_sources
        )
        raise RuntimeError(
            "Automatic publication stopped because required sources were not fully checked: "
            + details
        )

    included_by_bank = {bank: [] for bank in BANKS}

    for item, result, pid, recovered in publish_items + recovered_items:
        included_by_bank[item.bank].append(card(item, result, recovered))

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
        required_checks = [check for check in checks if check.required]
        if required_checks and all(check.status == "ok" for check in required_checks):
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
    else:
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

    all_published = publish_items + recovered_items
    new_state = update_state_after_publish(
        state,
        start,
        end,
        all_published,
    )
    save_state(new_state)


if __name__ == "__main__":
    main()
