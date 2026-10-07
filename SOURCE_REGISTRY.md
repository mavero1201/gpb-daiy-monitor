# Реестр источников Daily Banking

Проверено: 07.10.2026.

Это канонический список источников для недельного мониторинга 12 банков.  
Правило: новые источники не подменяют этот список автоматически. Изменение реестра делается отдельно и осознанно.

| Банк | Telegram | MAX | Основные web-источники |
|---|---|---|---|
| Газпромбанк | https://t.me/gazprombank | https://max.ru/Gazprombank | https://www.gazprombank.ru/personal/page/special-offers/ ; https://www.gazprombank.ru/personal/page/personal-offers/ |
| ВТБ | https://t.me/BankVTB | https://max.ru/vtb | https://www.vtb.ru/personal/karty/debetovye/ ; https://www.vtb.ru/personal/karty/ |
| Альфа-Банк | https://t.me/alfabank | Публичный контент-канал не подтверждён. Есть сервисный бот https://max.ru/alfabank_bot, он не используется как контент-источник | https://alfabank.ru/actions/rules/ ; https://alfabank.ru/everyday/debit-cards/alfacard/ |
| Сбер | https://t.me/sberbank | https://max.ru/sber | https://www.sberbank.com/ru/person/bank_cards |
| Т-Банк | https://t.me/tbank | https://max.ru/tbank | https://www.tbank.ru/cards/debit-cards/ ; https://www.tbank.ru/about/news/ |
| Ozon Банк | https://t.me/ozon_bank_official | https://max.ru/ozonbank | https://finance.ozon.ru/products ; https://finance.ozon.ru/promo/cards |
| Яндекс Банк | https://t.me/yandexfintech | Отдельный официальный контент-канал MAX не подтверждён | https://yabank.yandex.ru/account ; https://pay.yandex.ru/ ; https://yandex.ru/support/pay/ru/cashback |
| ПСБ | https://t.me/psbbank | https://max.ru/psb | https://www.psbank.ru/personal/cards/rules |
| Совкомбанк | https://t.me/sovcombankofficial | https://max.ru/sovcombank | https://sovcombank.ru/pages/vse-aktsii-karti-halva- |
| МТС Банк | https://t.me/mts_bank_official | https://max.ru/mts_bank_official | https://www.mtsbank.ru/chastnim-licam/tarif/ ; https://www.mtsbank.ru/chastnim-licam/karti/all/debet/ |
| ОТП Банк | https://t.me/otpbanknews | https://max.ru/otpbanknews | https://www.otpbank.ru/retail/cards/debit/otpcard/ ; https://www.otpbank.ru/new/ |
| Wildberries Банк | Отдельный официальный consumer-канал WB Банка не подтверждён. Secondary: https://t.me/wildberriesofficialcustomer | Отдельный канал WB Банка не подтверждён. Secondary: https://max.ru/wildberriesru_official | https://wb-bank.ru/documents |

## Как реестр используется алгоритмом

1. **Строгий автоматический слой** - официальные Telegram-каналы и web-страницы, помеченные в `sources.py` как `automatic=True`. Обязательные источники имеют `required=True`. Если обязательный источник не проверен, выпуск не публикуется.
2. **MAX** - закреплён как официальный reference/discovery-слой. Ссылки на зарегистрированные MAX-каналы и посты получают приоритет при верификации условий, если они встречаются в официальных публикациях или правилах.
3. MAX не является блокирующим источником полноты выпуска. Официальный MAX API позволяет читать ленту канала через `GET /messages` только если бот является администратором этого канала. Для каналов банков-конкурентов это технически невозможно.
4. Для Wildberries Банка официальные consumer-каналы самого банка не подтверждены, поэтому каналы экосистемы Wildberries используются только как secondary discovery, а обязательным источником остаётся официальный сайт WB Банка.
5. Если появляется новый официальный канал или банк меняет URL раздела, сначала обновляется этот реестр, затем алгоритм.

## Приоритет доказательств

При проверке акции:
1. официальный раздел правил / карточка акции банка;
2. официальный Telegram;
3. зарегистрированный официальный MAX-пост;
4. другие ссылки из официальной публикации;
5. сторонний источник может использоваться только для обнаружения, но не заменяет первичный источник для финальной карточки.
