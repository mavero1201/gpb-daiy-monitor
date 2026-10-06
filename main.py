import argparse
import os
import sys

import requests

DEFAULT_CHAT_ID = "-1004291568481"


def send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", DEFAULT_CHAT_ID)

    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Add it as a GitHub Actions repository secret."
        )

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
            "parse_mode": "HTML",
        },
        timeout=30,
    )
    response.raise_for_status()

    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API returned an error: {payload}")


def main() -> int:
    parser = argparse.ArgumentParser(description="GPB Daily Banking promo monitor")
    parser.add_argument(
        "--test-telegram",
        action="store_true",
        help="Send a one-off test message to the configured Telegram channel.",
    )
    args = parser.parse_args()

    if args.test_telegram:
        send_telegram(
            "✅ GPB Daily Monitor: GitHub Actions подключен. "
            "Тестовая публикация прошла успешно."
        )
        print("Telegram test message sent.")
        return 0

    print("No action selected. Use --test-telegram for the connection test.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
