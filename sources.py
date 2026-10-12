from __future__ import annotations

from urllib.parse import urlparse

VERIFIED_ON = "2026-10-07"

# Канонический реестр источников мониторинга Daily Banking.
# automatic=True  -> источник реально обходится еженедельным collector.
# automatic=False -> источник закреплён как официальный reference/discovery,
#                    но не считается обязательным для полноты выпуска.
#
# MAX пока не включён в строгий автоматический обход: официальный API MAX
# позволяет читать ленту канала только боту-администратору этого канала.
# Для каналов конкурентов это условие невыполнимо. Публичные MAX-ссылки
# остаются в реестре и имеют приоритет как источник/доказательство, если
# встречаются в официальных публикациях или правилах.

SOURCE_REGISTRY = [
    {
        "bank": "Газпромбанк",
        "sources": [
            {"id": "gpb_tg", "type": "telegram", "value": "gazprombank", "url": "https://t.me/gazprombank", "role": "official_channel", "required": True, "automatic": True},
            {"id": "gpb_max", "type": "max", "value": "Gazprombank", "url": "https://max.ru/Gazprombank", "role": "official_channel", "required": False, "automatic": False},
            {"id": "gpb_web_special", "type": "web", "value": "https://www.gazprombank.ru/personal/page/special-offers/", "url": "https://www.gazprombank.ru/personal/page/special-offers/", "role": "promotions", "required": True, "automatic": True},
            {"id": "gpb_web_personal", "type": "web", "value": "https://www.gazprombank.ru/personal/page/personal-offers/", "url": "https://www.gazprombank.ru/personal/page/personal-offers/", "role": "personal_offers", "required": False, "automatic": True},
        ],
    },
    {
        "bank": "ВТБ",
        "sources": [
            {"id": "vtb_tg", "type": "telegram", "value": "BankVTB", "url": "https://t.me/BankVTB", "role": "official_channel", "required": True, "automatic": True},
            {"id": "vtb_max", "type": "max", "value": "vtb", "url": "https://max.ru/vtb", "role": "official_channel", "required": False, "automatic": False},
            {"id": "vtb_web_debit", "type": "web", "value": "https://www.vtb.ru/personal/karty/debetovye/", "url": "https://www.vtb.ru/personal/karty/debetovye/", "role": "debit_cards", "required": True, "automatic": True},
            {"id": "vtb_web_cards", "type": "web", "value": "https://www.vtb.ru/personal/karty/", "url": "https://www.vtb.ru/personal/karty/", "role": "cards_promotions", "required": False, "automatic": True},
        ],
    },
    {
        "bank": "Альфа-Банк",
        "sources": [
            {"id": "alfa_tg", "type": "telegram", "value": "alfabank", "url": "https://t.me/alfabank", "role": "official_channel", "required": True, "automatic": True},
            {"id": "alfa_max_bot", "type": "max_bot", "value": "alfabank_bot", "url": "https://max.ru/alfabank_bot", "role": "service_bot_not_content_channel", "required": False, "automatic": False},
            {"id": "alfa_web_actions", "type": "web", "value": "https://alfabank.ru/actions/rules/", "url": "https://alfabank.ru/actions/rules/", "role": "promotion_rules", "required": True, "automatic": True},
            {"id": "alfa_web_debit", "type": "web", "value": "https://alfabank.ru/everyday/debit-cards/alfacard/", "url": "https://alfabank.ru/everyday/debit-cards/alfacard/", "role": "debit_card", "required": False, "automatic": True},
        ],
    },
    {
        "bank": "Сбер",
        "sources": [
            {"id": "sber_tg", "type": "telegram", "value": "sberbank", "url": "https://t.me/sberbank", "role": "official_channel", "required": True, "automatic": True},
            {"id": "sber_max", "type": "max", "value": "sber", "url": "https://max.ru/sber", "role": "official_channel", "required": False, "automatic": False},
            {"id": "sber_web_cards", "type": "web", "value": "https://www.sberbank.com/ru/person/bank_cards", "url": "https://www.sberbank.com/ru/person/bank_cards", "role": "bank_cards", "required": True, "automatic": True},
        ],
    },
    {
        "bank": "Т-Банк",
        "sources": [
            {"id": "tbank_tg", "type": "telegram", "value": "tbank", "url": "https://t.me/tbank", "role": "official_channel", "required": True, "automatic": True},
            {"id": "tbank_max", "type": "max", "value": "tbank", "url": "https://max.ru/tbank", "role": "official_channel", "required": False, "automatic": False},
            {"id": "tbank_web_debit", "type": "web", "value": "https://www.tbank.ru/cards/debit-cards/", "url": "https://www.tbank.ru/cards/debit-cards/", "role": "debit_cards", "required": True, "automatic": True},
            {"id": "tbank_web_news", "type": "web", "value": "https://www.tbank.ru/about/news/", "url": "https://www.tbank.ru/about/news/", "role": "news", "required": False, "automatic": True},
        ],
    },
    {
        "bank": "Ozon Банк",
        "sources": [
            {"id": "ozon_tg", "type": "telegram", "value": "ozon_bank_official", "url": "https://t.me/ozon_bank_official", "role": "official_channel", "required": True, "automatic": True},
            {"id": "ozon_max", "type": "max", "value": "ozonbank", "url": "https://max.ru/ozonbank", "role": "official_channel", "required": False, "automatic": False},
            {"id": "ozon_web_products", "type": "web", "value": "https://finance.ozon.ru/products", "url": "https://finance.ozon.ru/products", "role": "products", "required": True, "automatic": True},
            {"id": "ozon_web_card", "type": "web", "value": "https://finance.ozon.ru/promo/cards", "url": "https://finance.ozon.ru/promo/cards", "role": "debit_card_promotions", "required": False, "automatic": True},
        ],
    },
    {
        "bank": "Яндекс Банк",
        "sources": [
            {"id": "yandex_tg", "type": "telegram", "value": "yandexfintech", "url": "https://t.me/yandexfintech", "role": "official_yandex_pay_channel", "required": True, "automatic": True},
            {"id": "yandex_max_unconfirmed", "type": "max", "value": "", "url": "", "role": "no_dedicated_content_channel_confirmed", "required": False, "automatic": False},
            {"id": "yandex_web_account", "type": "web", "value": "https://yabank.yandex.ru/account", "url": "https://yabank.yandex.ru/account", "role": "account", "required": False, "required_any_group": "yandex_official_web", "automatic": True},
            {"id": "yandex_web_pay", "type": "web", "value": "https://pay.yandex.ru/", "url": "https://pay.yandex.ru/", "role": "pay", "required": False, "required_any_group": "yandex_official_web", "automatic": True},
            {"id": "yandex_web_cashback", "type": "web", "value": "https://yandex.ru/support/pay/ru/cashback", "url": "https://yandex.ru/support/pay/ru/cashback", "role": "cashback_rules", "required": False, "required_any_group": "yandex_official_web", "automatic": True},
        ],
    },
    {
        "bank": "ПСБ",
        "sources": [
            {"id": "psb_tg", "type": "telegram", "value": "psbbank", "url": "https://t.me/psbbank", "role": "official_channel", "required": True, "automatic": True},
            {"id": "psb_max", "type": "max", "value": "psb", "url": "https://max.ru/psb", "role": "official_channel", "required": False, "automatic": False},
            {"id": "psb_web_rules", "type": "web", "value": "https://www.psbank.ru/personal/cards/rules", "url": "https://www.psbank.ru/personal/cards/rules", "role": "card_rules_and_promotions", "required": True, "automatic": True},
        ],
    },
    {
        "bank": "Совкомбанк",
        "sources": [
            {"id": "sovcom_tg", "type": "telegram", "value": "sovcombankofficial", "url": "https://t.me/sovcombankofficial", "role": "official_channel", "required": True, "automatic": True},
            {"id": "sovcom_max", "type": "max", "value": "sovcombank", "url": "https://max.ru/sovcombank", "role": "official_channel", "required": False, "automatic": False},
            {"id": "sovcom_web_actions", "type": "web", "value": "https://sovcombank.ru/pages/vse-aktsii-karti-halva-", "url": "https://sovcombank.ru/pages/vse-aktsii-karti-halva-", "role": "halva_promotions", "required": True, "automatic": True},
        ],
    },
    {
        "bank": "МТС Банк",
        "sources": [
            {"id": "mts_tg", "type": "telegram", "value": "mts_bank_official", "url": "https://t.me/mts_bank_official", "role": "official_channel", "required": True, "automatic": True},
            {"id": "mts_max", "type": "max", "value": "mts_bank_official", "url": "https://max.ru/mts_bank_official", "role": "official_channel", "required": False, "automatic": False},
            {"id": "mts_web_tariffs", "type": "web", "value": "https://www.mtsbank.ru/chastnim-licam/tarif/", "url": "https://www.mtsbank.ru/chastnim-licam/tarif/", "role": "tariffs_and_promotion_rules", "required": True, "automatic": True},
            {"id": "mts_web_debit", "type": "web", "value": "https://www.mtsbank.ru/chastnim-licam/karti/all/debet/", "url": "https://www.mtsbank.ru/chastnim-licam/karti/all/debet/", "role": "debit_cards", "required": False, "automatic": True},
        ],
    },
    {
        "bank": "ОТП Банк",
        "sources": [
            {"id": "otp_tg", "type": "telegram", "value": "otpbanknews", "url": "https://t.me/otpbanknews", "role": "official_channel", "required": True, "automatic": True},
            {"id": "otp_max", "type": "max", "value": "otpbanknews", "url": "https://max.ru/otpbanknews", "role": "official_channel", "required": False, "automatic": False},
            {"id": "otp_web_card", "type": "web", "value": "https://www.otpbank.ru/retail/cards/debit/otpcard/", "url": "https://www.otpbank.ru/retail/cards/debit/otpcard/", "role": "debit_card", "required": True, "automatic": True},
            {"id": "otp_web_new", "type": "web", "value": "https://www.otpbank.ru/new/", "url": "https://www.otpbank.ru/new/", "role": "new_offers", "required": False, "automatic": True},
        ],
    },
    {
        "bank": "Wildberries Банк",
        "sources": [
            {"id": "wb_tg_ecosystem", "type": "telegram", "value": "wildberriesofficialcustomer", "url": "https://t.me/wildberriesofficialcustomer", "role": "official_wildberries_ecosystem_channel", "required": False, "automatic": True},
            {"id": "wb_max_ecosystem", "type": "max", "value": "wildberriesru_official", "url": "https://max.ru/wildberriesru_official", "role": "official_wildberries_ecosystem_channel", "required": False, "automatic": False},
            {"id": "wb_web_docs", "type": "web", "value": "https://wb-bank.ru/documents", "url": "https://wb-bank.ru/documents", "role": "bank_documents_and_rules", "required": True, "automatic": True},
        ],
    },
]


def _automatic_sources(entry: dict) -> list[dict]:
    result = []
    for source in entry["sources"]:
        if not source.get("automatic"):
            continue
        if source["type"] not in {"telegram", "web"}:
            continue
        result.append(
            {
                "id": source["id"],
                "type": source["type"],
                "value": source["value"],
                "required": source.get("required", False),
                "required_any_group": source.get("required_any_group"),
            }
        )
    return result


BANK_SOURCES = [
    {"bank": entry["bank"], "sources": _automatic_sources(entry)}
    for entry in SOURCE_REGISTRY
]

BANKS = [item["bank"] for item in BANK_SOURCES]


def reference_urls(bank: str) -> list[str]:
    for entry in SOURCE_REGISTRY:
        if entry["bank"] == bank:
            return [s["url"] for s in entry["sources"] if s.get("url")]
    return []


def official_link_priority(bank: str, url: str) -> int:
    """Smaller value = stronger/officialer evidence for this bank."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return 9

    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()

    for ref in reference_urls(bank):
        ref_parsed = urlparse(ref)
        ref_host = (ref_parsed.hostname or "").lower()
        ref_path = ref_parsed.path.rstrip("/").lower()

        if host == ref_host and (not ref_path or path.startswith(ref_path)):
            return 0

    # Official MAX post under the registered channel path.
    if host in {"max.ru", "www.max.ru"}:
        return 1

    # Other links are still allowed because banks often use redirectors
    # (clck.ru, appmetrica, short links) to reach official rules.
    return 5


def required_any_groups() -> list[dict]:
    groups: dict[tuple[str, str], list[str]] = {}
    for entry in SOURCE_REGISTRY:
        bank = entry["bank"]
        for source in entry["sources"]:
            group = source.get("required_any_group")
            if not group or not source.get("automatic"):
                continue
            groups.setdefault((bank, group), []).append(source["id"])

    return [
        {"bank": bank, "group": group, "source_ids": source_ids}
        for (bank, group), source_ids in groups.items()
    ]


def strict_coverage_failures(source_checks) -> list[str]:
    failures = [
        f"{check.bank}:{check.source_id}:{check.status}"
        for check in source_checks
        if check.required and check.status != "ok"
    ]

    checks_by_key = {
        (check.bank, check.source_id): check
        for check in source_checks
    }

    for group in required_any_groups():
        statuses = [
            checks_by_key[(group["bank"], source_id)].status
            for source_id in group["source_ids"]
            if (group["bank"], source_id) in checks_by_key
        ]
        if not statuses or not any(status == "ok" for status in statuses):
            failures.append(
                f'{group["bank"]}:{group["group"]}:all_unavailable'
            )

    return failures


def bank_fully_checked(bank: str, source_checks) -> bool:
    bank_checks = [check for check in source_checks if check.bank == bank]
    required_checks = [check for check in bank_checks if check.required]

    if required_checks and not all(check.status == "ok" for check in required_checks):
        return False

    groups = [group for group in required_any_groups() if group["bank"] == bank]
    by_id = {check.source_id: check for check in bank_checks}

    for group in groups:
        statuses = [
            by_id[source_id].status
            for source_id in group["source_ids"]
            if source_id in by_id
        ]
        if not statuses or not any(status == "ok" for status in statuses):
            return False

    return bool(required_checks or groups)
