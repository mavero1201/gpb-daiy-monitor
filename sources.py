BANK_SOURCES = [
    {
        "bank": "Газпромбанк",
        "sources": [
            {"id": "gpb_tg", "type": "telegram", "value": "gazprombank", "required": True},
            {"id": "gpb_web_special", "type": "web", "value": "https://www.gazprombank.ru/personal/page/special-offers/", "required": True},
        ],
    },
    {
        "bank": "ВТБ",
        "sources": [
            {"id": "vtb_tg", "type": "telegram", "value": "BankVTB", "required": True},
            {"id": "vtb_web_debit", "type": "web", "value": "https://www.vtb.ru/personal/karty/debetovye/", "required": True},
        ],
    },
    {
        "bank": "Альфа-Банк",
        "sources": [
            {"id": "alfa_tg", "type": "telegram", "value": "alfabank", "required": True},
            {"id": "alfa_web_debit", "type": "web", "value": "https://alfabank.ru/everyday/debit-cards/alfacard/", "required": True},
        ],
    },
    {
        "bank": "Сбер",
        "sources": [
            {"id": "sber_tg", "type": "telegram", "value": "sberbank", "required": True},
        ],
    },
    {
        "bank": "Т-Банк",
        "sources": [
            {"id": "tbank_tg", "type": "telegram", "value": "tbank", "required": True},
            {"id": "tbank_web_debit", "type": "web", "value": "https://www.tbank.ru/cards/debit-cards/", "required": True},
        ],
    },
    {
        "bank": "Ozon Банк",
        "sources": [
            {"id": "ozon_tg", "type": "telegram", "value": "ozon_bank_official", "required": True},
        ],
    },
    {
        "bank": "Яндекс Банк",
        "sources": [
            {"id": "yandex_tg", "type": "telegram", "value": "yandexfintech", "required": True},
            {"id": "yandex_web_pay", "type": "web", "value": "https://bank.yandex.ru/pay?from=home", "required": True},
        ],
    },
    {
        "bank": "ПСБ",
        "sources": [
            {"id": "psb_tg", "type": "telegram", "value": "psbbank", "required": True},
            {"id": "psb_web_rules", "type": "web", "value": "https://www.psbank.ru/personal/cards/rules", "required": True},
        ],
    },
    {
        "bank": "Совкомбанк",
        "sources": [
            {"id": "sovcom_tg", "type": "telegram", "value": "sovcombankofficial", "required": True},
            {"id": "sovcom_web_actions", "type": "web", "value": "https://sovcombank.ru/pages/vse-aktsii-karti-halva-", "required": True},
        ],
    },
    {
        "bank": "МТС Банк",
        "sources": [
            {"id": "mts_tg", "type": "telegram", "value": "mts_bank_official", "required": True},
            {"id": "mts_web_debit", "type": "web", "value": "https://www.mtsbank.ru/chastnim-licam/karti/all/debet/", "required": True},
        ],
    },
    {
        "bank": "ОТП Банк",
        "sources": [
            {"id": "otp_tg", "type": "telegram", "value": "otpbanknews", "required": True},
        ],
    },
    {
        "bank": "Wildberries Банк",
        "sources": [
            {"id": "wb_web_docs", "type": "web", "value": "https://wb-bank.ru/documents", "required": True},
        ],
    },
]

BANKS = [item["bank"] for item in BANK_SOURCES]
