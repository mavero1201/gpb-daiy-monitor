import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from collector import RawItem
from official_rules_search import (
    discover_official_rule_urls, is_official_document_url,
)
from evaluator import recheck_exact_period


class OfficialRulesSearchTests(unittest.TestCase):
    def test_only_official_https_urls(self):
        self.assertTrue(is_official_document_url("Сбер", "https://www.sberbank.ru/ru/promo/rules.pdf"))
        self.assertFalse(is_official_document_url("Сбер", "https://sberbank.ru.evil.com/rules.pdf"))
        self.assertFalse(is_official_document_url("Сбер", "https://otherbank.ru/rules.pdf"))
        self.assertFalse(is_official_document_url("Сбер", "http://sberbank.ru/rules.pdf"))

    @patch("official_rules_search.requests.get")
    def test_search_returns_only_official_results(self, get):
        rss = b"""<rss><channel>
        <item><link>https://www.psbank.ru/personal/cards/rules/promo.pdf</link></item>
        <item><link>https://unrelated.example/promo.pdf</link></item>
        </channel></rss>"""
        get.return_value = SimpleNamespace(content=rss, raise_for_status=lambda: None)
        urls = discover_official_rule_urls("ПСБ", "Марафон призов 5 млн рублей", limit=4)
        self.assertEqual(urls, ["https://www.psbank.ru/personal/cards/rules/promo.pdf"])
        self.assertLessEqual(get.call_count, 2)

    @patch("evaluator._fetch_document")
    @patch("evaluator.discover_official_rule_urls")
    def test_rule_dates_are_fetched_not_inferred_from_search(self, search, fetch):
        search.return_value = ["https://www.psbank.ru/promo/rules.pdf"]
        fetch.return_value = (
            "Правила акции: приз 5 млн рублей. Период участия с 01.08.2026 по 31.10.2026.",
            None,
            "https://www.psbank.ru/promo/rules.pdf",
        )
        item = RawItem(
            bank="ПСБ", source_id="psb_tg", source_type="telegram",
            published_at=datetime(2026, 10, 19, tzinfo=ZoneInfo("Europe/Moscow")),
            text="Участвуйте в Марафоне призов. Приз 5 млн рублей. Оформите карту.",
            url="https://t.me/psbbank/3740", external_links=[],
        )
        period, evidence, source = recheck_exact_period(item, item.text, item.url)
        self.assertEqual(tuple(map(str, period)), ("2026-08-01", "2026-10-31"))
        self.assertEqual(source, "https://www.psbank.ru/promo/rules.pdf")


if __name__ == "__main__":
    unittest.main()
