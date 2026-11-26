"""Evidence-based regression controls from Sabina's October manual register.

The screenshots establish a benchmarking target, not independently verified
bank rules. Tests must not convert those dates into published offer facts.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

import collector
import evaluator
import pipeline
import quality
from sources import BANK_SOURCES, BANKS

FIXTURE = Path(__file__).parent / "fixtures" / "sabina_october_2026.json"


class SabinaOctoberControls(unittest.TestCase):
    def test_manual_register_has_34_separately_identified_offers(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        items = data["items"]
        self.assertEqual(34, len(items))
        self.assertEqual(34, len({item["id"] for item in items}))
        self.assertEqual(7, sum(i["campaign_start"] >= "2026-10-19" for i in items))
        self.assertEqual(2, sum(i["review_state"] == "historical_published" for i in items))
        self.assertIn("NOT verified", data["methodology"])

    def test_existing_mass_market_scope_not_widened_for_kids(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        child = next(i for i in data["items"] if i["id"] == 7)
        self.assertEqual("out_of_scope_child_cards", child["review_state"])
        self.assertFalse(evaluator.evaluate(collector.RawItem(
            bank="Сбер", source_id="test", source_type="telegram",
            published_at=datetime(2026, 10, 2, tzinfo=ZoneInfo("Europe/Moscow")),
            text="Акция: детская карта, оформите Детскую карту за бонусы",
            url="https://t.me/sberbank/1", external_links=[],
        )).included)

    def test_named_campaign_period_overrides_unrelated_qualifying_period(self):
        text = (
            "Период выполнения покупок с 10.08.2026 по 20.02.2027. "
            "Период проведения Акции - с 08.10.2026 по 28.02.2027. "
            "Срок выплаты приза по 10.03.2027."
        )
        value, evidence = evaluator.declared_campaign_period(text, date(2026, 10, 28))
        self.assertEqual((date(2026, 10, 8), date(2027, 2, 28)), value)
        self.assertIn("Период проведения Акции", evidence)

    def test_otp_salary_benchmark_has_distinct_campaign_dates(self):
        reference = json.loads(FIXTURE.read_text(encoding="utf-8"))
        salary = next(i for i in reference["items"] if i["id"] == 19)
        self.assertEqual("2026-10-28", salary["campaign_start"])
        text = (
            "Правила Акции. Розыгрыш 100 000 бонусных рублей за "
            "зачисление зарплаты на карту ОТП Банка. "
            "Период проведения акции: с 28.10.2026 по 31.01.2027. "
            "Период начисления бонусов с 01.02.2027 по 28.02.2027."
        )
        value, _ = evaluator.declared_campaign_period(text, date(2026, 10, 28))
        self.assertEqual(
            (date.fromisoformat(salary["campaign_start"]),
             date.fromisoformat(salary["campaign_end"])), value,
        )

    def test_otp_jetour_deadline_is_not_campaign_period(self):
        text = (
            "Розыгрыш автомобиля за оформление карты ОТП Банка и покупку. "
            "Подайте заявку до 23 ноября 2026 года."
        )
        value, _ = evaluator.declared_campaign_period(text, date(2026, 10, 30))
        self.assertIsNone(value)
        self.assertIsNone(evaluator.extract_period(text, date(2026, 10, 30)))
        self.assertEqual("deadline_only", evaluator.extract_date_hint(text)[0])

    def test_conflicting_declared_campaign_periods_fail_closed(self):
        text = (
            "Период проведения Акции с 01.10.2026 по 30.10.2026. "
            "Период проведения Акции с 01.11.2026 по 30.11.2026."
        )
        value, info = evaluator.declared_campaign_period(text, date(2026, 10, 1))
        self.assertIsNone(value)
        self.assertEqual("conflicting_campaign_periods", info)

    def test_certificate_is_reward_not_merely_purchase_amount(self):
        post = (
            "Правила проведения акции. Оформите дебетовую карту ПСБ и "
            "совершите покупки от 1000 ₽. Получите подарочный сертификат "
            "номиналом 3000 ₽. Период проведения Акции: "
            "с 01.10.2026 по 30.10.2026."
        )
        reward = evaluator.extract_reward(post, post, "ПСБ")
        self.assertEqual("Сертификат 3000 ₽", reward)
        self.assertEqual("сертификат", evaluator.classify_mechanic(post))
        self.assertTrue(evaluator.has_customer_action(post))

    def test_certificate_does_not_borrow_purchase_threshold(self):
        post = (
            "Оформите банковскую карту и получите сертификат за покупки "
            "на сумму от 3000 ₽. Номинал сертификата в посте не указан."
        )
        reward = evaluator.extract_reward(post, post, "ПСБ")
        self.assertNotEqual("Сертификат 3000 ₽", reward)

    def test_source_registry_has_new_verified_official_entry_points(self):
        mapped = {entry["bank"]: {s["id"]: s for s in entry["sources"]} for entry in BANK_SOURCES}
        self.assertEqual(12, len(BANKS))
        for bank, source in [
            ("ПСБ", "psb_web_cashback"),
            ("ПСБ", "psb_web_10percent"),
            ("ОТП Банк", "otp_web_card_promos"),
            ("Сбер", "sber_web_spasibo"),
        ]:
            self.assertIn(source, mapped[bank])
            self.assertFalse(mapped[bank][source]["required"])

    def test_catalog_index_captures_nonpromo_documents_before_filter(self):
        source = {"id":"psb_web_rules", "value":"https://www.psbank.ru/personal/cards/rules", "role":"rules", "required":True}
        root = BeautifulSoup('<html><body><a href="/promo/one.pdf">Правила акции карта</a><a href="/promo/two.pdf">Правила акции тариф</a></body></html>',"html.parser")
        documents = {
            "https://www.psbank.ru/promo/one.pdf":("Правила проведения акции. Оформите дебетовую карту ПСБ. Сертификат 3000 рублей. Период проведения Акции: с 01.10.2026 по 30.10.2026. " * 2,None,"https://www.psbank.ru/promo/one.pdf"),
            "https://www.psbank.ru/promo/two.pdf":("Обычный банковский тариф для держателей карты, ставки и тарифные комиссии. " * 3,None,"https://www.psbank.ru/promo/two.pdf"),
        }
        def get_doc(url):
            if url == source["value"]:
                return "Правила акции: список доступных документов для держателей карт ПСБ. " * 3,root,url
            return documents[url]
        begin=datetime(2026,10,19,tzinfo=ZoneInfo("Europe/Moscow"))
        end=datetime(2026,10,25,tzinfo=ZoneInfo("Europe/Moscow"))
        with patch.object(collector, "_fetch_document", side_effect=get_doc):
            raw, check = collector.fetch_web_source("ПСБ", source, begin, end)
        self.assertEqual(2, len(check.catalog_index) - 1)
        stages={e["url"]:e["stage"] for e in check.catalog_index}
        self.assertIn("raw_item_created", stages.values())
        self.assertIn("prefilter_no_promo_signal", stages.values())
        self.assertTrue(all(r.url.startswith("https://www.psbank.ru") for r in raw))

    def test_pipeline_writes_audit_of_rejections_and_skipped_catalog_links(self):
        start=datetime(2026,10,19,tzinfo=ZoneInfo("Europe/Moscow"))
        end=datetime(2026,10,25,tzinfo=ZoneInfo("Europe/Moscow"))
        item=SimpleNamespace(
            bank="ОТП Банк", source_id="otp_tg", source_type="telegram",
            published_at=start, text="Розыгрыш 100000 бонусов за зачисление зарплаты на карту ОТП Банка.",
            raw_html="<div>test post</div>",
            url="https://t.me/otpbanknews/1919", external_links=[],
        )
        res=SimpleNamespace(
            included=False,reason="no_exact_period_after_recheck",
            promo_start=None,promo_end=None,title="",reward="",conditions="",
            mechanic="",date_status="deadline_only",date_evidence="до 30 ноября",
            evidence_url=item.url,
        )
        check=SimpleNamespace(
            bank="ОТП Банк",source_id="otp_card",source_type="web",
            source_value="https://www.otpbank.ru/retail/cards/debit/otpcard/",
            status="limited",required=True,item_count=0,error="no readable rules",
            catalog_index=[{
                "url":"https://www.otpbank.ru/document/promo.pdf",
                "stage":"not_fetched_link_cap","link_label":"Правила акции",
                "date_hint_unverified":"","source_text_excerpt":"",
            }],
        )
        with tempfile.TemporaryDirectory() as root:
            with patch.object(pipeline,"ARTIFACT_DIR",Path(root)):
                paths=pipeline.write_audit(start,end,[(item,res)],[check])
            rawfile=next(p for p in paths if p.name.startswith("raw_source_items_"))
            catalogfile=next(p for p in paths if p.name.startswith("catalog_discovery_"))
            with rawfile.open(encoding="utf-8-sig") as f:
                first=list(csv.DictReader(f,delimiter=";"))[0]
            self.assertEqual("no_exact_period_after_recheck",first["decision_reason"])
            self.assertIn("100000 бонусов",first["raw_text"])
            self.assertEqual("<div>test post</div>",first["raw_html"])
            with catalogfile.open(encoding="utf-8-sig") as f:
                record=list(csv.DictReader(f,delimiter=";"))[0]
            self.assertEqual("not_fetched_link_cap",record["discovery_stage"])


if __name__ == "__main__":
    unittest.main()
