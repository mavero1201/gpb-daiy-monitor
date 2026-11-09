"""Unattended Monday publisher for source-verified Daily Banking promotions.

The collector runs from the tested engine directory, while writable publication
markers and state live in the main GitHub checkout. No messages on dry runs.
"""
from __future__ import annotations

from datetime import date
from html import escape
import json
from pathlib import Path
import re
import subprocess

from collector import previous_calendar_week
from main import send_telegram
from pipeline import (
    load_state, run_pipeline, save_state,
    update_state_after_publish, write_audit,
)
from preview import card
from sources import BANKS, strict_coverage_failures

MIN_WEEK_START = date(2026, 11, 9)
SENT_DIR = Path("data/weekly_auto_sent")
MANUAL_DIR = Path("data/manual_publications")
REPORT_DIR = Path("artifacts")
MAX_MESSAGE_LENGTH = 3900
TARGET_BODY_LENGTH = 3550


def _manual_publication_overlaps(start: date, end: date) -> bool:
    """Fail closed if an earlier manual issue covers part of this week."""
    if not MANUAL_DIR.exists():
        return False
    for path in MANUAL_DIR.glob("*.sent"):
        match = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})", path.name)
        if not match:
            continue
        try:
            other_start, other_end = map(date.fromisoformat, match.groups())
        except ValueError:
            continue
        if other_start <= end and other_end >= start:
            return True
    return False


def _ordered(items):
    position = {bank: index for index, bank in enumerate(BANKS)}
    return sorted(items, key=lambda p: (
        position.get(p[0].bank, len(BANKS)),
        p[1].promo_start,
        p[1].title,
    ))


def build_pages(items, start: date, end: date, *, limited_coverage: bool):
    """Split only between complete HTML cards and repeat the weekly heading."""
    if not items:
        return []
    header = (
        "📌 <b>Мониторинг банковских акций Daily Banking</b>\n"
        f"<b>{start:%d.%m.%Y} - {end:%d.%m.%Y}</b>"
    )
    disclaimer = (
        "\n\n<i>Проверенные предложения из доступных открытых источников. "
        "Часть источников недоступна, возможны пропуски.</i>"
        if limited_coverage else ""
    )

    pages = []
    current = []
    current_ids = []
    last_bank = None

    def flush():
        nonlocal current, current_ids, last_bank
        if current:
            pages.append((header + "\n\n" + "\n\n".join(current), list(current_ids)))
        current = []
        current_ids = []
        last_bank = None

    for item, result, pid, recovered in _ordered(items):
        formatted = card(item, result, recovered=False)
        card_block = (
            f"<b>{escape(item.bank)}</b>\n\n{formatted}"
            if item.bank != last_bank else formatted
        )
        proposed = header + "\n\n" + "\n\n".join(current + [card_block])
        if len(proposed) > TARGET_BODY_LENGTH and current:
            flush()
            card_block = f"<b>{escape(item.bank)}</b>\n\n{formatted}"
            proposed = header + "\n\n" + card_block
        if len(proposed) > TARGET_BODY_LENGTH:
            raise ValueError("Individual verified card exceeds safe Telegram size")
        current.append(card_block)
        current_ids.append(pid)
        last_bank = item.bank
    flush()

    if disclaimer:
        body, ids = pages[-1]
        if len(body) + len(disclaimer) <= MAX_MESSAGE_LENGTH:
            pages[-1] = (body + disclaimer, ids)
        else:
            pages.append((header + disclaimer, []))
    for body, _ in pages:
        if len(body) > MAX_MESSAGE_LENGTH:
            raise ValueError("Telegram page exceeds safe length")
    return pages


def _commit_progress(path: Path):
    subprocess.run(["git", "add", str(path), "data/state.json"], check=True)
    subprocess.run(
        ["git", "commit", "-m", f"Record auto Daily Banking publication {path.stem}"],
        check=True,
    )
    subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)


def main(*, publish: bool = False) -> None:
    start_dt, end_dt = previous_calendar_week()
    start, end = start_dt.date(), end_dt.date()
    if start < MIN_WEEK_START:
        print("Unattended mode not active for historical periods; skip.")
        return
    marker = SENT_DIR / f"{start}_{end}.json"
    if marker.exists():
        progress = json.loads(marker.read_text(encoding="utf-8"))
        if progress.get("complete"):
            print(f"Weekly issue {start} to {end} already delivered. Skip.")
            return
    else:
        progress = {"start": str(start), "end": str(end), "sent_ids": [], "complete": False}

    if _manual_publication_overlaps(start, end):
        print("Manual publication overlaps this reporting week. No duplicate send.")
        return

    actual_start, actual_end, evaluated, checks, matches, recovered, state = run_pipeline()
    if actual_start.date() != start or actual_end.date() != end:
        raise RuntimeError("Reporting week changed during collection")
    write_audit(actual_start, actual_end, evaluated, checks)
    failures = strict_coverage_failures(checks)
    print(f"Coverage exceptions: {len(failures)}; {failures}")

    included = []
    already_sent = set(progress["sent_ids"])
    for item, result, pid, recovered_flag in matches + recovered:
        if pid in already_sent:
            continue
        if result.promo_start is None or not start <= result.promo_start <= end:
            raise RuntimeError("Campaign with unverified start or outside week")
        if result.promo_end is None or result.promo_end < result.promo_start:
            raise RuntimeError("Campaign has invalid end date")
        included.append((item, result, pid, recovered_flag))

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / f"weekly_auto_summary_{start}_{end}.json"
    report.write_text(
        json.dumps({
            "period": [str(start), str(end)],
            "confirmed_cards": len(included),
            "coverage_failures": failures,
            "published": False,
            "note": "Only evidence-complete offers. Other material stays in audit."
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not included:
        print("No fully verified new offers. Do not publish empty digest.")
        return

    pages = build_pages(included, start, end, limited_coverage=bool(failures))
    for index, (body, ids) in enumerate(pages, 1):
        (REPORT_DIR / f"weekly_auto_{start}_{end}_part{index}.html").write_text(
            body, encoding="utf-8"
        )
    if not publish:
        print(f"DRY RUN: {len(included)} cards / {len(pages)} parts; no Telegram send.")
        return

    marker.parent.mkdir(parents=True, exist_ok=True)
    by_id = {row[2]: row for row in included}
    for index, (body, ids) in enumerate(pages, 1):
        if ids and all(pid in progress["sent_ids"] for pid in ids):
            continue
        send_telegram(body)
        progress["sent_ids"] = sorted(set(progress["sent_ids"]) | set(ids))
        progress["complete"] = index == len(pages)
        marker.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if ids:
            state = update_state_after_publish(
                state, actual_start, actual_end,
                [by_id[pid] for pid in ids],
            )
            if index != len(pages):
                state["last_successful_period_start"] = None
                state["last_successful_period_end"] = None
            save_state(state)
        elif index == len(pages):
            state["last_successful_period_start"] = start.isoformat()
            state["last_successful_period_end"] = end.isoformat()
            save_state(state)
        _commit_progress(marker)
    print(f"SENT: {len(included)} reviewed new campaigns in {len(pages)} messages.")


if __name__ == "__main__":
    import os
    main(publish=os.getenv("AUTO_PUBLISH_TO_TELEGRAM", "0") == "1")
