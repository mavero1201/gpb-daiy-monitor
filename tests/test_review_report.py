import tempfile
import unittest
from datetime import date
from pathlib import Path

from review_report import report_html, write_review_report


class ReviewReportTests(unittest.TestCase):
    def test_distinguishes_current_and_older_publications_and_escapes_html(self):
        current = dict(bank="ВТБ", published_at="2026-10-22T10:00:00+03:00",
                       url="https://t.me/bankvtb/3882", title="<script>alert(1)</script>",
                       reason="no_exact_period_after_recheck", source_text="Скидка 6%",
                       reward="", date_evidence="")
        older = dict(current, published_at="2026-10-12T10:00:00+03:00",
                     title="Старое предложение")
        sources = [
            dict(bank="ВТБ", source_id="vtb_web", type="web", status="ok", item_count="0"),
            dict(bank="ВТБ", source_id="vtb_tg", type="telegram", status="ok", item_count="10"),
        ]
        html = report_html([current, older], sources, date(2026, 10, 19), date(2026, 10, 25))
        self.assertIn("Публикации отчётной недели (1)", html)
        self.assertIn("Вне отчётной недели (1)", html)
        self.assertIn("1 / 1", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>alert", html)
        self.assertIn("не подтверждённые акции", html)

    def test_creates_file_from_audit_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            name = "2026-10-19_2026-10-25"
            (root / f"review_queue_{name}.csv").write_text(
                "bank;published_at;url;title;reason;source_text\n"
                "ПСБ;2026-10-20;https://t.me/psbbank/3741;Суперкешбэк;"
                "activity_month_only_needs_terms;Текст\n",
                encoding="utf-8",
            )
            (root / f"audit_sources_{name}.csv").write_text(
                "bank;source_id;type;status;item_count\n"
                "ПСБ;psb_web;web;ok;0\n", encoding="utf-8",
            )
            result = write_review_report(root, date(2026, 10, 19), date(2026, 10, 25))
            self.assertTrue(result.is_file())
            self.assertIn("Суперкешбэк", result.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
