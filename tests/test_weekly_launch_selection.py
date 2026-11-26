"""Regression tests for the agreed weekly launch selection rule."""
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pipeline


class LaunchWeekSelectionTests(unittest.TestCase):
    def test_launch_dates_not_post_dates(self):
        start = datetime(2026, 10, 19, tzinfo=timezone.utc)
        end = datetime(2026, 10, 25, tzinfo=timezone.utc)

        def case(name, published, promo_start, promo_end):
            item = SimpleNamespace(
                bank="Альфа-Банк", source_id="test", source_type="telegram",
                published_at=datetime.fromisoformat(published),
                text="Тестовое предложение", url="https://t.me/alfabank/1",
            )
            result = SimpleNamespace(
                included=True, reason="included",
                title=name, reward="10% кешбэк", mechanic="кешбэк",
                promo_start=date.fromisoformat(promo_start),
                promo_end=date.fromisoformat(promo_end),
                evidence_url="https://alfabank.ru/actions/rules/",
            )
            return item, result

        cases = [
            case("Old started promo but newly posted", "2026-10-22T12:00:00+00:00", "2026-10-01", "2026-10-31"),
            case("Newly launched earlier announcement", "2026-10-18T12:00:00+00:00", "2026-10-21", "2026-10-31"),
            case("One-day valid launch", "2026-10-23T12:00:00+00:00", "2026-10-23", "2026-10-23"),
            case("Next week's promo announced now", "2026-10-22T12:00:00+00:00", "2026-10-26", "2026-11-05"),
        ]

        with patch.object(pipeline, "collect_previous_week", return_value=(start, end, [i for i, _ in cases], [])), \
             patch.object(pipeline, "evaluate", side_effect=[r for _, r in cases]), \
             patch.object(pipeline, "validate_card", return_value=None), \
             patch.object(pipeline, "load_state", return_value={"sent_promos": {}, "last_successful_period_start": None}):
            _, _, evaluated, _, publish, recovered, _ = pipeline.run_pipeline()
        self.assertEqual(
            ["Newly launched earlier announcement", "One-day valid launch"],
            [result.title for _, result, _, _ in publish],
        )
        self.assertEqual([], recovered)
        self.assertEqual(
            ["outside_launch_week", "outside_launch_week"],
            [result.reason for _, result in [evaluated[0], evaluated[3]]],
        )


if __name__ == "__main__":
    unittest.main()
