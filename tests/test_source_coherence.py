import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from evaluator import Evaluation, evaluate
from quality import validate_card


def item(text, links=()):
    return SimpleNamespace(
        bank="ВТБ", text=text, published_at=datetime(2026, 10, 22, tzinfo=timezone.utc),
        url="https://t.me/bankvtb/3883", external_links=list(links),
        source_type="telegram", source_id="vtb_tg",
    )


class SourceCoherenceTests(unittest.TestCase):
    def test_unrelated_page_period_does_not_create_card(self):
        post = "Оплатите картой ВТБ покупку и получите 6% кешбэка."
        other = "Другая акция действует с 01.10.2026 по 31.10.2026."
        with patch("evaluator.build_evidence", return_value=(post + " " + other, "https://vtb.ru/other")), \
             patch("evaluator.recheck_exact_period", return_value=(None, post + " " + other, "https://vtb.ru/other")):
            result = evaluate(item(post))
        self.assertEqual(result.reason, "no_exact_period_after_recheck")

    def test_other_page_cannot_supply_reward_or_conditions(self):
        post = "Оплатите картой ВТБ и получите подарок. С 19.10.2026 по 25.10.2026."
        other = "Оплатите подписку и получите 15% кешбэка."
        with patch("evaluator.build_evidence", return_value=(post + " " + other, "https://vtb.ru/other")):
            result = evaluate(item(post))
        self.assertFalse(result.included)
        self.assertEqual(result.reason, "no_reward")

    def test_review_queue_keeps_rejected_candidate(self):
        from pipeline import write_audit
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import pipeline
        candidate = Evaluation(False, "no_exact_period_after_recheck")
        with TemporaryDirectory() as tmp:
            with patch.object(pipeline, "ARTIFACT_DIR", Path(tmp)), \
                 patch.object(pipeline, "BANKS", ["ВТБ"]):
                paths = write_audit(
                    datetime(2026, 10, 19, tzinfo=timezone.utc),
                    datetime(2026, 10, 25, tzinfo=timezone.utc),
                    [(item("Текст исходной акции"), candidate)], [],
                )
            queue = next(p for p in paths if "review_queue" in str(p))
            self.assertIn("Текст исходной акции", queue.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
