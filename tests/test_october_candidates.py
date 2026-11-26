"""Regression excerpts from the 2026-10-19..25 archived Telegram review queue.

These are source excerpts, not reconstructed offers or verified campaign terms.
All external rule fetching is disabled to make the test deterministic.
"""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from collector import RawItem
from evaluator import evaluate
from quality import validate_card


CASES = [
    (
        "vtb_wb",
        "ВТБ",
        "Получайте скидку до 6% на WB с картой ВТБ Мы с Wildberries всё чаще радуем вас вместе. При оформлении заказа выбирайте оплату картой ВТБ — получайте 3% скидки. Участникам программы «WB Клуб» добавляем ещё 3%. Максимальная сумма скидки — 3 000 ₽ в месяц.",
        "no_exact_period_after_recheck",
    ),
    (
        "alfa_baths",
        "Альфа-Банк",
        "Поддадим ЖАРУ в Альфа-Пятницу. С КЭШБЭКОМ ДО 50% в банях. 23 октября устраиваем первую Альфа-Пятницу в банях — и возвращаем кэшбэк до 50%. Вам же осталось только оплатить чек в бане Альфа-Картой и забрать выгоду до 25 000 рублей.",
        "quality_single_day_requires_review",
    ),
    (
        "sber_deposit",
        "Сбер",
        "ОТКРЫЛИ ВКЛАД — ПОЛУЧИЛИ ШАНС ВЫИГРАТЬ 18,5 МЛН БОНУСОВ СПАСИБО. Открывайте любой вклад до 31 октября и участвуйте в розыгрыше 18,5 МЛН бонусов Спасибо. Откройте вклад в СберБанк Онлайн.",
        "deadline_only_needs_start",
    ),
    (
        "tbank_credit",
        "Т-Банк",
        "Тратите 10 000 ₽ — возвращаем 3 000 ₽. До 22 ноября оформите кредитку с бесплатным годовым обслуживанием. Потратьте 10 000 ₽ в первый месяц после получения карты. Мы вернем 3 000 ₽.",
        "deadline_only_needs_start",
    ),
    (
        "psb_prizes",
        "ПСБ",
        "Марафон призов от ПСБ продолжается! Уже в ноябре мы разыграем: главный приз — 5 млн рублей. Для участия в розыгрыше нужно поддерживать среднемесячные остатки на счете и совершать покупки по карте. Акция продлится до 31 октября 2026 года.",
        "deadline_only_needs_start",
    ),
    (
        "psb_cashback",
        "ПСБ",
        "На случай сезонных трат — суперкешбэк по карте ПСБ. Вот сколько возвращаем за покупки в октябре: 10% — за поездки на такси; 5% — на одежду и обувь. Чтобы активировать суперкешбэк: Оформите кредитную карту «180 дней без %». Оплачивайте покупки картой.",
        "activity_month_only_needs_terms",
    ),
    (
        "vtb_two_offers",
        "ВТБ",
        "Теперь можно рекомендовать до 10 продуктов ВТБ. Если карты нет — оформите, делитесь с друзьями и забирайте бонус. Скидка 6% на WB при оплате нашей картой — прилагается!",
        "multiple_offers_require_split",
    ),
    (
        "sber_two_offers",
        "Сбер",
        "Получайте кешбэк 18,5% бонусами Спасибо у партнёров экосистемы, а со СберПрайм — целых 37%. Если Прайма ещё нет, подключайтесь за 1 ₽ на 60 дней. Специальный курс будет действовать с 12 по 15 ноября. 1 бонус Спасибо = 1,85 ₽.",
        "multiple_offers_require_split",
    ),
]


class OctoberCandidateTests(unittest.TestCase):
    def test_archived_candidates_remain_structured_and_unpublished(self):
        for case_id, bank, post, expected in CASES:
            with self.subTest(case=case_id):
                item = RawItem(
                    bank=bank, source_id="archived_tg", source_type="telegram",
                    published_at=datetime(2026, 10, 22, tzinfo=timezone.utc),
                    text=post, url=f"https://t.me/archive/{case_id}",
                    external_links=[],
                )
                with patch("evaluator.build_evidence", return_value=(post, item.url)), \
                     patch("evaluator.recheck_exact_period", return_value=(None, post, item.url)):
                    result = evaluate(item)
                gate_reason = validate_card(item, result)
                actual = gate_reason or result.reason
                self.assertEqual(actual, expected)
                self.assertFalse(result.included and gate_reason is None)


if __name__ == "__main__":
    unittest.main()
