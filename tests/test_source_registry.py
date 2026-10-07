import unittest

from sources import (
    BANKS,
    BANK_SOURCES,
    SOURCE_REGISTRY,
    official_link_priority,
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
