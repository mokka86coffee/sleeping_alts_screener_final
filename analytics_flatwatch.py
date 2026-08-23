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
    from analytics_squeeze import absorption_for, squeeze_for
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

    Отбор идёт по ВСЕЙ выборке кандидатов, не по звёздам: скор звёзд
    любит движение, а дно-флэт по построению живёт вне подиума —
    поглощение и заряд находились по всем 281, и мост ищет там же.
    stars нужны только чтобы исключить монеты в фазе go (разгон).
    Донные вердикты — те же детекторы analytics_squeeze, что и у
    звёзд (absorption_for / squeeze_for, кеш пульса по mtime).
    """
    going = {(s.get("t") or "") + "USDT" for s in stars
             if (s.get("phase") or {}).get("k") == "go"}
    picked: list[dict] = []
    flat_price = 0   # диагностика воронки: сколько лежит по цене

    for c in candidates:
        sym = getattr(c, "symbol", "").upper()
        if not sym or sym in going:
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
        flat_price += 1

        # подтверждение дна — любой донный признак по пульсу
        try:
            ab = absorption_for(sym)
            sq = squeeze_for(sym)
        except Exception:
            ab, sq = {}, {}
        absorbed = bool(ab.get("absorbed"))
        if not (absorbed or sq.get("charged")):
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
            "reason": ("поглощение" if absorbed else "заряд"),
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
            "flatByPrice": flat_price,
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
    return (f"{WATCH_PATH.name}: {len(picked)} монет "
            f"(лежат по цене {flat_price}, с донным признаком "
            f"{len(picked)})")
