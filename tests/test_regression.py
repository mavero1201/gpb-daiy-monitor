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
        ]

        for case in cases:
            with self.subTest(case=case[0]):
                self.check_case(*case)


if __name__ == "__main__":
    unittest.main()
