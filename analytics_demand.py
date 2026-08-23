"""Структурный спрос (Р-31). Обратная сторона разлоков.

У нас был перекос: файл про ПРЕДЛОЖЕНИЕ (unlocks.json — кто и когда
выбросит токены на рынок) и ничего про СПРОС. А выкуп с рынка устроен
ровно так же, только с обратным знаком: известен заранее, повторяется
по расписанию, измеряется в долларах. Не отмечать его — значит видеть
у монеты только то, что давит.

Что сюда попадает:
    buyback   — протокол покупает свой токен с рынка на выручку;
    burn      — сжигает купленное или часть эмиссии;
    feeswitch — комиссия сети идёт держателям или в выкуп;
    lockup    — крупная доля заперта стейкингом с длинным сроком.

ГЛАВНОЕ ПРАВИЛО ФАЙЛА: значок без размера — не сигнал, а украшение.
«Есть выкуп» ничего не говорит: PROM тоже «протокол с выручкой», а
выручки там $681 за квартал при обороте $71 млн в сутки. Поэтому у
записи есть размер, и слой считает годовой выкуп к капитализации —
единственное число, по которому две монеты можно сравнить.

СТАТУС ОБЯЗАТЕЛЕН И РАЗЛИЧАЕТСЯ:
    proposed — предложено, обсуждается;
    voting   — вынесено на голосование;
    active   — работает, деньги идут.
Предложение не равно работающему выкупу, и путать их — тот же
самообман, что считать разлок состоявшимся до даты.

Файл ручной, как unlocks.json и events.json: такие вещи приходят из
блогов проектов и голосований, а не из свечей.

Формат demand.json:

    {
      "TREEUSDT": {
        "kind": "buyback",
        "status": "proposed",
        "share_of_revenue": 50,
        "cadence": "weekly",
        "note": "TIP-4: 50% выручки MEY с tETH на еженедельный выкуп",
        "source": "…", "checked_at": "2026-08-23"
      }
    }
"""

from __future__ import annotations

import json
from pathlib import Path

from core_config import BASE_DIR

# КОРЕНЬ, не output/ — ручной файл, та же ошибка пути, что у
# календаря (см. заметку в analytics_calendar, найдено 23.08). Из-за
# неё строка «спрос» на TREE и HYPE не показывалась вовсе.
DEMAND_PATH = BASE_DIR / "demand.json"

KINDS = ("buyback", "burn", "feeswitch", "lockup")
STATUSES = ("proposed", "voting", "active")

KIND_RU = {"buyback": "выкуп", "burn": "сжигание",
           "feeswitch": "комиссия в токен", "lockup": "заперто стейкингом"}
STATUS_RU = {"proposed": "предложено", "voting": "голосование",
             "active": "работает"}

# Годовой выкуп к капитализации. Ниже одного процента — фон: столько
# рынок проторговывает за день, и разговоры о «структурном спросе»
# там пустые. Выше пяти — величина, которую уже видно в стакане.
DEMAND_WEAK_PCT = 1.0
DEMAND_STRONG_PCT = 5.0


def load_demand(path: Path = DEMAND_PATH) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def for_symbol(symbol: str, mcap_usd: float | None = None,
               revenue_30d_usd: float | None = None,
               path: Path = DEMAND_PATH) -> dict:
    """Отметка структурного спроса по монете.

    mcap_usd и revenue_30d_usd — снаружи: первый из фундаментальных
    полей, второй из замера выручки (fundamental_revenue.py). Без них
    отдаётся сама запись без размера — и это честно: «выкуп заявлен,
    величина не посчитана» отличается от «выкуп на 8% капы в год».

    Пустой словарь — монеты в файле нет. Это НЕ «спроса нет»: это
    «не заполняли», и показ обязан различать.
    """
    rec = (load_demand(path) or {}).get(symbol) or {}
    if not rec:
        return {}

    kind = str(rec.get("kind") or "")
    status = str(rec.get("status") or "")
    out = {
        "kind": kind, "status": status,
        "label": KIND_RU.get(kind, kind or "спрос"),
        "statusRu": STATUS_RU.get(status, status),
        "note": str(rec.get("note") or ""),
    }
    if rec.get("source"):
        out["source"] = rec["source"]

    # ── размер: годовой выкуп к капитализации ──
    share = rec.get("share_of_revenue")
    try:
        share_f = float(share) / 100.0 if share is not None else None
    except (TypeError, ValueError):
        share_f = None
    if share_f and revenue_30d_usd and mcap_usd:
        try:
            yearly = float(revenue_30d_usd) * 12.0 * share_f
            pct = yearly / float(mcap_usd) * 100.0
        except (TypeError, ValueError, ZeroDivisionError):
            pct = None
        if pct is not None:
            out["yearPct"] = round(pct, 2)
            out["yearUsd"] = round(yearly)
            out["weak"] = pct < DEMAND_WEAK_PCT
            out["strong"] = pct >= DEMAND_STRONG_PCT
    return out


def phrase(d: dict) -> str:
    """Строка для показа. Пусто — показывать нечего.

    Размер идёт ПЕРЕД словами: «выкуп 8% капы в год» читается, а
    «активный выкуп» — нет.
    """
    if not d:
        return ""
    parts = []
    if d.get("yearPct") is not None:
        parts.append(f"{d['label']} {d['yearPct']:.1f}% капы в год")
    else:
        parts.append(f"{d['label']}, размер не посчитан")
    if d.get("statusRu") and d.get("status") != "active":
        parts.append(d["statusRu"])
    return " · ".join(parts)
