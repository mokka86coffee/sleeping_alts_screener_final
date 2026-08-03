"""Сырой срез по ОДНОЙ монете на момент запуска.

Не отбирает, не фильтрует, не решает. Задача одна: выложить в JSON
всё, что система видит по монете прямо сейчас, чтобы числа можно было
сверить с графиком глазами.

Отличие от flow_probe.py принципиальное. Probe гонит рынок и пишет
итоги — монета туда попадает, только если прошла ликвидность, состав
выборки и не выпала по вето. Здесь символ задан руками, и никаких
условий на него нет: даже если ядро молчит, а все шесть подкейсов
отказали, выгрузка всё равно состоится, и в ней будет написано, ПОЧЕМУ
они отказали.

Запуск:
    python flow_dump.py BICOUSDT              всё, сеть включена
    python flow_dump.py TAKEUSDT --no-net     без funding и OI
    python flow_dump.py BICOUSDT --bars       плюс бары всех масштабов
    python flow_dump.py BICOUSDT --tail 120   ограничить длину рядов
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import datetime, timezone

from core.binance import (
    K_CLOSE, K_CLOSE_TIME, K_HIGH, K_LOW, K_OPEN, K_OPEN_TIME,
    K_QUOTE_VOLUME, K_TAKER_BUY_QUOTE, K_TRADES, K_VOLUME,
    get_funding_history, get_funding_rate, get_futures_tickers,
    get_oi_history, get_open_interest, get_spot_ticker,
    klines_1d, klines_1h, klines_1w, klines_4h,
)
from detectors.flow_core import build_context
from detectors.flow_signal import veto_bullish, veto_common

import detectors.flow_churn as flow_churn
import detectors.flow_fuel as flow_fuel
import detectors.flow_hidden as flow_hidden
import detectors.flow_leverage as flow_leverage
import detectors.flow_spring as flow_spring
import detectors.flow_taker as flow_taker

# Порядок зрелости, тот же что в диспетчере.
RUNNERS = (
    flow_hidden, flow_spring, flow_churn,
    flow_taker, flow_fuel, flow_leverage,
)

# Кто из подкейсов не требует зон. Нужно, чтобы причина отказа
# считалась тем же вето, которое модуль применяет к себе, а не
# усреднённым: иначе в выгрузке будет написано «нет живых зон» у
# hidden, который зон и не спрашивает.
NO_ZONES = {"flow_hidden", "flow_taker", "flow_leverage"}

# Кто играет от разворота и проверяет обвал дельты дополнительно.
BULLISH = {"flow_hidden", "flow_spring", "flow_churn",
           "flow_taker", "flow_leverage"}


def _fill(k: list) -> float:
    """Доля набранного времени свечи.

    Дублируется здесь сознательно: скрипт обязан работать, даже если
    ядро сломано правкой. Диагностический инструмент, зависящий от
    того, что он диагностирует, бесполезен ровно тогда, когда нужен.
    """
    now_ms = time.time() * 1000.0
    try:
        t_open = float(k[K_OPEN_TIME])
        t_close = float(k[K_CLOSE_TIME])
    except (TypeError, ValueError, IndexError):
        return 1.0
    span = t_close - t_open
    if span <= 0 or now_ms >= t_close:
        return 1.0
    return max(0.0, min(1.0, (now_ms - t_open) / span))


def _iso(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000.0, timezone.utc).isoformat(
        timespec="seconds"
    )


def dump_klines(raw: list[list], tail: int = 0) -> list[dict]:
    """Свечи с разложенным потоком и меткой заполнения.

    Именованные поля, а не массивы из двенадцати позиций: срез читают
    глазами, и K_TAKER_BUY_QUOTE на десятом месте глазами не читается.
    """
    src = raw[-tail:] if tail else raw
    out = []
    for k in src:
        try:
            q = float(k[K_QUOTE_VOLUME])
            b = float(k[K_TAKER_BUY_QUOTE])
            out.append({
                "open_time": _iso(float(k[K_OPEN_TIME])),
                "open": float(k[K_OPEN]),
                "high": float(k[K_HIGH]),
                "low": float(k[K_LOW]),
                "close": float(k[K_CLOSE]),
                "volume_base": float(k[K_VOLUME]),
                "quote": q,
                "taker_buy_quote": b,
                "taker_sell_quote": max(0.0, q - b),
                "delta": b - max(0.0, q - b),
                "buy_share": round(b / q, 4) if q > 0 else None,
                "trades": int(float(k[K_TRADES])),
                "fill": round(_fill(k), 4),
            })
        except (TypeError, ValueError, IndexError):
            continue
    return out


def dump_bars(bars) -> list[dict]:
    """Бары агрегата ядра. Показывают, что получилось из дневок."""
    return [
        {
            "idx": b.idx,
            "open": b.open, "high": b.high, "low": b.low, "close": b.close,
            "quote": b.quote,
            "buy_quote": b.buy_quote,
            "sell_quote": b.sell_quote,
            "delta": b.delta,
            "buy_share": round(b.buy_share, 4),
            "fill": round(b.fill, 4),
        }
        for b in bars
    ]


def dump_events(events) -> list[dict]:
    """События всех масштабов, полным списком и без среза."""
    return sorted(
        (e.to_dict() for e in events),
        key=lambda d: (d.get("age_days", d.get("age", 0)), -d["sigma"]),
    )


def probe_subcases(ctx) -> dict:
    """Гоняет все шесть подкейсов и записывает ИСХОД каждого.

    Три различимых состояния, и различать их обязательно:
      · signal  — фигура собралась, есть скор и множители;
      · veto    — отказало общее вето, причина известна текстом;
      · silent  — вето прошло, фигура не сложилась внутри модуля;
      · error   — исключение, то есть дефект кода.

    Молчащий подкейс и упавший подкейс выглядят одинаково в любом
    сводном отчёте. Здесь они разведены, потому что первое — свойство
    рынка, а второе — опечатка.
    """
    out = {}
    for module in RUNNERS:
        mod_name = getattr(
            module, "name", module.__name__.rsplit(".", 1)[-1]
        )
        entry: dict = {}

        # Причина отказа фиксируется ДО вызова detect: сам модуль
        # вернёт None и не скажет, на чём остановился.
        req_zones = mod_name not in NO_ZONES
        checker = veto_bullish if mod_name in BULLISH else veto_common
        reason = checker(ctx, require_zones=req_zones)
        entry["veto"] = reason

        try:
            sig = module.detect(ctx)
        except Exception as exc:
            entry["state"] = "error"
            entry["error"] = f"{type(exc).__name__}: {exc}"
            entry["traceback"] = traceback.format_exc()
            out[mod_name] = entry
            continue

        if sig is None:
            entry["state"] = "veto" if reason else "silent"
        else:
            entry["state"] = "signal"
            entry["signal"] = sig.to_dict()
        out[mod_name] = entry
    return out


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("Укажи символ: python flow_dump.py BICOUSDT")
        raise SystemExit(1)

    symbol = args[0].upper()
    if not symbol.endswith("USDT"):
        symbol += "USDT"

    allow_network = "--no-net" not in sys.argv
    want_bars = "--bars" in sys.argv

    tail = 0
    if "--tail" in sys.argv:
        try:
            tail = int(sys.argv[sys.argv.index("--tail") + 1])
        except (IndexError, ValueError):
            tail = 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"flow_dump_{symbol}_{stamp}.json"

    print(f"{symbol}: снимаю срез, сеть {'включена' if allow_network else 'выключена'}")
    started = time.time()

    data: dict = {
        "meta": {
            "symbol": symbol,
            "launched_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
            "launched_at_local": datetime.now().isoformat(timespec="seconds"),
            "allow_network": allow_network,
            "tail": tail or None,
            "note": (
                "Срез на момент запуска. Правый край всех рядов — "
                "незакрытый бар, смотри поле fill."
            ),
        }
    }

    # ── Тикер 24h ────────────────────────────────────────────
    # Отдельным запросом монету не взять: эндпоинт отдаёт весь рынок.
    # Оборот нужен, потому что ядро принимает его параметром.
    quote_volume_24h = 0.0
    try:
        for t in get_futures_tickers():
            if t.get("symbol") == symbol:
                data["ticker_24h"] = t
                quote_volume_24h = float(t.get("quoteVolume", 0) or 0)
                break
        else:
            data["ticker_24h"] = None
            print("  тикера нет в списке фьючерсов — монета может быть делистнута")
    except Exception as exc:
        data["ticker_24h"] = {"error": f"{type(exc).__name__}: {exc}"}

    # ── Свечи по всем каноническим масштабам ─────────────────
    data["klines"] = {}
    for label, loader in (
        ("1d", klines_1d), ("4h", klines_4h),
        ("1h", klines_1h), ("1w", klines_1w),
    ):
        try:
            raw = loader(symbol)
            data["klines"][label] = {
                "count": len(raw),
                "bars": dump_klines(raw, tail),
            }
        except Exception as exc:
            data["klines"][label] = {"error": f"{type(exc).__name__}: {exc}"}

    # ── Деривативы ───────────────────────────────────────────
    if allow_network:
        deriv: dict = {}
        try:
            deriv["funding_rate_last"] = get_funding_rate(symbol)
        except Exception as exc:
            deriv["funding_rate_last"] = f"error: {exc}"
        try:
            hist = get_funding_history(symbol, limit=100)
            deriv["funding_history"] = hist
            deriv["funding_history_count"] = len(hist)
        except Exception as exc:
            deriv["funding_history"] = f"error: {exc}"
        try:
            deriv["open_interest_base"] = get_open_interest(symbol)
        except Exception as exc:
            deriv["open_interest_base"] = f"error: {exc}"
        try:
            oih = get_oi_history(symbol, period="1d", limit=30)
            deriv["oi_history"] = oih
            deriv["oi_history_count"] = len(oih)
        except Exception as exc:
            deriv["oi_history"] = f"error: {exc}"
        data["derivatives"] = deriv

        try:
            data["spot_ticker"] = get_spot_ticker(symbol)
        except Exception as exc:
            data["spot_ticker"] = {"error": str(exc)}
    else:
        data["derivatives"] = None
        data["spot_ticker"] = None

    # ── Контекст ядра ────────────────────────────────────────
    # Вето здесь нет и быть не может: ядро считает, а не отбирает.
    # Если valid == false, значит не хватило истории — единственная
    # причина, по которой контекст не собирается.
    try:
        ctx = build_context(symbol, quote_volume_24h)
        data["flow_context"] = ctx.to_dict()
        data["flow_context"]["valid"] = ctx.valid
        data["flow_context"]["symbol"] = ctx.symbol
        data["flow_context"]["horizon_scale"] = ctx.horizon_scale
        data["flow_context"]["distrust_zones"] = ctx.distrust_zones

        # События полным списком: to_dict() ядра отдаёт только счётчик.
        data["events"] = dump_events(ctx.events)

        if want_bars:
            data["aggregated_bars"] = {
                str(scale): dump_bars(bars[-tail:] if tail else bars)
                for scale, bars in sorted(ctx.bars.items())
            }

        if ctx.valid:
            data["subcases"] = probe_subcases(ctx)
        else:
            data["subcases"] = {
                "_note": "контекст невалиден, подкейсы не запускались"
            }
    except Exception as exc:
        data["flow_context"] = {"error": f"{type(exc).__name__}: {exc}"}
        data["traceback"] = traceback.format_exc()
        traceback.print_exc()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    # ── Короткая сводка в консоль ────────────────────────────
    ctxd = data.get("flow_context") or {}
    vx = ctxd.get("vortex") or {}
    print(f"\n{'=' * 52}")
    print(f"{symbol}  за {time.time() - started:.1f}с")
    print(f"  цена        {ctxd.get('price')}")
    print(f"  масштабы    {ctxd.get('scales')}")
    print(f"  заполнение  {ctxd.get('fills')}")
    print(f"  событий     {ctxd.get('events_total')}")
    print(f"  зон         {len(ctxd.get('zones') or [])} "
          f"(подтверждённых {ctxd.get('zones_confirmed')})")
    print(f"  вортекс     {vx}")
    print(f"  поток       {ctxd.get('flow')}")
    print(f"  падение     {ctxd.get('drop')}")

    subs = data.get("subcases") or {}
    print("\n  подкейсы:")
    for name, entry in subs.items():
        if name.startswith("_"):
            continue
        state = entry.get("state")
        if state == "signal":
            s = entry["signal"]
            print(f"    {name:16s} {s['score']:5.1f} "
                  f"(база {s['base_score']:5.1f}, срез {s['cut']}) "
                  f"{'; '.join(s['reasons'][:2])}")
        elif state == "veto":
            print(f"    {name:16s} вето: {entry.get('veto')}")
        elif state == "error":
            print(f"    {name:16s} ОШИБКА: {entry.get('error')}")
        else:
            print(f"    {name:16s} молчит (вето прошло, фигура не собралась)")

    print(f"\nФайл: {path}")


if __name__ == "__main__":
    main()
