"""Human-readable audit report. This never approves or publishes offers.

Reads the existing audit CSVs; no network, Telegram, or publication-state writes.
"""
from __future__ import annotations

import csv
from collections import Counter
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import urlparse


REASON_LABELS = {
    "no_exact_period_after_recheck": "Не подтверждён период акции",
    "deadline_only_needs_start": "Есть дедлайн, нет даты начала",
    "activity_month_only_needs_terms": "Указан месяц покупок, нет полного срока",
    "multiple_offers_require_split": "Несколько предложений в одном сообщении",
    "quality_single_day_requires_review": "Однодневная акция, нужна проверка",
    "no_reward": "Не определено вознаграждение",
    "no_conditions": "Не определены условия",
    "quality_unstructured_card": "Нужна редактура карточки",
    "quality_irrelevant_text": "Возможна нерелевантная публикация",
    "quality_mechanic_mismatch": "Не совпадает механика",
    "quality_unverified_reward": "Не подтверждено вознаграждение",
    "quality_unknown_mechanic": "Неизвестная механика",
    "quality_no_bank_product_link": "Не подтверждена связь с банковским продуктом",
    "quality_missing_required_field": "Нет обязательного поля",
    "quality_invalid_source": "Некорректный адрес источника",
}


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=";"))


def report_html(
    review: list[dict[str, str]],
    sources: list[dict[str, str]],
    start: date,
    end: date,
) -> str:
    """Review queue is not a list of confirmed promotions."""
    current, historical = [], []
    for row in review:
        try:
            published = date.fromisoformat(row["published_at"][:10])
        except (ValueError, KeyError):
            historical.append(row)
            continue
        (current if start <= published <= end else historical).append(row)

    def h(value: str) -> str:
        return escape(str(value or ""), quote=True)

    def link(url: str) -> str:
        parsed = urlparse(url or "")
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            return "Нет корректной ссылки"
        return f'<a href="{h(url)}" target="_blank" rel="noopener noreferrer">Оригинал</a>'

    def cards(rows: list[dict[str, str]]) -> str:
        if not rows:
            return "<p>Нет материалов.</p>"
        parts = []
        for row in sorted(rows, key=lambda x: (x.get("bank", ""), x.get("published_at", ""))):
            title = row.get("title") or row.get("source_text", "")[:160]
            source_text = row.get("source_text", "")
            reason = REASON_LABELS.get(row.get("reason", ""), row.get("reason", ""))
            date_hint = row.get("date_evidence", "")
            reward = row.get("reward", "")
            parts.append(
                '<article class="item">'
                f'<div class="meta"><b>{h(row.get("bank", ""))}</b>'
                f' · {h(row.get("published_at", "")[:10])} · {link(row.get("url", ""))}</div>'
                f'<h3>{h(title)}</h3>'
                f'<p><b>Почему не подтверждено:</b> {h(reason)}</p>'
                + (f'<p><b>Срок или дедлайн в тексте:</b> {h(date_hint)}</p>' if date_hint else "")
                + (f'<p><b>Автоматически извлечённая награда, требует проверки:</b> {h(reward)}</p>' if reward else "")
                + f'<details><summary>Исходный текст публикации</summary><p>{h(source_text)}</p></details>'
                '</article>'
            )
        return "\n".join(parts)

    no_web = [s for s in sources if s.get("type") == "web" and s.get("status") == "ok" and int(s.get("item_count") or 0) == 0]
    bad = [s for s in sources if s.get("status") in ("error", "limited", "unsupported")]
    web = [s for s in sources if s.get("type") == "web"]
    counts = Counter(r.get("reason", "") for r in current)
    breakdown = ", ".join(f"{h(REASON_LABELS.get(k, k))}: {v}" for k, v in counts.most_common())
    web_list = "".join(
        f'<li>{h(s.get("bank", ""))} · {h(s.get("source_id", ""))} '
        f'({h(s.get("status", ""))}, {h(s.get("item_count", ""))} материалов)</li>'
        for s in no_web + bad
    )
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Проверка мониторинга Daily Banking {start} - {end}</title>
<style>
body{{font:16px/1.55 Arial,sans-serif;color:#202b39;background:#f4f6f9;max-width:1080px;margin:auto;padding:28px}}
h1{{font-size:28px}}h2{{font-size:22px;margin-top:36px}}h3{{font-size:17px;margin:8px 0}}
.meta{{color:#475569;font-size:14px}}.item{{background:white;padding:18px 22px;border:1px solid #e1e6ed;border-radius:12px;margin:12px 0}}
.item p{{margin:8px 0}}a{{color:#1451a4}}details{{margin-top:10px}}details p{{white-space:pre-wrap}}
.stats{{display:flex;gap:12px;flex-wrap:wrap}}.stat{{background:white;padding:16px 20px;border-radius:10px;min-width:160px}}
.stat b{{display:block;font-size:28px}}.note{{border-left:3px solid #64748b;padding-left:14px;color:#475569}}
</style></head><body>
<h1>Мониторинг Daily Banking: очередь проверки</h1>
<p>{start:%d.%m.%Y} - {end:%d.%m.%Y}</p>
<p class="note"><b>Это не подтверждённые акции.</b> Это исходные публикации, которые алгоритм не смог автоматически подтвердить. Даты, награды и условия нужно сверять с первоисточником. Наличие публикации не означает, что акция началась в отчётную неделю.</p>
<div class="stats">
<div class="stat"><b>{len(review)}</b>всего на проверку</div>
<div class="stat"><b>{len(current)}</b>опубликованы в отчётную неделю</div>
<div class="stat"><b>{len(historical)}</b>вне отчётной недели / дата не определена</div>
<div class="stat"><b>{len(no_web)} / {len(web)}</b>веб-источников: статус OK, но 0 материалов</div>
</div>
<h2>1. Публикации отчётной недели ({len(current)})</h2>
<p>Требуют проверки релевантности, периода, вознаграждения и условий. <b>Причины:</b> {breakdown}.</p>
{cards(current)}
<h2>2. Вне отчётной недели ({len(historical)})</h2>
<p class="note">Отдельный раздел для восстановительного поиска. Не считать новыми акциями без проверки даты старта и изменения условий.</p>
{cards(historical)}
<h2>3. Проблемы охвата источников</h2>
<p>Статус «OK» означает, что страница открылась, а не что все акции банка собраны. Нулевой результат веб-источника нельзя интерпретировать как отсутствие акций.</p>
<ul>{web_list}</ul>
</body></html>"""


def write_review_report(artifact_dir: Path, start: date, end: date) -> Path:
    period = f"{start:%Y-%m-%d}_{end:%Y-%m-%d}"
    review = load_csv(artifact_dir / f"review_queue_{period}.csv")
    sources = load_csv(artifact_dir / f"audit_sources_{period}.csv")
    output = artifact_dir / f"review_report_{period}.html"
    output.write_text(report_html(review, sources, start, end), encoding="utf-8")
    return output
