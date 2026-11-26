"""Regression protection for unattended weekly Telegram publication."""
import json
from datetime import date, datetime
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import weekly_auto_publish as w

MOSCOW = ZoneInfo("Europe/Moscow")


def make_offer(i=1, bank="ВТБ"):
    item = SimpleNamespace(
        bank=bank, source_type="telegram", source_id="vtb_tg",
        url=f"https://t.me/BankVTB/{i}", text="Оплатить картой ВТБ",
        published_at=datetime(2026, 11, 10, 12, 0, tzinfo=MOSCOW),
    )
    result = SimpleNamespace(
        title=f"Кешбэк на покупки №{i}", reward="10% кешбэка",
        conditions="Оплатить покупку картой банка", mechanic="кешбэк",
        goal="Увеличение транзакционной активности",
        promo_start=date(2026, 11, 10), promo_end=date(2026, 11, 15),
        evidence_url=f"https://www.vtb.ru/promo/{i}", included=True,
    )
    return item, result, f"id-{i}", False


class WeeklyAutoPublishTests(unittest.TestCase):
    def test_pages_split_without_cutting_cards_or_html(self):
        items = [make_offer(i) for i in range(1, 18)]
        pages = w.build_pages(
            items, date(2026, 11, 9), date(2026, 11, 15), limited_coverage=True
        )
        self.assertGreater(len(pages), 1)
        self.assertEqual(17, sum(len(ids) for _, ids in pages))
        for body, ids in pages:
            self.assertLessEqual(len(body), w.MAX_MESSAGE_LENGTH)
            self.assertIn("09.11.2026 - 15.11.2026", body)
            self.assertEqual(body.count("<b>Срок акции</b>"), len(ids))
        self.assertIn("возможны пропуски", pages[-1][0])

    def test_one_card_no_extra_source_note_when_all_checked(self):
        pages = w.build_pages(
            [make_offer()], date(2026, 11, 9), date(2026, 11, 15),
            limited_coverage=False,
        )
        self.assertEqual(1, len(pages))
        self.assertNotIn("возможны пропуски", pages[0][0])

    def test_manual_publication_overlap_prevents_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "2026-11-03_2026-11-05.sent"
            path.write_text("already sent", encoding="utf-8")
            with patch.object(w, "MANUAL_DIR", Path(folder)):
                self.assertTrue(w._manual_publication_overlaps(
                    date(2026, 11, 2), date(2026, 11, 8)
                ))
                self.assertFalse(w._manual_publication_overlaps(
                    date(2026, 11, 9), date(2026, 11, 15)
                ))

    def test_existing_complete_delivery_skips_collection_and_send(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            markers = root / "delivery"
            markers.mkdir()
            path = markers / "2026-11-09_2026-11-15.json"
            path.write_text(json.dumps({"complete": True, "sent_ids": ["id-1"]}))
            start = datetime(2026, 11, 9, 0, 0, tzinfo=MOSCOW)
            end = datetime(2026, 11, 15, 23, 59, tzinfo=MOSCOW)
            with patch.object(w, "SENT_DIR", markers), \
                 patch.object(w, "previous_calendar_week", return_value=(start,end)), \
                 patch.object(w, "run_pipeline") as collect, \
                 patch.object(w, "send_telegram") as send:
                w.main(publish=True)
            collect.assert_not_called()
            send.assert_not_called()

    def test_zero_verified_offers_never_post_or_mark_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            start = datetime(2026, 11, 9, 0, 0, tzinfo=MOSCOW)
            end = datetime(2026, 11, 15, 23, 59, tzinfo=MOSCOW)
            state = {"sent_promos": {}, "last_successful_period_start": None}
            with patch.object(w, "SENT_DIR", root / "markers"), \
                 patch.object(w, "MANUAL_DIR", root / "manual"), \
                 patch.object(w, "REPORT_DIR", root / "reports"), \
                 patch.object(w, "previous_calendar_week", return_value=(start,end)), \
                 patch.object(w, "run_pipeline", return_value=(start,end,[],[],[],[],state)), \
                 patch.object(w, "write_audit"), \
                 patch.object(w, "strict_coverage_failures", return_value=["ПСБ:unavailable"]), \
                 patch.object(w, "send_telegram") as send:
                w.main(publish=True)
            send.assert_not_called()
            self.assertFalse((root / "markers").exists())

    def test_verified_offer_publishes_once_and_records_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            start = datetime(2026, 11, 9, 0, 0, tzinfo=MOSCOW)
            end = datetime(2026, 11, 15, 23, 59, tzinfo=MOSCOW)
            state = {"sent_promos": {}, "last_successful_period_start": None}
            with patch.object(w, "SENT_DIR", root / "markers"), \
                 patch.object(w, "MANUAL_DIR", root / "manual"), \
                 patch.object(w, "REPORT_DIR", root / "reports"), \
                 patch.object(w, "previous_calendar_week", return_value=(start,end)), \
                 patch.object(w, "run_pipeline", return_value=(start,end,[],[],[make_offer()],[],state)), \
                 patch.object(w, "write_audit"), \
                 patch.object(w, "strict_coverage_failures", return_value=[]), \
                 patch.object(w, "update_state_after_publish", return_value=state), \
                 patch.object(w, "save_state"), \
                 patch.object(w, "_commit_progress") as commit, \
                 patch.object(w, "send_telegram") as send:
                w.main(publish=True)
                marker = json.loads(
                    (root / "markers" / "2026-11-09_2026-11-15.json").read_text()
                )
            send.assert_called_once()
            commit.assert_called_once()
            self.assertTrue(marker["complete"])
            self.assertEqual(["id-1"], marker["sent_ids"])


if __name__ == "__main__":
    unittest.main()
