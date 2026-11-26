import unittest
from publish_approved import validate_preview, message_parts


class PublishApprovedTests(unittest.TestCase):
    def test_reject_empty_preview(self):
        with self.assertRaises(ValueError):
            validate_preview(
                "<b>Мониторинг акций Daily Banking</b>\n"
                "Нет предложений, прошедших проверку для публикации."
            )

    def test_accept_complete_card(self):
        preview = (
            "<b>Мониторинг акций Daily Banking</b>\n"
            "<b>Банк</b>\n<b>Акция</b>\n"
            "<b>Вознаграждение</b> - 3000 ₽\n"
            "<b>Условия</b> - Оплатить покупки\n"
            "<b>Механика</b> - денежный возврат\n"
            "<b>Срок акции</b> - 01.10.2026 - 31.10.2026\n"
            '<a href="https://bank.example/rules">Источник</a>'
        )
        validate_preview(preview)
        self.assertEqual(message_parts(preview), [preview])

    def test_reject_oversize_indivisible_block(self):
        with self.assertRaises(ValueError):
            message_parts("A" * 4000)


if __name__ == "__main__":
    unittest.main()
