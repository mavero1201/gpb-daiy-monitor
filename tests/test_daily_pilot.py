"""Regression tests for the bounded twice-daily read-only pilot."""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import daily_pilot

MOSCOW = ZoneInfo("Europe/Moscow")


class DailyPilotTests(unittest.TestCase):
    def test_reporting_window_is_current_moscow_calendar_day(self):
        start, end = daily_pilot.reporting_window(datetime(2026, 11, 3, 16, 10, tzinfo=MOSCOW))
        self.assertEqual(date(2026, 11, 3), start.date())
        self.assertEqual((0, 0), (start.hour, start.minute))
        self.assertEqual((16, 10), (end.hour, end.minute))
        self.assertEqual(14, (daily_pilot.PILOT_END - daily_pilot.PILOT_START).days + 1)

    def test_mixed_vtb_post_yields_one_dated_review_lead(self):
        text = (
            "В ноябре у нас кешбэк дня: 50% Чиббис, 45% Яндекс Лавка, "
            "10% Детский мир, 15% Отелло. Точные даты в приложении. "
            "А подписчики ВТБ Плюс уже 3 ноября смогут выбрать одну из "
            "категорий с 7% кешбэка на покупки 4 ноября: "
            "«Развлечения», «Театры и кино» или «Цветы»."
        )
        item = SimpleNamespace(
            bank="ВТБ", source_type="telegram", source_id="vtb_promos_tg",
            published_at=datetime(2026, 11, 3, 11, 0, tzinfo=MOSCOW),
            url="https://t.me/vtbvygoda/2229", text=text,
        )
        lead = daily_pilot.explicit_dated_vtb_plus_suboffer(item, date(2026, 11, 4))
        self.assertIsNotNone(lead)
        self.assertEqual("2026-11-04", lead["promo_start"])
        self.assertEqual("2026-11-04", lead["promo_end"])
        self.assertEqual("7% кешбэка", lead["reward"])
        self.assertEqual("mixed_post_explicit_dated_offer", lead["reason"])
        self.assertEqual(item.url, lead["source_url"])
        self.assertEqual("review", lead["status"])
        self.assertIsNone(
            daily_pilot.explicit_dated_vtb_plus_suboffer(item, date(2026, 11, 3))
        )
        item.bank = "Альфа-Банк"
        self.assertIsNone(
            daily_pilot.explicit_dated_vtb_plus_suboffer(item, date(2026, 11, 4))
        )

    def test_no_invented_start_from_bank_promo_announcement(self):
        item = SimpleNamespace(
            bank="ВТБ", source_type="telegram", source_id="vtb_promos_tg",
            published_at=datetime(2026, 11, 3, 11, 0, tzinfo=MOSCOW),
            url="https://t.me/vtbvygoda/9999",
            text="ВТБ Плюс: 50% Чиббис и 45% Яндекс Лавка. Сроки в приложении.",
        )
        self.assertIsNone(
            daily_pilot.explicit_dated_vtb_plus_suboffer(item, date(2026, 11, 4))
        )
        item.text = "ВТБ Плюс 7% кешбэка на покупки 4 ноября: категории есть."
        self.assertIsNone(
            daily_pilot.explicit_dated_vtb_plus_suboffer(item, date(2026, 11, 4))
        )

    def test_no_network_outside_approved_pilot_dates(self):
        start = datetime(2026, 11, 17, 0, 0, tzinfo=MOSCOW)
        end = datetime(2026, 11, 17, 17, 0, tzinfo=MOSCOW)
        with patch.object(daily_pilot, "reporting_window", return_value=(start, end)), \
             patch.object(daily_pilot, "collect_period") as collect:
            daily_pilot.main()
        collect.assert_not_called()

    def test_daily_audit_does_not_send_and_excludes_older_start(self):
        start = datetime(2026, 11, 3, 0, 0, tzinfo=MOSCOW)
        end = datetime(2026, 11, 3, 17, 5, tzinfo=MOSCOW)
        items = [
            SimpleNamespace(bank="ВТБ", source_id="vtb_tg", source_type="telegram",
                            published_at=end, url="https://t.me/BankVTB/100",
                            text="Акция на этой неделе", external_links=[]),
            SimpleNamespace(bank="ВТБ", source_id="vtb_tg", source_type="telegram",
                            published_at=end, url="https://t.me/BankVTB/101",
                            text="Новая акция", external_links=[]),
        ]

        def result(day):
            return SimpleNamespace(
                included=True, reason="included", title="Кешбэк", reward="10% кешбэк",
                conditions="Оплатить картой", mechanic="кешбэк", goal="активность",
                promo_start=day, promo_end=date(2026, 11, 9),
                evidence_url="https://www.vtb.ru/promo", date_status="", date_evidence="",
            )

        with tempfile.TemporaryDirectory() as folder, \
             patch.object(daily_pilot, "reporting_window", return_value=(start, end)), \
             patch.object(daily_pilot, "collect_period", return_value=(start, end, items, [])) as collect, \
             patch.object(daily_pilot, "evaluate", side_effect=[result(date(2026, 11, 1)), result(date(2026, 11, 3))]), \
             patch.object(daily_pilot, "validate_card", return_value=None), \
             patch.object(daily_pilot, "_mark_duplicates"), \
             patch.object(daily_pilot, "write_audit") as audit, \
             patch.object(daily_pilot, "ARTIFACT_DIR", Path(folder)):
            daily_pilot.main()
            manifest = json.loads(next(Path(folder).glob("daily_pilot_*.json")).read_text(encoding="utf-8"))
        self.assertEqual(21, collect.call_args.kwargs["recovery_days"])
        self.assertEqual(1, manifest["algorithm_candidates"])
        self.assertFalse(manifest["published_to_telegram"])
        audit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
