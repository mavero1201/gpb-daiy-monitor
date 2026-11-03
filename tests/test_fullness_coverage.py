"""Regression checks for launch-week recall and conservative Telegram coverage."""
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch
from types import SimpleNamespace

import collector
from evaluator import extract_period
from sources import BANK_SOURCES


class FullnessCoverageTests(unittest.TestCase):
    def test_earlier_announcements_are_included_in_scan_window(self):
        week_start = datetime(2026, 10, 26, tzinfo=timezone.utc)
        week_end = datetime(2026, 11, 1, tzinfo=timezone.utc)
        observed = []

        def fetch(bank, src, start, end):
            observed.append((start, end))
            return [], collector.SourceCheck(
                bank=bank, source_id=src["id"], source_type="telegram",
                source_value=src["value"], status="ok", item_count=0,
            )

        with patch.object(collector, "previous_calendar_week", return_value=(week_start, week_end)), \
             patch.object(collector, "BANK_SOURCES", [{"bank": "ВТБ", "sources": [{"id": "vtb_tg", "type": "telegram", "value": "BankVTB"}]}]), \
             patch.object(collector, "fetch_telegram_source", side_effect=fetch):
            collector.collect_previous_week()

        self.assertEqual(21, (week_start - observed[0][0]).days)
        self.assertEqual(week_end, observed[0][1])

    def test_consecutive_cross_month_weekend_is_two_days(self):
        period = extract_period(
            "На 31 октября и 1 ноября — три категории повышенного кешбэка по карте ВТБ.",
            date(2026, 10, 30),
        )
        self.assertEqual((date(2026, 10, 31), date(2026, 11, 1)), period)

    def test_nonconsecutive_dates_are_not_assumed_to_be_one_promo(self):
        period = extract_period(
            "На 25 октября и 1 ноября — отдельные предложения.",
            date(2026, 10, 30),
        )
        self.assertIsNone(period)

    def test_official_halva_promo_telegram_is_monitored(self):
        sovcom = next(b for b in BANK_SOURCES if b["bank"] == "Совкомбанк")
        channels = [s for s in sovcom["sources"] if s["type"] == "telegram" and s.get("automatic")]
        self.assertIn("halvacard_official", [x["value"] for x in channels])

    def test_repeated_telegram_page_is_reported_incomplete(self):
        html = """
        <div class="tgme_widget_message_wrap">
          <div class="tgme_widget_message" data-post="example_bank/123">
            <div class="tgme_widget_message_text">Кешбэк 10% по карте с 26.10.2026 по 01.11.2026.</div>
            <time datetime="2026-10-30T12:00:00+00:00"></time>
            <a class="tgme_widget_message_date" href="https://t.me/example_bank/123">message</a>
          </div>
        </div>
        """
        response = SimpleNamespace(text=html, raise_for_status=lambda: None)
        with patch("collector.requests.get", return_value=response):
            items, coverage = collector.fetch_telegram_source(
                "Тестовый банк",
                {"id": "test_tg", "value": "example_bank", "required": True},
                datetime(2026, 10, 15, tzinfo=timezone.utc),
                datetime(2026, 11, 1, tzinfo=timezone.utc),
            )
        self.assertEqual(1, len(items))
        self.assertEqual("limited", coverage.status)
        self.assertTrue(coverage.error)


if __name__ == "__main__":
    unittest.main()
