"""Regression tests for bank promotion index recall, without network requests."""
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from bs4 import BeautifulSoup

from collector import (
    _allowed_catalog_link,
    _catalog_launch_date_hint,
    _looks_like_candidate_link,
    fetch_web_source,
)


class OfficialCatalogRecallTests(unittest.TestCase):
    def test_only_bank_official_alfa_document_cdn_is_allowed(self):
        root = "https://alfabank.ru/actions/rules/"
        self.assertTrue(_allowed_catalog_link("https://alfabank.servicecdn.ru/doc/rules.pdf", root))
        self.assertTrue(_allowed_catalog_link("https://alfabank.ru/actions/rules/1.pdf", root))
        self.assertFalse(_allowed_catalog_link("https://untrusted-cdn.example/rules.pdf", root))
        self.assertFalse(_allowed_catalog_link("https://alfabank.servicecdn.ru/doc/rules.pdf", "https://vtb.ru/promo/"))

    def test_generic_tariffs_not_confused_with_offers(self):
        self.assertFalse(_looks_like_candidate_link("Тариф ЖКХ", "https://psbank.ru/tar_jkh.pdf"))
        self.assertFalse(_looks_like_candidate_link("Политика конфиденциальности", "https://bank.ru/actions/privacy.pdf"))
        self.assertTrue(_looks_like_candidate_link("Правила акции Кешбэк 10%", "https://alfabank.servicecdn.ru/docs/abc.pdf"))
        self.assertTrue(_looks_like_candidate_link("Акции по Халве 20% кешбэк", "https://sovcombank.ru/document/18990"))

    def test_explicit_catalog_start_date(self):
        self.assertEqual(date(2026, 10, 26), _catalog_launch_date_hint("Акция с 26.10.2026 по 09.11.2026"))
        self.assertEqual(date(2026, 11, 1), _catalog_launch_date_hint("За период проведения акции с «01» ноября 2026 г. по «30» ноября 2026"))
        self.assertIsNone(_catalog_launch_date_hint("Акция действует до 30 октября"))
        self.assertIsNone(_catalog_launch_date_hint("С 1 ноября (год не указан)"))

    def test_new_promos_are_prioritized_ahead_of_older_35_links(self):
        root_url = "https://alfabank.ru/actions/rules/"
        old = "".join(
            f'<li><a href="https://alfabank.servicecdn.ru/docs/old_{i}.pdf">Правила акции Кешбэк 10%</a> '
            'Акция с 01.10.2026 по 31.10.2026</li>'
            for i in range(36)
        )
        recent = "".join(
            f'<li><a href="https://alfabank.servicecdn.ru/docs/new_{i}.pdf">Правила акции Кешбэк до 20%</a> '
            f'Акция с {day:02d}.10.2026 по 09.11.2026</li>'
            for i, day in enumerate((26, 27, 28, 29), start=1)
        )
        html = "<html><body><h1>Официальные акции банка</h1>" + old + recent + "</body></html>"
        soup = BeautifulSoup(html, "html.parser")
        root = (soup.get_text(" ", strip=True), soup, root_url)
        rule_text = (
            "Правила акции: клиенты банка платят Альфа-Картой за покупки "
            "и получают кешбэк до 20%. Действует с 26.10.2026 по 09.11.2026. "
            "Покупка по карте обязательна для получения вознаграждения."
        )

        def fake_fetch(url):
            if url == root_url:
                return root
            return rule_text, None, url

        with patch("collector._fetch_document", side_effect=fake_fetch):
            items, check = fetch_web_source(
                "Альфа-Банк",
                {"id": "alfa_web_actions", "value": root_url, "required": False},
                datetime(2026, 10, 19, tzinfo=timezone.utc),
                datetime(2026, 11, 1, tzinfo=timezone.utc),
            )

        self.assertEqual("limited", check.status)  # Never certify truncated catalogue.
        self.assertEqual(35, len(items))
        chosen = {item.url for item in items}
        for i in range(1, 5):
            self.assertIn(f"https://alfabank.servicecdn.ru/docs/new_{i}.pdf", chosen)
        self.assertNotIn("https://alfabank.servicecdn.ru/docs/old_35.pdf", chosen)


if __name__ == "__main__":
    unittest.main()
