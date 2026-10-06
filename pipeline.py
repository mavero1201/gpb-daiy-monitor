from __future__ import annotations

import csv
import json
from pathlib import Path

from collector import collect_previous_week
from evaluator import evaluate
from sources import BANKS

ARTIFACT_DIR = Path("artifacts")


def run_pipeline():
    start, end, raw_items, source_checks = collect_previous_week()
    evaluated = [(item, evaluate(item)) for item in raw_items]
    return start, end, evaluated, source_checks


def write_audit(start, end, evaluated, source_checks):
    ARTIFACT_DIR.mkdir(exist_ok=True)
    period_key = f"{start:%Y-%m-%d}_{end:%Y-%m-%d}"

    item_path = ARTIFACT_DIR / f"audit_items_{period_key}.csv"
    with item_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "bank", "source_id", "published_at", "url", "included", "reason",
            "promo_start", "promo_end", "title",
        ])
        for item, result in evaluated:
            writer.writerow([
                item.bank,
                item.source_id,
                item.published_at.isoformat(),
                item.url,
                result.included,
                result.reason,
                result.promo_start.isoformat() if result.promo_start else "",
                result.promo_end.isoformat() if result.promo_end else "",
                result.title,
            ])

    source_path = ARTIFACT_DIR / f"audit_sources_{period_key}.csv"
    with source_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["bank", "source_id", "type", "value", "status", "item_count", "error"])
        for check in source_checks:
            writer.writerow([
                check.bank,
                check.source_id,
                check.source_type,
                check.source_value,
                check.status,
                check.item_count,
                check.error,
            ])

    summary = {}
    for bank in BANKS:
        bank_items = [(i, r) for i, r in evaluated if i.bank == bank]
        checks = [c for c in source_checks if c.bank == bank]
        summary[bank] = {
            "raw_items": len(bank_items),
            "included": sum(1 for _, r in bank_items if r.included),
            "rejected": sum(1 for _, r in bank_items if not r.included),
            "sources": [
                {
                    "id": c.source_id,
                    "type": c.source_type,
                    "status": c.status,
                    "item_count": c.item_count,
                    "error": c.error,
                }
                for c in checks
            ],
        }

    summary_path = ARTIFACT_DIR / f"audit_summary_{period_key}.json"
    summary_path.write_text(
        json.dumps(
            {
                "period_start": start.date().isoformat(),
                "period_end": end.date().isoformat(),
                "raw_items": len(evaluated),
                "included": sum(1 for _, r in evaluated if r.included),
                "banks": summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return [item_path, source_path, summary_path]
