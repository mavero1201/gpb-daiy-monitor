"""Find candidate official campaign documents when a bank post omits the dates.

Search results are only navigation. Never treat a search snippet as evidence:
the evaluator must fetch the actual official document and match its offer.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests

from sources import reference_urls

EXTRA_OFFICIAL_HOSTS = {
    "Сбер": ("sberbank.ru",),
    "ПСБ": ("psbank.ru",),
}


def official_hosts(bank: str) -> set[str]:
    hosts = set(EXTRA_OFFICIAL_HOSTS.get(bank, ()))
    for url in reference_urls(bank):
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        if host and host not in {"t.me", "max.ru"}:
            hosts.add(host)
    return hosts


def is_official_document_url(bank: str, url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if parsed.scheme != "https" or not host:
        return False
    if any(host == allowed or host.endswith("." + allowed) for allowed in official_hosts(bank)):
        return True
    return False


def discover_official_rule_urls(bank: str, post_text: str, limit: int = 4) -> list[str]:
    """Best-effort official-site discovery, bounded to two web searches.

    A failed or blocked search must never imply there are no campaign rules.
    The result is a list of URLs for further validation, not verified offers.
    """
    hosts = official_hosts(bank)
    if not hosts:
        return []
    # Keep distinctive reward amounts and words; do not search with an entire
    # social post containing unrelated offers, emoji and boilerplate.
    amounts = re.findall(r"\d[\d\s]{0,9}\s*(?:₽|%|руб\w*|млн)", post_text.lower())[:2]
    words = re.findall(r"[а-яёa-z]{4,}", post_text.lower())
    stop = {"которые", "чтобы", "можете", "будет", "только", "когда", "всего",
            "сегодня", "покупки", "банка", "карты", "акция", "акции"}
    terms = list(dict.fromkeys(w for w in words if w not in stop))[:7]
    if not terms and not amounts:
        return []
    query = " ".join([bank, *amounts, *terms[:5], "правила акции"])
    results: list[str] = []
    # Search a small number of official domains, not the open web.
    for host in sorted(hosts)[:2]:
        try:
            response = requests.get(
                "https://www.bing.com/search",
                params={"q": f"site:{host} {query}", "format": "rss"},
                timeout=12,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
            links = [node.text for node in root.findall(".//item/link") if node.text]
        except Exception:
            continue
        for url in links:
            if is_official_document_url(bank, url) and url not in results:
                results.append(url)
                if len(results) >= limit:
                    return results
    return results
