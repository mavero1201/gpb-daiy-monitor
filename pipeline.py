from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re
from datetime import timedelta

from collector import collect_previous_week
from evaluator import evaluate
from quality import validate_card
from sources import BANKS

ARTIFACT_DIR = Path("artifacts")
STATE_PATH = Path("data/state.json")


def _normalize(value: str) -> str:
    return re.sub(r"\W+", " ", (value or "").lower()).strip()


def _reward_fingerprint(text: str) -> tuple[str, ...]:
    values = re.findall(r"\d[\d\s]*(?:%|₽|руб(?:лей|ля|ль|\.)?)", (text or "").lower())
    return tuple(re.sub(r"\s+", "", value) for value in values)


def promo_id(item, result) -> str:
    payload = "|".join([
        item.bank,
        _normalize(result.title),
        str(result.promo_start or ""),
        str(result.promo_end or ""),
        result.mechanic or "",
        ",".join(_reward_fingerprint(result.reward)),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {
            "last_successful_period_start": None,
            "last_successful_period_end": None,
            "sent_promos": {},
        }

    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    data.setdefault("last_successful_period_start", None)
    data.setdefault("last_successful_period_end", None)
    data.setdefault("sent_promos", {})
    return data


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
    seen = {}
    for item, result in evaluated:
        key = _duplicate_key(item, result)
        if key is None:
            continue

        if key not in seen:
            seen[key] = (item, result)
            continue

        first_item, first_result = seen[key]

        if first_item.source_type == "web" and item.source_type == "telegram":
            first_result.included = False
            first_result.reason = "duplicate"
            seen[key] = (item, result)
        else:
            result.included = False
            result.reason = "duplicate"


def run_pipeline(republish_current_week: bool = False):
    start, end, raw_items, source_checks = collect_previous_week(recovery_days=7)
    evaluated = [(item, evaluate(item)) for item in raw_items]
    for item, result in evaluated:
        reason = validate_card(item, result)
        if reason:
            result.included = False
            result.reason = reason
    _mark_duplicates(evaluated)

    state = load_state()
    sent = state.get("sent_promos", {})
    has_publication_history = bool(state.get("last_successful_period_start"))
    recovery_start = (start - timedelta(days=7)).date()
    recovery_end = (start - timedelta(days=1)).date()

    publish_items = []
    recovered_items = []

    for item, result in evaluated:
        if not result.included:
            continue

        pid = promo_id(item, result)
        if pid in sent and not (republish_current_week and start.date() <= item.published_at.date() <= end.date()):
            result.included = False
            result.reason = "already_published"
            continue

        publication_day = item.published_at.date()

        if start.date() <= publication_day <= end.date():
            publish_items.append((item, result, pid, False))
            continue

        # Всегда перепроверяем ровно одну предыдущую календарную неделю,
        # если у мониторинга уже есть история публикаций. Это позволяет
        # подхватить акцию, которую прошлый выпуск не смог подтвердить,
        # даже если после этого уже был опубликован пустой текущий выпуск.
        if (
            has_publication_history
            and not republish_current_week
            and recovery_start <= publication_day <= recovery_end
        ):
            recovered_items.append((item, result, pid, True))
            continue

        result.included = False
        result.reason = "outside_current_or_recovery_period"

    return start, end, evaluated, source_checks, publish_items, recovered_items, state


def update_state_after_publish(state: dict, start, end, published_items) -> dict:
    sent = state.setdefault("sent_promos", {})

    for item, result, pid, recovered in published_items:
        sent[pid] = {
            "bank": item.bank,
            "title": result.title,
            "publication_date": item.published_at.date().isoformat(),
            "promo_start": result.promo_start.isoformat() if result.promo_start else None,
            "promo_end": result.promo_end.isoformat() if result.promo_end else None,
            "source_url": result.evidence_url or item.url,
            "recovered": recovered,
        }

    state["last_successful_period_start"] = start.date().isoformat()
    state["last_successful_period_end"] = end.date().isoformat()
    return state


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

    review_reasons = {
        "no_exact_period_after_recheck", "quality_unstructured_card",
        "quality_irrelevant_text", "quality_mechanic_mismatch",
        "quality_unverified_reward", "quality_unknown_mechanic",
        "quality_no_bank_product_link", "quality_single_day_requires_review",
        "quality_missing_required_field", "quality_invalid_source",
        "no_reward", "no_conditions",
    }
    review_path = ARTIFACT_DIR / f"review_queue_{period_key}.csv"
    with review_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["bank", "source_id", "published_at", "url", "reason",
                         "title", "reward", "conditions", "mechanic",
                         "promo_start", "promo_end", "evidence_url", "source_text"])
        for item, result in evaluated:
            if result.reason not in review_reasons:
                continue
            writer.writerow([
                item.bank, item.source_id, item.published_at.isoformat(),
                item.url, result.reason, result.title, result.reward,
                result.conditions, result.mechanic,
                result.promo_start.isoformat() if result.promo_start else "",
                result.promo_end.isoformat() if result.promo_end else "",
                result.evidence_url, item.text,
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
                "requires_review": sum(1 for _, r in evaluated if r.reason in review_reasons),
                "banks": summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return [item_path, source_path, summary_path, review_path]
