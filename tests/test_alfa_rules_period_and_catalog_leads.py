"""Regressions from the actual 03-04 Nov Daily Banking audit (not synthetic claims)."""
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from bs4 import BeautifulSoup

from collector import fetch_web_source, _catalog_launch_date_hint
from evaluator import official_alfa_rule_campaign_period


class OfficialAlfaRulesPeriodTests(unittest.TestCase):
    def test_campaign_period_not_first_monthly_reporting_period(self):
        rule = (
            "Правила проведения Акции «Награды за задания». "
            "Первым Отчетным периодом является период с 01.11.2026 по 30.11.2026. "
            "Период проведения Акции – с 01.10.2026 по 31.12.2026 (включительно). "
            "Период участия в Акции – с 01.10.2026 по 30.11.2026."
        )
        self.assertEqual(
            (date(2026, 10, 1), date(2026, 12, 31)),
            official_alfa_rule_campaign_period(rule),
        )

    def test_new_november_campaign_period_is_preserved(self):
        rule = (
            "Правила проведения Акции «Повышенный кэшбэк 15% в Альфа-Афише». "
            "В отчетном периоде с 01.10.2026 по 31.10.2026. "
            "Период проведения Акции – с 01.11.2026 по 30.11.2026 (включительно). "
            "Клиенты совершают покупку картой в сервисе Афиша."
        )
        self.assertEqual(
            (date(2026, 11, 1), date(2026, 11, 30)),
            official_alfa_rule_campaign_period(rule),
        )

    def test_no_explicit_campaign_period_is_not_invented(self):
        rule = "Правила проведения Акции «Награды». Отчётный период с 01.11.2026 по 30.11.2026."
        self.assertIsNone(official_alfa_rule_campaign_period(rule))

    def test_official_index_quoted_november_date(self):
        self.assertEqual(
            date(2026, 11, 1),
            _catalog_launch_date_hint(
                "Правила проведения акции «Кэшбэк до 10% на покупки в Горбилет». "
                "За период проведения акции с «01» ноября 2026 г. по «30» ноября 2026 г."
            ),
        )

    def test_all_relevant_catalog_links_recorded_even_when_not_downloaded(self):
        root_url = "https://alfabank.ru/actions/rules/"
        offers = "".join(
            f'<li><a href="https://alfabank.servicecdn.ru/rules/nov_{i}.pdf">'
            'Правила акции «Кэшбэк 10% по Альфа-Карте». '
            'За период проведения акции с «01» ноября 2026 г. по «30» ноября 2026 г.'
            '</a></li>'
            for i in range(40)
        )
        root_html = "<html><body>" + offers + "</body></html>"
        root_soup = BeautifulSoup(root_html, "html.parser")
        root = (root_soup.get_text(" ", strip=True), root_soup, root_url)
        doc = (
            "Правила проведения Акции «Кешбэк 10%»."
            " Совершите оплату по дебетовой карте Альфа-Банка и получите 10% кешбэка. "
            " Период проведения Акции – с 01.11.2026 по 30.11.2026."
        )
        with patch(
            "collector._fetch_document",
            side_effect=lambda url: root if url == root_url else (doc, None, url),
        ):
            items, coverage = fetch_web_source(
                "Альфа-Банк",
                {"id": "alfa_web_actions", "value": root_url, "required": False},
                datetime(2026, 11, 4, tzinfo=timezone.utc),
                datetime(2026, 11, 4, 23, tzinfo=timezone.utc),
            )
        self.assertEqual("limited", coverage.status)
        self.assertEqual(35, len(items))
        self.assertEqual(40, len(coverage.catalog_launch_hints))
        self.assertEqual(5, sum(
            not lead["document_fetched"]
            for lead in coverage.catalog_launch_hints
        ))
        self.assertTrue(all(
            lead["start_hint"] == "2026-11-01"
            for lead in coverage.catalog_launch_hints
        ))


if __name__ == "__main__":
    unittest.main()
