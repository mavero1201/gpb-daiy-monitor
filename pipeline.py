from __future__ import annotations

import csv
import json
from pathlib import Path
import re

from collector import collect_previous_week
from evaluator import evaluate
from sources import BANKS

ARTIFACT_DIR = Path("artifacts")


def _reward_fingerprint(text: str) -> tuple[str, ...]:
    values = re.findall(r"\d[\d\s]*(?:%|₽|руб(?:лей|ля|ль|\.)?)", text.lower())
    return tuple(re.sub(r"\s+", "", value) for value in values)


def _duplicate_key(item, result):
    if not result.included:
        return None
    return (
        item.bank,
        result.promo_start,
        result.promo_end,
        result.mechanic,
        _reward_fingerprint(result.reward),
    )


def _mark_duplicates(evaluated):
    # Telegram и сайт могут привести к одной и той же акции.
    # В audit сохраняем оба обнаружения, но в выпуск пропускаем одно.
    seen = {}
    for item, result in evaluated:
        key = _duplicate_key(item, result)
        if key is None:
            continue

        if key not in seen:
            seen[key] = (item, result)
            continue

        first_item, first_result = seen[key]

        # При равных данных предпочитаем карточку из Telegram:
        # обычно там чище название, а условия уже могут быть верифицированы
        # через официальный сайт по внешней ссылке.
        if first_item.source_type == "web" and item.source_type == "telegram":
            first_result.included = False
            first_result.reason = "duplicate"
            seen[key] = (item, result)
        else:
            result.included = False
            result.reason = "duplicate"


def run_pipeline():
    start, end, raw_items, source_checks = collect_previous_week()
    evaluated = [(item, evaluate(item)) for item in raw_items]
    _mark_duplicates(evaluated)
    return start, end, evaluated, source_checks


def write_audit(start, end, evaluated, source_checks):
    ARTIFACT_DIR.mkdir(exist_ok=True)
    period_key = f"{start:%Y-%m-%d}_{end:%Y-%m-%d}"

    item_path = ARTIFACT_DIR / f"audit_items_{period_key}.csv"
    with item_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "bank", "source_id", "source_type", "published_at", "url",
            "included", "reason", "promo_start", "promo_end", "title",
        ])
        for item, result in evaluated:
            writer.writerow([
                item.bank,
                item.source_id,
                item.source_type,
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
        writer.writerow(["bank", "source_id", "type", "value", "required", "status", "item_count", "error"])
        for check in source_checks:
            writer.writerow([
                check.bank,
                check.source_id,
                check.source_type,
                check.source_value,
                check.required,
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
                    "required": c.required,
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
