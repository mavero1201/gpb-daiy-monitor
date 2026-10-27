"""A successful HTTP response with zero offers is not evidence of full coverage."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from bs4 import BeautifulSoup
from collector import fetch_web_source
from sources import strict_coverage_failures


class WebCoverageTests(unittest.TestCase):
    def test_empty_web_promo_catalog_is_unverified(self):
        html = "<html><body><h1>Каталог предложений</h1><p>" + ("Акции по картам. " * 30) + "</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        source = {
            "id": "gpb_web_special",
            "value": "https://www.gazprombank.ru/personal/page/special-offers/",
            "required": True,
        }
        with patch("collector._fetch_document", return_value=(soup.get_text(" ", strip=True), soup, source["value"])):
            items, check = fetch_web_source(
                "Газпромбанк", source,
                datetime(2026, 10, 19, tzinfo=timezone.utc),
                datetime(2026, 10, 25, tzinfo=timezone.utc),
            )
        self.assertEqual([], items)
        self.assertEqual("unverified_zero", check.status)
        self.assertTrue(any("gpb_web_special" in issue for issue in strict_coverage_failures([check])))


if __name__ == "__main__":
    unittest.main()
