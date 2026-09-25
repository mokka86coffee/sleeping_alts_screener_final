"""Срез по монетам с Binance — замена coinglass_fetch (24.09, владелец: «нет денег больше на coinglass»).

ЧТО ПИШЕТ. output/binance_fetch.json и ТОТ ЖЕ срез в output/coinglass_fetch.json — в прежнем виде до поля,
поэтому архив получасовок, стыки, карточка, книги и интро ничего не замечают. Файлы coinglass_*.py не трогаются.

ОТКУДА ЧИСЛА (всё бесплатно, через core_binance с общим лимитером):
  · fut   — получасовые свечи фьючерса: покупки рынком (taker buy quote) и продажи (оборот минус покупки),
            тейкер бара, накопленная дельта. У Coinglass это была сумма Binance+OKX+Bybit, здесь — Binance.
  · spot  — то же по споту, если пара на споте есть; нет пары — None, как и раньше.
  · oiUsd, oiChgPct — история открытого интереса по получасам (openInterestHist, sumOpenInterestValue).
  · funding — последняя ставка premiumIndex, в ПРОЦЕНТАХ, как отдавал Coinglass (доля × 100).
  · liq   — None: ликвидаций по сторонам Binance историей не отдаёт. В missing не пишется — это не сбой
            сбора, а отсутствие источника; признак в срезе: "liq_source": null.

ЗАПУСК
    python3 binance_fetch.py                 # показать по журналу
    python3 binance_fetch.py --write         # записать срез
    python3 binance_fetch.py ENA ONE         # только названные
В прогоне зовётся из run.py вместо coinglass_fetch.collect (та же сигнатура).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent

from core_binance import closed_only, get_funding_rate, get_klines, get_oi_history, get_spot_klines

OUT_PATH = BASE_DIR / "output" / "binance_fetch.json"
COMPAT_PATH = BASE_DIR / "output" / "coinglass_fetch.json"   # его читают все экраны — вид среза прежний
INTERVAL = "30m"
WINDOW = 48                                                   # закрытых баров: сутки
try:
    from core_config import BINANCE_FETCH_THREADS, BINANCE_FETCH_MAX_COINS
except ImportError:
    BINANCE_FETCH_THREADS = 6                                 # как у анализа в прогоне
    BINANCE_FETCH_MAX_COINS = 400


_LIQ_CACHE: dict = {}


def _liq_sides() -> dict | None:
    """output/liq_sides.json от liq_stream.py, если сводка свежее 2 часов; читается один раз за прогон"""
    if "v" not in _LIQ_CACHE:
        _LIQ_CACHE["v"] = None
        try:
            from datetime import datetime, timezone
            d = json.loads((BASE_DIR / "output" / "liq_sides.json").read_text(encoding="utf-8"))
            at = datetime.fromisoformat(str(d.get("at")).replace("Z", "+00:00")).timestamp()
            if datetime.now(timezone.utc).timestamp() - at <= 7200 and d.get("coins"):
                _LIQ_CACHE["v"] = d
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    return _LIQ_CACHE["v"]


def _base_coin(sym: str) -> str:
    s = sym.upper()
    for tail in ("USDT", "USDC", "BUSD", "USD"):
        if s.endswith(tail) and len(s) > len(tail):
            return s[: -len(tail)]
    return s


def _journal_coins() -> tuple[list[str], str | None]:
    """Монеты журнала + BTC — тот же список, что брал Coinglass."""
    note = None
    try:
        from analytics_leaders import tracked_symbols
        symbols = sorted(tracked_symbols())
    except Exception as e:  # noqa: BLE001
        symbols = []
        note = f"журнал не прочитан ({type(e).__name__}: {e}) — в срезе только BTC; запускать из корня проекта"
    coins: list[str] = []
    for s in ["BTC"] + [_base_coin(x) for x in symbols]:
        if s and s not in coins:
            coins.append(s)
    if len(coins) > BINANCE_FETCH_MAX_COINS:
        note = ((note + " · ") if note else "") + f"журнал {len(coins)} монет, взято {BINANCE_FETCH_MAX_COINS}"
    return coins[:BINANCE_FETCH_MAX_COINS], note


def _flow(klines: list[list]) -> dict | None:
    """Свечи → тот же разбор, что parse_cvd у Coinglass: свод + ряд по барам {t, tk, b, s, cvd}."""
    rows = closed_only(klines or [])[-WINDOW:]
    if not rows:
        return None
    buy = sell = 0.0
    cvd = 0.0
    series: list[dict] = []
    for k in rows:
        try:
            q = float(k[7])                                   # оборот бара в долларах
            b = float(k[10])                                  # из него покупки рынком
        except (IndexError, TypeError, ValueError):
            continue
        s = max(0.0, q - b)
        buy += b
        sell += s
        cvd += b - s
        series.append({"t": int(k[0]), "tk": round(b / s, 3) if s else None,
                       "b": round(b, 2), "s": round(s, 2), "cvd": round(cvd, 2)})
    if not series:
        return None
    first = series[0]["b"] - series[0]["s"]
    return {"buyUsd": round(buy, 2), "sellUsd": round(sell, 2), "taker": round(buy / sell, 3) if sell > 0 else None,
            "bars": len(series), "series": series, "cvd": round(cvd, 2), "cvdChg": round(cvd - first, 2)}


def snap_coin(coin: str, errors: dict) -> tuple[dict, int]:
    pair = coin + "USDT"
    out: dict = {}
    req = 0
    try:
        out["fut"] = _flow(get_klines(pair, INTERVAL, WINDOW + 1)); req += 1
    except Exception as e:  # noqa: BLE001
        out["fut"] = None; errors[f"{coin} fut"] = f"{type(e).__name__}: {e}"
    try:
        out["spot"] = _flow(get_spot_klines(pair, INTERVAL, WINDOW + 1)); req += 1
    except Exception as e:  # noqa: BLE001
        out["spot"] = None; errors[f"{coin} spot"] = f"{type(e).__name__}: {e}"
    try:
        oh = get_oi_history(pair, INTERVAL, WINDOW + 1); req += 1
        vals = [float(r.get("sumOpenInterestValue")) for r in (oh or []) if r.get("sumOpenInterestValue") is not None]
        out["oiUsd"] = round(vals[-1], 2) if vals else None
        out["oiChgPct"] = round((vals[-1] / vals[0] - 1) * 100, 2) if len(vals) > 1 and vals[0] else None
    except Exception as e:  # noqa: BLE001
        out["oiUsd"] = out["oiChgPct"] = None; errors[f"{coin} oi"] = f"{type(e).__name__}: {e}"
    try:
        fr = get_funding_rate(pair); req += 1
        out["funding"] = round(fr * 100, 6) if fr is not None else None     # доля → проценты, как у Coinglass
    except Exception as e:  # noqa: BLE001
        out["funding"] = None; errors[f"{coin} funding"] = f"{type(e).__name__}: {e}"
    # ЛИКВИДАЦИИ ПО СТОРОНАМ — ИЗ ЖИВОГО ПОТОКА (26.09, liq_stream.py → output/liq_sides.json): сводка не старше 2 ч,
    # иначе как раньше — нет источника
    _ls = _liq_sides()
    _lc = (_ls.get("coins") or {}).get(pair) if _ls else None
    out["liq"] = {"long24h": _lc["long24h"], "short24h": _lc["short24h"], "long1h": _lc.get("long1h"), "short1h": _lc.get("short1h")} if _lc else None
    miss = [k for k in ("fut", "spot") if not out.get(k)]
    if out.get("oiUsd") is None:
        miss.append("oi")
    if out.get("funding") is None:
        miss.append("funding")
    if miss:
        out["missing"] = miss
    return out, req


def collect(symbols: list[str] | None = None, *, key: str | None = None, write: bool = False,
            verbose: bool = True, candle_ms: int | None = None) -> dict:
    """Та же сигнатура, что у coinglass_fetch.collect: прогон зовёт её вместо него. key не нужен."""
    coins = [_base_coin(s) for s in symbols] if symbols else None
    state: dict = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "binance",
                   "window": f"{WINDOW}x{INTERVAL}", "coins": {}, "errors": {}, "requests": 0, "liq_source": ("binance_stream" if _liq_sides() else None)}
    if coins is None:
        coins, note = _journal_coins()
        if note:
            state["errors"]["журнал"] = note
    try:                                                      # та же закрытая свеча, что у прогона
        import candle_gate as _cg
        b_ms = int(candle_ms) if candle_ms else _cg.boundary()
        _cg.wait_closed(b_ms, log=lambda m: verbose and print(m, file=sys.stderr))
        state["stamp"] = _cg.stamp(b_ms)
    except Exception:  # noqa: BLE001
        state["stamp"] = {"note": "candle_gate не найден — без калитки"}
    t0 = time.time()

    def _one(coin):
        errs: dict = {}
        entry, n = snap_coin(coin, errs)
        return coin, entry, n, errs

    with ThreadPoolExecutor(max_workers=BINANCE_FETCH_THREADS) as ex:
        for i, (coin, entry, n, errs) in enumerate(ex.map(_one, coins), 1):
            state["coins"][coin] = entry
            state["requests"] += n
            state["errors"].update(errs)
            if verbose and (i % 25 == 0 or i == len(coins)):
                print(f"    binance: {i}/{len(coins)} монет, {time.time() - t0:.0f} с", file=sys.stderr, flush=True)
    if write:
        state["started_at"] = state["at"]
        state["at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        txt = json.dumps(state, ensure_ascii=False, indent=1)
        for p in (OUT_PATH, COMPAT_PATH):
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(txt, encoding="utf-8")
            except OSError:
                state["errors"]["write"] = f"срез не записался в {p.name}"
    return state


def main() -> int:
    ap = argparse.ArgumentParser(description="Срез по монетам с Binance (замена Coinglass)")
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    st = collect(a.symbols or None, write=a.write)
    print(f"монет {len(st['coins'])} · запросов {st['requests']} · ошибок {len(st['errors'])}")
    for c, v in list(st["coins"].items())[:12]:
        f = v.get("fut") or {}
        print(f"  {c:9} тейкер {f.get('taker')} · дельта {f.get('cvd')} · OI ${v.get('oiUsd') or 0:,.0f} "
              f"({v.get('oiChgPct')}%) · фандинг {v.get('funding')}%" + (f" · нет: {','.join(v['missing'])}" if v.get("missing") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
