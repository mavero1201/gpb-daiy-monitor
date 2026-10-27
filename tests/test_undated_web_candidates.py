"""Collection of official bank offers without publication dates.
External requests are mocked; no Telegram publication.
"""
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from bs4 import BeautifulSoup

from collector import fetch_web_source
from evaluator import evaluate


ROOT = "https://www.vtb.ru/personal/karty/debetovye/"
CARD = "https://www.vtb.ru/promo/new-reward"


def source():
    return {"id": "vtb_web_debit", "value": ROOT, "required": True}


def html_document(value, url):
    soup = BeautifulSoup(value, "html.parser")
    return (soup.get_text(" ", strip=True), soup, url)


class WebCandidatePeriodTests(unittest.TestCase):
    def collect(self, card_text):
        root = html_document(
            '<html><body><p>' + ('Банковские предложения по картам. ' * 7) + '</p><a href="/promo/new-reward">Кешбэк за покупки картой</a></body></html>',
            ROOT,
        )
        card = html_document(f"<html><body><p>{card_text}</p></body></html>", CARD)

        def fetch(url):
            return root if url == ROOT else card if url == CARD else None

        with patch("collector._fetch_document", side_effect=fetch):
            return fetch_web_source(
                "ВТБ", source(),
                datetime(2026, 10, 19, tzinfo=timezone.utc),
                datetime(2026, 10, 25, tzinfo=timezone.utc),
            )

    def test_undated_page_is_collected_and_explicit_period_verified(self):
        items, check = self.collect(
            "Оплатите картой ВТБ покупку и получите 10% кешбэка. "
            "Акция действует с 19.10.2026 по 25.10.2026."
        )
        self.assertEqual("ok", check.status)
        self.assertEqual(1, len(items))
        self.assertIsNone(items[0].published_at)
        result = evaluate(items[0])
        self.assertTrue(result.included, result.reason)
        self.assertEqual(date(2026, 10, 19), result.promo_start)
        self.assertEqual(date(2026, 10, 25), result.promo_end)

    def test_dont_guess_year_on_undated_page(self):
        items, check = self.collect(
            "Оплатите картой ВТБ покупку и получите 10% кешбэка. "
            "Акция действует с 19 по 25 октября."
        )
        self.assertEqual(1, len(items))
        self.assertIsNone(items[0].published_at)
        with patch("evaluator.recheck_exact_period", return_value=(None, items[0].text, CARD)):
            result = evaluate(items[0])
        self.assertFalse(result.included)
        self.assertIsNone(result.promo_start)

    def test_incomplete_catalog_never_certified(self):
        links = "".join(
            f'<a href="/promo/offer{i}">Кешбэк за покупки картой №{i}</a>'
            for i in range(36)
        )
        root = html_document("<html><body>" + links + "</body></html>", ROOT)
        page = html_document(
            "<html><body><p>Оплатите картой ВТБ покупку и получите 10% кешбэка. "
            "Акция с 19.10.2026 по 25.10.2026.</p></body></html>", CARD
        )
        with patch("collector._fetch_document", side_effect=lambda url: root if url == ROOT else page):
            items, check = fetch_web_source(
                "ВТБ", source(),
                datetime(2026, 10, 19, tzinfo=timezone.utc),
                datetime(2026, 10, 25, tzinfo=timezone.utc),
            )
        self.assertEqual("limited", check.status)
        self.assertEqual(35, len(items))


if __name__ == "__main__":
    unittest.main()
