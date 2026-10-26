import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from evaluator import Evaluation, evaluate
from quality import validate_card


def item(text, links=()):
    return SimpleNamespace(
        bank="ВТБ", text=text, published_at=datetime(2026, 10, 22, tzinfo=timezone.utc),
        url="https://t.me/bankvtb/3883", external_links=list(links),
        source_type="telegram", source_id="vtb_tg",
    )


class SourceCoherenceTests(unittest.TestCase):
    def test_unrelated_page_period_does_not_create_card(self):
        post = "Оплатите картой ВТБ покупку и получите 6% кешбэка."
        other = "Другая акция действует с 01.10.2026 по 31.10.2026."
        with patch("evaluator.build_evidence", return_value=(post + " " + other, "https://vtb.ru/other")), \
             patch("evaluator.recheck_exact_period", return_value=(None, post + " " + other, "https://vtb.ru/other")):
            result = evaluate(item(post))
        self.assertEqual(result.reason, "no_exact_period_after_recheck")

    def test_other_page_cannot_supply_reward_or_conditions(self):
        post = "Оплатите картой ВТБ и получите подарок. С 19.10.2026 по 25.10.2026."
        other = "Оплатите подписку и получите 15% кешбэка."
        with patch("evaluator.build_evidence", return_value=(post + " " + other, "https://vtb.ru/other")):
            result = evaluate(item(post))
        self.assertFalse(result.included)
        self.assertEqual(result.reason, "no_reward")

    def test_dates_are_not_mistaken_for_reward(self):
        from evaluator import extract_reward
        post = "Подарок за оплату картой ВТБ. С 19.10.2026 по 25.10.2026."
        self.assertEqual(extract_reward(post, post, "ВТБ"), "")

    def test_numeric_cashback_is_reward(self):
        from evaluator import extract_reward
        post = "Оплатите картой ВТБ и получите кешбэк 6%."
        self.assertIn("6%", extract_reward(post, post, "ВТБ"))

    def test_large_bonus_prize_is_recognized(self):
        from evaluator import extract_reward
        post = "Разыгрываем 18,5 МЛН бонусов Спасибо. Откройте вклад до 31 октября."
        self.assertIn("18,5 МЛН бонусов", extract_reward(post, post, "Сбер"))

    def test_explicit_ruble_return_is_not_confused_with_spending(self):
        from evaluator import extract_reward, classify_mechanic, classify_goal
        post = (
            "До 22 ноября оформите кредитную карту. "
            "Потратьте 10 000 ₽ в первый месяц. Мы вернем 3 000 ₽."
        )
        self.assertEqual(extract_reward(post, post, "Т-Банк"), "Возврат 3 000 ₽")
        self.assertEqual(classify_mechanic(post), "денежный возврат")
        self.assertEqual(classify_goal(post), "оформление банковского продукта")

    def test_million_ruble_prize_is_recognized(self):
        from evaluator import extract_reward
        post = "Марафон призов: уже в ноябре разыграем главный приз — 5 млн рублей."
        self.assertIn("5 млн рублей", extract_reward(post, post, "ПСБ"))

    def test_deadline_is_not_invented_as_full_period(self):
        from evaluator import extract_date_hint
        post = "До 22 ноября оформите кредитную карту. Потратьте 10 000 ₽ и вернем 3 000 ₽."
        self.assertEqual(extract_date_hint(post), ("deadline_only", "До 22 ноября"))
        with patch("evaluator.build_evidence", return_value=(post, "https://t.me/tbank/11222")), \
             patch("evaluator.recheck_exact_period", return_value=(None, post, "https://t.me/tbank/11222")):
            result = evaluate(item(post))
        self.assertFalse(result.included)
        self.assertEqual(result.reason, "deadline_only_needs_start")
        self.assertEqual(result.date_evidence, "До 22 ноября")
        self.assertFalse(result.promo_start)

    def test_activity_month_is_not_invented_as_campaign_period(self):
        from evaluator import extract_date_hint
        post = "Суперкешбэк по карте ПСБ за покупки в октябре: 10% на такси. Оплачивайте покупки картой."
        self.assertEqual(extract_date_hint(post), ("activity_month_only", "за покупки в октябре"))
        with patch("evaluator.build_evidence", return_value=(post, "https://t.me/psbbank/3741")), \
             patch("evaluator.recheck_exact_period", return_value=(None, post, "https://t.me/psbbank/3741")):
            result = evaluate(item(post))
        self.assertEqual(result.reason, "activity_month_only_needs_terms")
        self.assertIsNone(result.promo_start)

    def test_one_day_promo_stays_in_review(self):
        from evaluator import extract_single_day_event
        from datetime import date
        post = "23 октября устраиваем Альфа-Пятницу в банях и возвращаем кешбэк до 50%. Оплатите Альфа-Картой."
        self.assertEqual(
            extract_single_day_event(post, date(2026, 10, 22)),
            (date(2026, 10, 23), date(2026, 10, 23)),
        )
        with patch("evaluator.build_evidence", return_value=(post, "https://t.me/AlfaBank/4874")):
            result = evaluate(item(post))
        self.assertTrue(result.included)
        self.assertEqual(validate_card(item(post), result), "quality_single_day_requires_review")

    def test_mixed_post_does_not_combine_two_offers(self):
        from evaluator import has_multiple_offers
        post = "Рекомендуйте карту другу и забирайте бонус. Скидка 6% на WB при оплате картой ВТБ."
        self.assertTrue(has_multiple_offers(post))
        with patch("evaluator.build_evidence", return_value=(post, "https://t.me/bankvtb/3883")):
            result = evaluate(item(post))
        self.assertEqual(result.reason, "multiple_offers_require_split")
        self.assertFalse(result.included)

    def test_unrelated_rule_page_cannot_supply_dates(self):
        from evaluator import period_from_matching_rules
        post = "Оплатите картой ВТБ и получите кешбэк 6%."
        other = "Другая акция с 01.10.2026 по 31.10.2026 дает кешбэк 20%."
        self.assertIsNone(period_from_matching_rules(item(post), other))

    def test_matching_rule_page_can_supply_dates(self):
        from evaluator import period_from_matching_rules
        from datetime import date
        post = "Оплатите картой ВТБ и получите кешбэк 6%."
        rules = "Кешбэк 6% за оплату картой ВТБ. Акция действует с 01.10.2026 по 31.10.2026."
        self.assertEqual(
            period_from_matching_rules(item(post), rules),
            (date(2026, 10, 1), date(2026, 10, 31)),
        )

    def test_review_queue_keeps_rejected_candidate(self):
        from pipeline import write_audit
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import pipeline
        candidate = Evaluation(False, "no_exact_period_after_recheck")
        with TemporaryDirectory() as tmp:
            with patch.object(pipeline, "ARTIFACT_DIR", Path(tmp)), \
                 patch.object(pipeline, "BANKS", ["ВТБ"]):
                paths = write_audit(
                    datetime(2026, 10, 19, tzinfo=timezone.utc),
                    datetime(2026, 10, 25, tzinfo=timezone.utc),
                    [(item("Текст исходной акции"), candidate)], [],
                )
                queue = next(p for p in paths if "review_queue" in str(p))
                self.assertIn("Текст исходной акции", queue.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
