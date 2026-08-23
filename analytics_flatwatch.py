"""Мост к пузырь-боту: список монет во флэте у дна.

Единственная связь скринера с внешним пузырь-ботом (bubble_bot.py).
Скринер на часовых данных умеет то, ради чего построен, — отличать
дно от движения; здесь этот вывод выписывается в файл, из которого
бот берёт СВОИ монеты и границы коридора. Связь односторонняя: бот
только читает, обратно в скринер не пишет ничего.

Что считается «флэтом у дна» здесь — это переиспользование уже
готовых сигналов звезды, не новая стратегия:
  • узкий коридор — суточный ход в пределах FLAT_PCT (та же планка
    STANCE_FLAT_PCT, которой analytics_intraday метит стойку «flat»);
  • не в разгоне — звезда не в фазе go и не улетела (aliveGap мал);
  • подтверждение дна — любой из наших донных признаков: absorption
    (Т-3, поглощение продаж у дна) или заряд на сжим (С-2).
Границы коридора отдаются боту как есть (low/high за окно), чтобы
он не считал их сам на быстрых данных, где флэт хуже виден.

Файл пишет боевая сборка прогона (persist=True), как unlocks_seen:
у файла одна версия правды, дубль-сборка для file:// его не трогает.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
    from core_http import log
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
    def log(msg: str) -> None:
        print(msg)

WATCH_PATH = BASE_DIR / "output" / "flat_watch.json"

FLAT_PCT = 3.0          # суточный ход не больше — «лежит ровно»
MAX_ATR = 4.0           # и внутренняя дёрганность невелика (ATR%)


def _corridor(c) -> tuple[float, float] | None:
    """Границы коридора из суточных крайних, если они есть в raw."""
    raw = getattr(c, "raw", {}) or {}
    hi, lo = raw.get("high_24h"), raw.get("low_24h")
    try:
        hi, lo = float(hi), float(lo)
    except (TypeError, ValueError):
        return None
    if hi > lo > 0:
        return lo, hi
    return None


def collect_flat_watch(candidates: list, stars: list,
                       persist: bool = False) -> str:
    """Пишет output/flat_watch.json: монеты во флэте у дна для бота.

    candidates — для цены/ATR/коридора (raw), stars — для наших
    донных вердиктов (absorb/squeeze/phase), собранных build_stars.
    """
    by_sym = {getattr(c, "symbol", "").upper(): c for c in candidates}
    picked: list[dict] = []

    for s in stars:
        sym = (s.get("t") or "") + "USDT"
        c = by_sym.get(sym)
        if c is None:
            continue
        raw = getattr(c, "raw", {}) or {}

        # узкий суточный коридор
        try:
            ch = abs(float(raw.get("ch_24h") or 0))
            atr = float(raw.get("atr_pct") or 0)
        except (TypeError, ValueError):
            continue
        if ch > FLAT_PCT or atr > MAX_ATR:
            continue

        # не в разгоне: звезда не в фазе go
        if (s.get("phase") or {}).get("k") == "go":
            continue

        # подтверждение дна — любой донный признак
        bottom = bool(s.get("absorb")) or \
            bool((s.get("squeeze") or {}).get("charged"))
        if not bottom:
            continue

        corr = _corridor(c)
        try:
            price = float(raw.get("price"))
        except (TypeError, ValueError):
            continue

        entry = {
            "sym": sym,
            "price": price,
            "atrPct": atr,
            "reason": ("поглощение" if s.get("absorb") else "заряд"),
        }
        if corr:
            entry["low"], entry["high"] = corr
        else:
            # коридор из ATR, если крайних нет: цена ± ATR%
            band = price * atr / 100.0
            entry["low"], entry["high"] = price - band, price + band
        picked.append(entry)

    doc = {
        "_meta": {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "count": len(picked),
            "flatPct": FLAT_PCT,
            "note": ("Монеты во флэте у дна для bubble_bot. Пишет "
                     "скринер, читает бот. Границы low/high — коридор "
                     "флэта: выход за них у бота = стоп."),
        },
        "coins": picked,
    }
    if persist:
        WATCH_PATH.parent.mkdir(parents=True, exist_ok=True)
        WATCH_PATH.write_text(
            json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return f"{WATCH_PATH.name}: {len(picked)} монет во флэте"
