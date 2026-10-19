import unittest
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from collector import RawItem
from evaluator import Evaluation
from quality import validate_card


def fixture(bank="ВТБ", text="Переведите пенсию на карту ВТБ и получите бонус 1000 рублей."):
    return RawItem(bank=bank, source_id="fixture", source_type="fixture",
                   published_at=datetime.fromisoformat("2026-10-12T12:00:00+03:00"),
                   text=text, url="https://example.org/terms", external_links=[])


def card(**changes):
    data = dict(included=True, reason="included", title="Бонус за перевод пенсии на карту ВТБ",
                reward="Бонус 1000 рублей", conditions="Переведите пенсию на карту ВТБ.",
                mechanic="бонусы", goal="привлечение клиентов",
                promo_start=date(2026, 9, 7), promo_end=date(2027, 4, 30),
                evidence_url="https://example.org/terms")
    data.update(changes)
    return Evaluation(**data)


class QualityGateTest(unittest.TestCase):
    def test_valid_structured_card(self):
        self.assertIsNone(validate_card(fixture(), card()))

    def test_mixed_ozon_offer_blocked(self):
        item = fixture("Ozon Банк", "Скидки по зелёным ценам на Ozon и оплата после получения")
        result = card(title="Скидки до 30% на Ozon", reward="Скидка до 30%",
                      conditions="Если вы потратили деньги с карты, банк выставляет долг.",
                      mechanic="кешбэк", promo_start=date(2026, 10, 12),
                      promo_end=date(2026, 10, 12))
        self.assertIsNotNone(validate_card(item, result))

    def test_social_post_title_blocked(self):
        self.assertEqual(validate_card(fixture(), card(title="Этот пост можно обсудить с родителями Если начнёте получать пенсию на карту ВТБ")), "quality_irrelevant_text")

    def test_mechanic_mismatch_blocked(self):
        self.assertEqual(validate_card(fixture(), card(mechanic="кешбэк")), "quality_mechanic_mismatch")

    def test_one_day_requires_review(self):
        d = date(2026, 10, 12)
        self.assertEqual(validate_card(fixture(), card(promo_start=d, promo_end=d)), "quality_single_day_requires_review")

    def test_preview_never_sends_or_saves(self):
        # Preview mode must return before Telegram publication and state mutation.
        from pathlib import Path
        import preview
        item = fixture()
        result = card()
        state = {"sent_promos": {}}
        start = datetime(2026, 10, 12)
        end = datetime(2026, 10, 18)
        with patch.dict("os.environ", {"PUBLISH_TO_TELEGRAM": "0", "FORCE_RUN": "1", "STRICT_SOURCES": "0"}), \
             patch.object(preview, "run_pipeline", return_value=(start, end, [(item, result)], [], [(item, result, "pid", False)], [], state)), \
             patch.object(preview, "write_audit"), \
             patch.object(preview, "send_telegram") as send, \
             patch.object(preview, "save_state") as save, \
             patch.object(preview, "BANKS", ["ВТБ"]), \
             patch.object(preview, "bank_fully_checked", return_value=True):
            preview.main()
            send.assert_not_called()
            save.assert_not_called()
        self.assertTrue(Path("artifacts/preview_2026-10-12_2026-10-18.html").exists())


if __name__ == "__main__":
    unittest.main()
