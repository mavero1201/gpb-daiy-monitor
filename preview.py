from __future__ import annotations

from html import escape
import os
from pathlib import Path

from main import send_telegram
from review_report import write_review_report
from collector import previous_calendar_week
from pipeline import (
    load_state,
    run_pipeline,
    save_state,
    update_state_after_publish,
    write_audit,
)
from sources import BANKS, bank_fully_checked, strict_coverage_failures


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
    republish = os.getenv("REPUBLISH_WEEK") == "1"
    force_run = os.getenv("FORCE_RUN") == "1" or republish
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
    ) = run_pipeline(republish_current_week=republish)

    write_audit(start, end, evaluated, source_checks)
    report_path = write_review_report(Path('artifacts'), start.date(), end.date())
    print(f'REVIEW REPORT: {report_path}')
    review_count = sum(1 for _, result in evaluated if result.reason in {
        "no_exact_period_after_recheck", "quality_unstructured_card",
        "quality_irrelevant_text", "quality_mechanic_mismatch",
        "quality_unverified_reward", "quality_unknown_mechanic",
        "quality_no_bank_product_link", "quality_single_day_requires_review",
        "quality_missing_required_field", "quality_invalid_source",
        "no_reward", "no_conditions",
        "deadline_only_needs_start", "activity_month_only_needs_terms",
        "multiple_offers_require_split",
    })

    strict_sources = os.getenv("STRICT_SOURCES") == "1"
    coverage_failures = strict_coverage_failures(source_checks)
    if strict_sources and coverage_failures:
        raise RuntimeError(
            "Automatic publication stopped because required source coverage failed: "
            + ", ".join(coverage_failures)
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

    fully_checked = [
        bank for bank in BANKS
        if bank_fully_checked(bank, source_checks)
    ]

    no_actions = [
        bank for bank in fully_checked
        if not included_by_bank[bank]
    ]
    if no_actions:
        blocks.append(
            "<i>Нет допущенных к публикации предложений за неделю: "
            + ", ".join(escape(bank) for bank in no_actions)
            + ".</i>"
        )

    if review_count and os.getenv("PUBLISH_TO_TELEGRAM") != "1":
        blocks.append(f"<i>Требуют дополнительной проверки: {review_count}. См. review_queue в архиве запуска. Это не означает отсутствие акций.</i>")

    if len(blocks) == 2:
        blocks.append("Нет предложений, прошедших проверку для публикации.")

    full = "\n\n".join(blocks)

    # Always save the exact publication candidate for review.
    preview_path = Path("artifacts") / f"preview_{start:%Y-%m-%d}_{end:%Y-%m-%d}.html"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_text(full, encoding="utf-8")
    if os.getenv("PUBLISH_TO_TELEGRAM") != "1":
        print(f"PREVIEW ONLY: {preview_path}. No Telegram messages sent; publication state unchanged.")
        return

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
