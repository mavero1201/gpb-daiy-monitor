import unittest
from types import SimpleNamespace

from sources import (
    BANKS,
    BANK_SOURCES,
    SOURCE_REGISTRY,
    bank_fully_checked,
    official_link_priority,
    required_any_groups,
    strict_coverage_failures,
)


class SourceRegistryTest(unittest.TestCase):
    def test_has_twelve_banks(self):
        self.assertEqual(12, len(BANKS))
        self.assertEqual(12, len(SOURCE_REGISTRY))

    def test_automatic_sources_are_supported(self):
        for entry in BANK_SOURCES:
            for source in entry["sources"]:
                self.assertIn(source["type"], {"telegram", "web"})

    def test_max_is_reference_not_strict_collector(self):
        for entry in SOURCE_REGISTRY:
            for source in entry["sources"]:
                if source["type"] in {"max", "max_bot"}:
                    self.assertFalse(source["automatic"])
                    self.assertFalse(source["required"])

    def test_alfa_web_outage_is_degraded_not_blocking(self):
        groups = required_any_groups()
        alfa = [
            group for group in groups
            if group["bank"] == "Альфа-Банк"
            and group["group"] == "alfa_official_web"
        ]
        self.assertEqual(1, len(alfa))
        self.assertFalse(alfa[0]["blocking"])

        checks = [
            SimpleNamespace(bank="Альфа-Банк", source_id="alfa_tg", required=True, status="ok"),
            SimpleNamespace(bank="Альфа-Банк", source_id="alfa_web_actions", required=False, status="error"),
            SimpleNamespace(bank="Альфа-Банк", source_id="alfa_web_debit", required=False, status="error"),
        ]
        self.assertEqual([], strict_coverage_failures(checks))
        self.assertFalse(bank_fully_checked("Альфа-Банк", checks))

    def test_yandex_web_sources_form_one_required_fallback_group(self):
        groups = required_any_groups()
        yandex = [
            group for group in groups
            if group["bank"] == "Яндекс Банк"
            and group["group"] == "yandex_official_web"
        ]
        self.assertEqual(1, len(yandex))
        self.assertEqual(
            {"yandex_web_account", "yandex_web_pay", "yandex_web_cashback"},
            set(yandex[0]["source_ids"]),
        )

    def test_yandex_outage_does_not_block_when_alternate_official_web_is_ok(self):
        checks = [
            SimpleNamespace(bank="Яндекс Банк", source_id="yandex_tg", required=True, status="ok"),
            SimpleNamespace(bank="Яндекс Банк", source_id="yandex_web_account", required=False, status="error"),
            SimpleNamespace(bank="Яндекс Банк", source_id="yandex_web_pay", required=False, status="ok"),
            SimpleNamespace(bank="Яндекс Банк", source_id="yandex_web_cashback", required=False, status="ok"),
        ]
        self.assertEqual([], strict_coverage_failures(checks))
        self.assertTrue(bank_fully_checked("Яндекс Банк", checks))

    def test_yandex_blocks_only_if_all_official_web_fallbacks_fail(self):
        checks = [
            SimpleNamespace(bank="Яндекс Банк", source_id="yandex_tg", required=True, status="ok"),
            SimpleNamespace(bank="Яндекс Банк", source_id="yandex_web_account", required=False, status="error"),
            SimpleNamespace(bank="Яндекс Банк", source_id="yandex_web_pay", required=False, status="error"),
            SimpleNamespace(bank="Яндекс Банк", source_id="yandex_web_cashback", required=False, status="error"),
        ]
        failures = strict_coverage_failures(checks)
        self.assertIn("Яндекс Банк:yandex_official_web:all_unavailable", failures)
        self.assertFalse(bank_fully_checked("Яндекс Банк", checks))

    def test_registered_official_link_has_priority(self):
        self.assertEqual(
            0,
            official_link_priority(
                "Т-Банк",
                "https://max.ru/tbank/example-post",
            ),
        )
        self.assertEqual(
            0,
            official_link_priority(
                "Газпромбанк",
                "https://www.gazprombank.ru/personal/page/special-offers/example",
            ),
        )


if __name__ == "__main__":
    unittest.main()
