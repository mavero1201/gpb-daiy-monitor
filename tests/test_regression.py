import unittest
from datetime import datetime

from collector import RawItem
from evaluator import evaluate


class RegressionWeekTest(unittest.TestCase):
    def check_case(self, case_id, bank, published_at, text, expected):
        item = RawItem(
            bank=bank,
            source_id="regression_fixture",
            source_type="fixture",
            published_at=datetime.fromisoformat(published_at),
            text=text,
            url="https://example.test/" + case_id,
            external_links=[],
        )
        result = evaluate(item)
        self.assertEqual(expected, result.included, msg=f"{case_id}: {result.reason}")

    def test_reference_week(self):
        cases = [
            (
                "include_gpb",
                "Газпромбанк",
                "2026-10-02T12:00:00+03:00",
                "Акция: 50% кешбэка. Совершите покупку картой. Акция действует с 01.10.2026 по 31.10.2026.",
                True,
            ),
            (
                "include_tbank",
                "Т-Банк",
                "2026-10-01T20:03:00+03:00",
                "Розыгрыш 1 000 000 рублей. Чтобы участвовать, пополните сервис. Акция действует с 1 по 8 октября 2026.",
                True,
            ),
            (
                "exclude_kids",
                "Альфа-Банк",
                "2026-09-30T20:01:00+03:00",
                "Бонусы и подарки владельцам детской карты.",
                False,
            ),
            (
                "exclude_no_end_date",
                "ПСБ",
                "2026-10-01T10:00:00+03:00",
                "Кешбэк 100% за снятие наличных. Снимайте наличные картой. Акция стартует с 01.10.2026.",
                False,
            ),
            (
                "exclude_ozon_blogger",
                "Ozon Банк",
                "2026-10-01T12:55:00+03:00",
                "Запустили акцию для блогеров. До 15 октября опубликуйте первый пост в Ozon Blogger и получите 2000 баллов на покупки. Акция действует с 15.09.2026 по 15.10.2026.",
                False,
            ),
            (
                "exclude_vtb_social_giveaway",
                "ВТБ",
                "2026-10-09T16:34:00+03:00",
                "Модные авоськи с повышенным кешбэком к выгулу готовы! Покупать по карте Магнит Пэй ВТБ до 20% выгоднее. Разыгрываем авоськи с 09.10.2026 по 31.10.2026. Чтобы участвовать, подпишитесь на канал и нажмите кнопку.",
                False,
            ),
            (
                "exclude_military_pension",
                "ПСБ",
                "2026-10-08T10:00:00+03:00",
                "Переведите военную пенсию в ПСБ и получите кешбэк 25% за покупки в супермаркетах. Закажите дебетовую карту. Акция действует с 24.08.2026 по 28.02.2027.",
                False,
            ),
            (
                "exclude_mts_barabania",
                "МТС Банк",
                "2026-10-08T11:30:00+03:00",
                "Акция только сегодня. Заходите в приложение или интернет-банк, откройте раздел Выгода и получите дополнительную попытку за 15 баллов кешбэка вместо 30. Акция доступна держателям карты МТС Деньги.",
                False,
            ),
            (
                "exclude_mts_payment_any_bank",
                "МТС Банк",
                "2026-09-29T16:05:42+03:00",
                "С 29 сентября по 8 октября пополняйте Steam через МТС Оплату от 2 000 ₽ и участвуйте в розыгрыше призов на общую сумму 200 000 ₽. Оплата через СБП с карты любого банка или с лицевого счёта МТС.",
                False,
            ),
            (
                "include_mts_payment_if_mts_bank_card_required",
                "МТС Банк",
                "2026-09-29T16:05:42+03:00",
                "С 29 сентября по 8 октября пополняйте Steam через МТС Оплату от 2 000 ₽ картой МТС Банка и участвуйте в розыгрыше призов на общую сумму 200 000 ₽.",
                True,
            ),
            (
                "exclude_no_customer_action",
                "Сбер",
                "2026-10-08T12:00:00+03:00",
                "Акция с 05.10.2026 по 11.10.2026. Кешбэк 10% по карте Сбера.",
                False,
            ),
        ]

        for case in cases:
            with self.subTest(case=case[0]):
                self.check_case(*case)


if __name__ == "__main__":
    unittest.main()
