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
        if pid in sent and not (republish_current_week and result.promo_start is not None and start.date() <= result.promo_start <= end.date()):
            result.included = False
            result.reason = "already_published"
            continue

        # Правило выпуска: учитываем ПЕРВЫЙ ДЕНЬ участия, а не день
        # публикации сообщения / документа и не факт действия на неделе.
        # Повторный сбор старых публикаций не создаёт новое предложение.
        if result.promo_start is None or result.promo_end is None:
            result.included = False
            result.reason = "missing_verified_campaign_period"
            continue

        if not (start.date() <= result.promo_start <= end.date()):
            result.included = False
            result.reason = "outside_launch_week"
            continue

        if result.promo_end < result.promo_start:
            result.included = False
            result.reason = "invalid_campaign_period"
            continue

        publish_items.append((item, result, pid, False))

    return start, end, evaluated, source_checks, publish_items, recovered_items, state


def update_state_after_publish(state: dict, start, end, published_items) -> dict:
    sent = state.setdefault("sent_promos", {})

    for item, result, pid, recovered in published_items:
        sent[pid] = {
            "bank": item.bank,
            "title": result.title,
            "publication_date": item.published_at.date().isoformat() if item.published_at else None,
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
                item.published_at.isoformat() if item.published_at else "",
                item.url,
                result.included,
                result.reason,
                result.promo_start.isoformat() if result.promo_start else "",
                result.promo_end.isoformat() if result.promo_end else "",
                result.title,
            ])

    # Full forensic journal: every extracted source record BEFORE evaluating
    # whether it matches Daily Banking. No silent disappearance on rejection.
    raw_path = ARTIFACT_DIR / f"raw_source_items_{period_key}.csv"
    with raw_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "bank", "source_id", "source_type", "published_at",
            "source_url", "raw_text", "raw_html", "external_links",
            "evaluation_stage", "decision_reason", "promo_start",
            "promo_end", "date_status", "date_evidence", "evidence_url",
        ])
        for item, result in evaluated:
            writer.writerow([
                item.bank, item.source_id, item.source_type,
                item.published_at.isoformat() if item.published_at else "",
                item.url, item.text, getattr(item, "raw_html", ""),
                json.dumps(item.external_links, ensure_ascii=False),
                "approved_for_publication" if result.included else "rejected_after_collection",
                result.reason,
                result.promo_start.isoformat() if result.promo_start else "",
                result.promo_end.isoformat() if result.promo_end else "",
                getattr(result, "date_status", ""),
                getattr(result, "date_evidence", ""),
                getattr(result, "evidence_url", ""),
            ])

    # Separate source-discovery index also records documents skipped by the
    # crawler cap or excluded by pre-evaluation keyword filters.
    catalog_path = ARTIFACT_DIR / f"catalog_discovery_{period_key}.csv"
    with catalog_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "bank", "source_id", "source_status", "url",
            "discovery_stage", "link_label", "date_hint_unverified",
            "final_url", "error", "source_text_excerpt",
        ])
        for check in source_checks:
            for entry in getattr(check, "catalog_index", []):
                writer.writerow([
                    check.bank, check.source_id, check.status,
                    entry.get("url", ""), entry.get("stage", ""),
                    entry.get("link_label", ""),
                    entry.get("date_hint_unverified", ""),
                    entry.get("final_url", ""),
                    entry.get("error", ""),
                    entry.get("source_text_excerpt", ""),
                ])

    # Stable weekly input for Sabina's monthly report. Unlike the Telegram
    # message, this file preserves a machine-readable campaign identity and
    # NEVER labels an evaluated candidate as already delivered.
    week_registry_path = ARTIFACT_DIR / f"weekly_campaign_registry_{period_key}.csv"
    with week_registry_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "campaign_id", "start_week", "end_week", "bank", "campaign_name",
            "campaign_start", "campaign_end", "source_publication_date",
            "reward", "conditions", "mechanic", "goal",
            "source_url", "source_id", "review_status",
        ])
        for item, result in evaluated:
            if not result.included or not result.promo_start:
                continue
            if not (start.date() <= result.promo_start <= end.date()):
                continue
            writer.writerow([
                promo_id(item, result),
                start.date().isoformat(), end.date().isoformat(),
                item.bank, result.title,
                result.promo_start.isoformat(),
                result.promo_end.isoformat() if result.promo_end else "",
                item.published_at.date().isoformat() if item.published_at else "",
                result.reward, result.conditions, result.mechanic,
                getattr(result, "goal", ""), result.evidence_url or item.url,
                item.source_id, "eligible_not_delivery_confirmed",
            ])

    review_reasons = {
        "no_exact_period_after_recheck", "quality_unstructured_card",
        "quality_irrelevant_text", "quality_mechanic_mismatch",
        "quality_unverified_reward", "quality_unknown_mechanic",
        "quality_no_bank_product_link", "quality_single_day_requires_review",
        "quality_missing_required_field", "quality_invalid_source",
        "no_reward", "no_conditions",
        "deadline_only_needs_start", "activity_month_only_needs_terms",
        "multiple_offers_require_split",
    }
    review_path = ARTIFACT_DIR / f"review_queue_{period_key}.csv"
    with review_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["bank", "source_id", "published_at", "url", "reason",
                         "title", "reward", "conditions", "mechanic",
                         "promo_start", "promo_end", "date_status",
                         "date_evidence", "evidence_url", "source_text"])
        for item, result in evaluated:
            if result.reason not in review_reasons:
                continue
            writer.writerow([
                item.bank, item.source_id, item.published_at.isoformat() if item.published_at else "",
                item.url, result.reason, result.title, result.reward,
                result.conditions, result.mechanic,
                result.promo_start.isoformat() if result.promo_start else "",
                result.promo_end.isoformat() if result.promo_end else "",
                result.date_status, result.date_evidence,
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

    return [item_path, source_path, summary_path, review_path, raw_path, catalog_path, week_registry_path]
