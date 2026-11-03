"""Read-only twice-daily pilot: collect offers, audit coverage, NEVER publish.

Pilot dates are deliberately bounded. The existing weekly monitor and Telegram
publisher remain unchanged.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path

from collector import MOSCOW, collect_period
from evaluator import evaluate
from pipeline import _mark_duplicates, write_audit
from quality import validate_card
from sources import BANKS, strict_coverage_failures

PILOT_START = date(2026, 11, 3)
PILOT_END = date(2026, 11, 16)
ARTIFACT_DIR = Path("artifacts")

REVIEW_REASONS = {
    "no_exact_period_after_recheck", "no_reward", "no_conditions",
    "quality_single_day_requires_review", "deadline_only_needs_start",
    "activity_month_only_needs_terms", "multiple_offers_require_split",
    "quality_unstructured_card", "quality_irrelevant_text",
    "quality_mechanic_mismatch", "quality_unverified_reward",
    "quality_unknown_mechanic", "quality_no_bank_product_link",
    "quality_missing_required_field", "quality_invalid_source",
}


def reporting_window(now: datetime | None = None):
    now = now or datetime.now(MOSCOW)
    now = now.astimezone(MOSCOW)
    start = datetime.combine(now.date(), time.min, tzinfo=MOSCOW)
    return start, now


def main() -> None:
    start, end = reporting_window()
    if not PILOT_START <= end.date() <= PILOT_END:
        print("Daily Banking pilot is outside its approved 03-16 Nov date range; skip.")
        return

    print(f"Daily Banking diagnostic run: {start:%d.%m.%Y} {start:%H:%M} to {end:%H:%M} Moscow")
    print("NO TELEGRAM PUBLICATION / NO STATE CHANGES.")
    _, _, items, checks = collect_period(start, end, recovery_days=21)
    evaluated = [(item, evaluate(item)) for item in items]
    for item, result in evaluated:
        rejection = validate_card(item, result)
        if rejection:
            result.included = False
            result.reason = rejection
    _mark_duplicates(evaluated)

    for item, result in evaluated:
        if not result.included:
            continue
        # Calendar-day launch rule, NEVER publication day.
        if result.promo_start is None or not (
            start.date() <= result.promo_start <= end.date()
        ):
            result.included = False
            result.reason = "outside_launch_day"

    write_audit(start, end, evaluated, checks)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    key = end.strftime("%Y-%m-%d_%H%M")
    failures = strict_coverage_failures(checks)
    by_bank = {}
    for bank in BANKS:
        rows = [(item, result) for item, result in evaluated if item.bank == bank]
        sources = [check for check in checks if check.bank == bank]
        by_bank[bank] = {
            "collected_materials": len(rows),
            "algorithm_candidates": sum(1 for _, res in rows if res.included),
            "requires_manual_review": sum(1 for _, res in rows if res.reason in REVIEW_REASONS),
            "source_issues": [
                {"id": c.source_id, "status": c.status, "error": c.error}
                for c in sources if c.status != "ok"
            ],
        }

    manifest = {
        "pilot_window": [PILOT_START.isoformat(), PILOT_END.isoformat()],
        "audit_date": end.date().isoformat(),
        "audit_time_moscow": end.isoformat(),
        "published_to_telegram": False,
        "all_banks": len(BANKS),
        "collected_materials": len(evaluated),
        "algorithm_candidates": sum(1 for _, res in evaluated if res.included),
        "requires_manual_review": sum(1 for _, res in evaluated if res.reason in REVIEW_REASONS),
        "source_coverage_confirmed": len(failures) == 0,
        "required_source_failures": failures,
        "by_bank": by_bank,
        "reasons": dict(Counter(res.reason for _, res in evaluated)),
    }
    report_path = ARTIFACT_DIR / f"daily_pilot_{key}.json"
    report_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    queue_path = ARTIFACT_DIR / f"daily_candidates_{key}.csv"
    with queue_path.open("w", encoding="utf-8-sig", newline="") as file:
        out = csv.writer(file, delimiter=";")
        out.writerow([
            "bank", "status", "reason", "source_id", "published_at",
            "promo_start", "promo_end", "title", "reward", "conditions",
            "source_url", "source_excerpt",
        ])
        for item, res in evaluated:
            if not res.included and res.reason not in REVIEW_REASONS:
                continue
            out.writerow([
                item.bank,
                "algorithm_candidate" if res.included else "review",
                res.reason,
                item.source_id,
                item.published_at.isoformat() if item.published_at else "",
                res.promo_start.isoformat() if res.promo_start else "",
                res.promo_end.isoformat() if res.promo_end else "",
                res.title, res.reward, res.conditions,
                res.evidence_url or item.url, item.text[:900],
            ])
    print(f"Collected: {manifest['collected_materials']}, algorithm candidates: {manifest['algorithm_candidates']}, review: {manifest['requires_manual_review']}.")
    print(f"Required-source failures: {len(failures)}. These do not suppress the diagnostic audit.")
    print(f"Reports: {report_path}, {queue_path}")
    print("PILOT ONLY: no messages sent to Telegram.")


if __name__ == "__main__":
    main()
