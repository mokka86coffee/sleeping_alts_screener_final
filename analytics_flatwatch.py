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
    picked: list[dict] = []
    flat_price = 0   # диагностика: сколько из выборки лежит по цене

    for c in candidates:
        sym = getattr(c, "symbol", "").upper()
        if not sym:
            continue
        raw = getattr(c, "raw", {}) or {}

        # v4 ([stated] «подходит любая структура»): фильтров по цене
        # НЕТ — боту уходит вся выборка, включая фазу go. Флэт/ход —
        # только метка; момент входа выбирает сам бот (белый пузырь
        # у дна суточного коридора).
        try:
            ch = abs(float(raw.get("ch_24h") or 0))
        except (TypeError, ValueError):
            ch = 0.0
        is_flat = ch <= FLAT_PCT
        if is_flat:
            flat_price += 1

        # Донный признак — МЕТКА качества, не отсев (v3): пользователь
        # изначально просил «всё, что идёт во флэте», а живой прогон
        # 24.08 показал воронку 4 лежащих / 0 с признаком — жёсткое
        # условие оставляло бота без скринерских монет. Момент входа
        # фильтрует сам бот (белый пузырь у дна), фаза go уже
        # исключена выше — крышу у хаёв не покупаем.
        try:
            ab = absorption_for(sym)
            sq = squeeze_for(sym)
        except Exception:
            ab, sq = {}, {}
        absorbed = bool(ab.get("absorbed"))
        charged = bool(sq.get("charged"))

        corr = _corridor(c)
        try:
            price = float(raw.get("price"))
        except (TypeError, ValueError):
            continue

        entry = {
            "sym": sym,
            "price": price,
            "atrPct": float(raw.get("atr_pct") or 0),
            "reason": ("поглощение" if absorbed
                       else "заряд" if charged
                       else "флэт" if is_flat else "ход"),
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
    with_bottom = sum(1 for c in picked
                      if c["reason"] in ("поглощение", "заряд"))
    doc["_meta"]["withBottom"] = with_bottom
    if persist:
        WATCH_PATH.write_text(
            json.dumps(doc, ensure_ascii=False, indent=1),
            encoding="utf-8")
    return (f"{WATCH_PATH.name}: {len(picked)} монет — вся выборка "
            f"(во флэте {flat_price}, с донным признаком {with_bottom})")


FLOW_WATCH_PATH = WATCH_PATH.with_name("flow_watch.json")


def collect_flow_watch(candidates: list, persist: bool = False) -> str:
    """Мост v2 «FLOW-полигон» ([stated] 24.08: «прогонять наш список
    flow и понимать, как лучше выстраивать ТВХ»). Боту уходят ТОЛЬКО
    монеты списка FLOW — те же, что на ленте стратегии, — вместе с
    коротким ключом подкейса (hidden/spring/churn/fuel/dormant/
    taker/leverage). Бот гоняет по ним три этапа (тех → ход →
    закрытие) на 5m и журналирует события ведения; разрез статистики
    по кейсам потом скажет, на каких фигурах какая механика работает.
    Старый collect_flat_watch остаётся соседом, но боевая сборка
    зовёт этот."""
    from analytics_flow import case_key, case_of

    picked: list[dict] = []
    for c in candidates:
        sym = getattr(c, "symbol", "").upper()
        if not sym or not getattr(c, "flow", None):
            continue
        raw = getattr(c, "raw", {}) or {}
        try:
            price = float(raw.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        corr = _corridor(c)
        if corr is None:
            try:
                atr = float(raw.get("atr_pct") or 0)
            except (TypeError, ValueError):
                atr = 0.0
            span = price * max(atr, 1.0) / 100.0
            corr = (price - span, price + span)
        low, high = corr
        picked.append({
            "sym": sym,
            "case": case_key(case_of(c)) or "flow",
            "price": price,
            "low": low,
            "high": high,
        })

    doc = {"coins": picked,
           "_meta": {"count": len(picked),
                     "src": "flow",
                     "at": datetime.now(timezone.utc)
                     .isoformat(timespec="seconds")}}
    if persist:
        FLOW_WATCH_PATH.write_text(
            json.dumps(doc, ensure_ascii=False, indent=1),
            encoding="utf-8")
    cases: dict[str, int] = {}
    for p in picked:
        cases[p["case"]] = cases.get(p["case"], 0) + 1
    по_кейсам = ", ".join(f"{k} {v}" for k, v in sorted(cases.items()))
    return (f"{FLOW_WATCH_PATH.name}: {len(picked)} монет FLOW"
            + (f" ({по_кейсам})" if по_кейсам else ""))
