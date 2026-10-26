"""Publish the exact approved GitHub artifact, without recollecting sources.

Only a separate, explicitly confirmed GitHub Actions dispatch may call this.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from main import send_telegram


def validate_preview(text: str) -> None:
    required = (
        "<b>Мониторинг акций Daily Banking</b>",
        "<b>Вознаграждение</b>",
        "<b>Условия</b>",
        "<b>Механика</b>",
        "<b>Срок акции</b>",
        "Источник</a>",
    )
    if not all(token in text for token in required):
        raise ValueError("The selected artifact contains no complete approved promo cards")
    if "Нет предложений, прошедших проверку для публикации." in text:
        raise ValueError("Empty preview must not be published")
    if re.search(r"<(?:script|iframe|img)\b", text, re.I):
        raise ValueError("Unexpected HTML in the publication candidate")


def message_parts(text: str, max_chars: int = 3900) -> list[str]:
    blocks = text.split("\n\n")
    parts: list[str] = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            parts.append(current)
        if len(block) > max_chars:
            raise ValueError("Single promo block exceeds Telegram message limit")
        current = block
    if current:
        parts.append(current)
    return parts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", required=True)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if not args.confirm:
        raise SystemExit("Explicit confirmation is required")
    path = Path(args.preview)
    text = path.read_text(encoding="utf-8")
    validate_preview(text)
    for part in message_parts(text):
        send_telegram(part)


if __name__ == "__main__":
    main()
