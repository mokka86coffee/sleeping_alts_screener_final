"""Сбор Coinglass: что рынок ДЕЛАЕТ, а не что о нём думают.

    python sources_coinglass.py            # показать по журналу
    python sources_coinglass.py --write    # записать coinglass.json
    python sources_coinglass.py --probe ONGUSDT   # одна монета подробно

ЧЕМ ЭТО ОТЛИЧАЕТСЯ ОТ ВСЕГО ОСТАЛЬНОГО В ПРОЕКТЕ. Наши датчики
считают по свечам: объём, размах, фигуры. Свеча показывает ИТОГ —
кто победил за час. Здесь приходят сами сделки, разложенные на
агрессивные покупки и продажи: видно не итог, а УСИЛИЕ обеих сторон.
Цена может стоять, пока продавец давит, а покупатель поглощает, — по
свече это тихий час, по этим числам работа.

ЧЕТЫРЕ ВЕЛИЧИНЫ, все проверены на живом ответе 29.08:

  · ТЕЙКЕРСКОЕ ОТНОШЕНИЕ — агрессивные покупки к продажам. Ниже
    единицы значит продавцы бьют по стакану сильнее. По ETH ушло на
    0.81 — шестилетний минимум; по ONG в ночь на 29.08 было 0.80 при
    ходе позиции +50%.

  · НАКОПЛЕННАЯ ДЕЛЬТА (CVD) — та самая, что на графиках дала сигнал
    за пять дней до августовского хода. САМИ ПОСЧИТАТЬ НЕ МОЖЕМ:
    нужны сделки, а у нас только свечи. У ONG за три часа: +207 тыс.,
    −64 тыс., −498 тыс. — перевернулась и обвалилась.

  · ЛИКВИДАЦИИ ПО СТОРОНАМ — не сумма, а КТО. 19.08 вынесло шорты
    (85% ликвидаций), 26.08 уже лонги (270 из 324 млн). Смена стороны
    важнее величины. У ONG в 02:00 лонгов вынесло в шестнадцать раз
    больше шортов.

  · ПРИТОК К КАПИТАЛИЗАЦИИ — сколько денег привели относительно
    размера монеты. Ровно тот вопрос, ради которого затевалась вся
    рамка «денег нет, их приводят». Приходит СПИСКОМ на сто монет
    одним запросом, с окнами от пяти минут до ста двадцати дней.

ЧЕГО ЗДЕСЬ НЕТ И ПОЧЕМУ. Карта ликвидаций — только с тарифа
Professional ($879); на Startup закрыта, и код её не просит, чтобы не
тратить запросы впустую.

ВАЖНОЕ ПРО ФОРМАТ, найдено пробником:
  · отказ приходит ВНУТРИ кода 200, в поле code — проверять до
    разбора данных, иначе «не пустили» неотличимо от «данных нет»;
  · числа приходят СТРОКАМИ ("5501770.193") — приводить явно;
  · точки с «aggregated» ждут МОНЕТУ (ONG) и обязательный
    exchange_list; парные ждут ПАРУ (ONGUSDT) и exchange;
  · в перечне эндпоинтов опечатка: /api/furures/... Настоящий путь
    без неё, но по монете он пуст — берём список на сто монет.

Ключ — только из окружения COINGLASS_KEY. В код не пишем: файл уходит
в репозиторий и в переписку, а это оплаченный доступ.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
    from core_http import log
except Exception:
    BASE_DIR = Path(__file__).resolve().parent
    def log(m: str) -> None:
        print(m)

BASE = "https://open-api-v4.coinglass.com/api"
OUT_PATH = BASE_DIR / "coinglass.json"
EXCHANGES = "Binance,OKX,Bybit"     # обязателен для сводных точек
PAUSE = 0.35                        # 80 запросов в минуту на Startup
BARS = 24                           # сутки часовых баров


def _get(path: str, params: dict, key: str) -> tuple[dict | None, str]:
    """Запрос. Возвращает (данные, причина отказа).

    Отказ Coinglass приходит ВНУТРИ кода 200 — поэтому проверяем поле
    code до того, как трогать data.
    """
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "CG-API-KEY": key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            doc = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, type(e).__name__

    code = str(doc.get("code", "0"))
    if code not in ("0", "None"):
        return None, str(doc.get("msg") or code)[:80]
    return doc.get("data"), ""


def _f(v) -> float:
    """Число из строки или числа. Пустое и мусор — ноль."""
    try:
        x = float(v)
        return x if x == x else 0.0
    except (TypeError, ValueError):
        return 0.0


def _coin(sym: str) -> str:
    s = sym.upper()
    for t in ("USDT", "USDC", "BUSD", "USD"):
        if s.endswith(t) and len(s) > len(t):
            return s[:-len(t)]
    return s


# ── величины по одной монете ─────────────────────────────────────

def taker(coin: str, key: str) -> dict | None:
    """Тейкерское отношение: сутки часовых баров + свежий бар.

    Отдаём и ряд, и последнее значение: одно число говорит о моменте,
    ряд — о том, ухудшается ли давление. У ONG за три часа
    0.985 → 0.910 → 0.801, и это важнее любого из трёх значений.
    """
    rows, err = _get("/futures/aggregated-taker-buy-sell-volume/history",
                     {"symbol": coin, "exchange_list": EXCHANGES,
                      "interval": "1h", "limit": str(BARS)}, key)
    if not isinstance(rows, list) or not rows:
        return None
    ser = []
    for r in rows:
        b = _f(r.get("aggregated_buy_volume_usd"))
        s = _f(r.get("aggregated_sell_volume_usd"))
        if s > 0:
            ser.append(round(b / s, 3))
    if not ser:
        return None
    last3 = ser[-3:]
    return {
        "now": ser[-1],
        "avg24": round(sum(ser) / len(ser), 3),
        "trend": last3,
        # падает три часа подряд — отдельный признак, его и читать
        "falling": len(last3) == 3 and last3[0] > last3[1] > last3[2],
    }


def cvd(coin: str, key: str) -> dict | None:
    """Накопленная дельта. Знак важнее величины: переход через ноль
    означает смену того, кто ведёт."""
    rows, err = _get("/futures/aggregated-cvd/history",
                     {"symbol": coin, "exchange_list": EXCHANGES,
                      "interval": "1h", "limit": str(BARS)}, key)
    if not isinstance(rows, list) or not rows:
        return None
    ser = [_f(r.get("cum_vol_delta")) for r in rows]
    if not ser:
        return None
    pos = sum(1 for x in ser if x > 0)
    return {
        "now": round(ser[-1]),
        "sum24": round(sum(ser)),
        "green_bars": pos,                  # сколько часов из суток вели покупатели
        # перевернулась в течение суток — из плюса в минус
        "flipped_down": len(ser) >= 3 and ser[0] > 0 and ser[-1] < 0,
    }


def liq(coin: str, key: str) -> dict | None:
    """Ликвидации по сторонам. Считаем перекос, а не сумму: важно,
    КОГО вынесло, а величина у мелких монет всегда мала."""
    rows, err = _get("/futures/liquidation/aggregated-history",
                     {"symbol": coin, "exchange_list": EXCHANGES,
                      "interval": "1h", "limit": str(BARS)}, key)
    if not isinstance(rows, list) or not rows:
        return None
    lo = sum(_f(r.get("aggregated_long_liquidation_usd")) for r in rows)
    sh = sum(_f(r.get("aggregated_short_liquidation_usd")) for r in rows)
    if lo + sh <= 0:
        return None
    return {
        "long_usd": round(lo),
        "short_usd": round(sh),
        # доля лонгов в выносе: выше 0.7 — выбивают покупателей
        "long_share": round(lo / (lo + sh), 3),
        "side": "лонги" if lo > sh * 1.5 else ("шорты" if sh > lo * 1.5 else "поровну"),
    }


# ── одним запросом на весь рынок ──────────────────────────────────

def netflow_all(key: str) -> dict:
    """Приток по ста монетам разом, с окнами от пяти минут до ста
    двадцати дней. Здесь же лежит ОТНОШЕНИЕ ПРИТОКА К КАПИТАЛИЗАЦИИ —
    та самая величина: сколько привели денег относительно размера.

    Один запрос вместо шестидесяти — поэтому берём всегда.
    """
    rows, err = _get("/futures/netflow-list", {}, key)
    if not isinstance(rows, list):
        return {}
    out = {}
    for r in rows:
        sym = str(r.get("symbol") or "").upper()
        if not sym:
            continue
        cap = _f(r.get("market_cap"))
        f24 = _f(r.get("net_flow_usd_24h"))
        out[sym] = {
            "flow_1h": round(_f(r.get("net_flow_usd_1h"))),
            "flow_24h": round(f24),
            "flow_7d": round(_f(r.get("net_flow_usd_7d"))),
            "cap": round(cap),
            # ГЛАВНОЕ ЧИСЛО: приток за сутки к капитализации, в процентах.
            # Оно сравнимо между монетами, в отличие от суммы в долларах.
            "flow_to_cap": round(f24 / cap * 100, 3) if cap > 0 else None,
        }
    return out


def collect(symbols: list[str], key: str, quiet: bool = False) -> dict:
    """Полный срез: список притоков + три величины по каждой монете."""
    out = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "coins": {}, "errors": 0}

    flows = netflow_all(key)
    out["flow_universe"] = len(flows)
    time.sleep(PAUSE)

    for sym in symbols:
        c = _coin(sym)
        rec = {}
        for name, fn in (("taker", taker), ("cvd", cvd), ("liq", liq)):
            try:
                v = fn(c, key)
                if v:
                    rec[name] = v
            except Exception as e:
                out["errors"] += 1
                if not quiet:
                    log(f"coinglass {c}/{name}: {type(e).__name__}")
            time.sleep(PAUSE)
        if c in flows:
            rec["flow"] = flows[c]
        if rec:
            out["coins"][c] = rec
    return out


def for_screens(res: dict) -> dict:
    """Сводка потока для экранов: карточка, зал, орбита, схема.

    Экраны не должны разбирать сырой ответ — им нужны готовые списки
    и одно главное значение на каждую величину. Здесь же решается,
    ЧТО считать главным, и это решение объясняется:

      · тейкер — показываем ХУДШИХ. Раздача на растущей позиции
        опаснее давления на упавшей, а растущие у нас в книге;
      · дельта — только перевернувшиеся: само значение без знака
        мало что говорит, а смена знака говорит всё;
      · ликвидации — сторона, а не сумма: у мелких монет суммы
        всегда малы, а перекос виден;
      · приток — к капитализации, потому что она сравнима между
        монетами, в отличие от долларов.
    """
    coins = res.get("coins") or {}
    taker_list, flipped, liq_list, flow_list = [], [], [], []

    for c, r in coins.items():
        t = r.get("taker") or {}
        if t.get("now") is not None:
            taker_list.append({"t": c, "v": t["now"], "fall": bool(t.get("falling"))})
        d = r.get("cvd") or {}
        if d.get("flipped_down"):
            flipped.append(c)
        l = r.get("liq") or {}
        if l.get("side") and l["side"] != "поровну":
            liq_list.append({"t": c, "s": l["side"], "share": l.get("long_share")})
        f = r.get("flow") or {}
        if f.get("flow_to_cap") is not None:
            flow_list.append({"t": c, "v": f["flow_to_cap"]})

    taker_list.sort(key=lambda x: x["v"])            # худшие первыми
    flow_list.sort(key=lambda x: -abs(x["v"]))       # по величине хода денег
    # сторона выноса по всей выборке: чего больше
    longs = sum(1 for x in liq_list if x["s"] == "лонги")
    shorts = sum(1 for x in liq_list if x["s"] == "шорты")

    out = {
        "takerList": taker_list[:8],
        "flipped": flipped,
        "flippedN": len(flipped) or None,
        "liqList": liq_list[:8],
        "flowList": flow_list[:8],
        "at": res.get("at"),
    }
    if taker_list:
        out["takerWorst"] = taker_list[0]
    if flow_list:
        out["flowTop"] = flow_list[0]
    if longs or shorts:
        out["liqSide"] = ("лонги" if longs > shorts else
                          "шорты" if shorts > longs else "поровну")
    return out


def _fmt(coin: str, r: dict) -> str:
    t, d, l, f = r.get("taker"), r.get("cvd"), r.get("liq"), r.get("flow")
    parts = []
    if t:
        mark = " ↓↓↓" if t.get("falling") else ""
        parts.append(f"тейкер {t['now']}{mark}")
    if d:
        parts.append(f"дельта {d['now']:+,}".replace(",", " ")
                     + (" ⚠ перевернулась" if d.get("flipped_down") else ""))
    if l:
        parts.append(f"вынос {l['side']} ({l['long_share']:.0%} лонгов)")
    if f and f.get("flow_to_cap") is not None:
        parts.append(f"приток {f['flow_to_cap']:+.2f}% капы")
    return f"{coin:<10} " + " · ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Сбор Coinglass")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--probe", metavar="SYMBOL", help="одна монета подробно")
    ap.add_argument("--limit", type=int, default=0, help="сколько монет журнала")
    a = ap.parse_args()

    key = os.environ.get("COINGLASS_KEY")
    if not key:
        print("✗ нет COINGLASS_KEY.  export COINGLASS_KEY=ваш_ключ")
        return 1

    if a.probe:
        syms = [a.probe]
    else:
        try:
            from analytics_leaders import tracked_symbols
            syms = sorted(tracked_symbols())
        except Exception:
            syms = ["BTCUSDT", "ETHUSDT"]
        if a.limit:
            syms = syms[:a.limit]

    print(f"монет: {len(syms)}   {datetime.now(timezone.utc):%d.%m %H:%M} UTC")
    res = collect(syms, key)

    print(f"\nсписок притоков: {res.get('flow_universe', 0)} монет рынка\n")
    for coin, r in res["coins"].items():
        print(" ", _fmt(coin, r))

    # то, что стоит увидеть без чтения всего: где давление и раздача
    bad = [(c, r) for c, r in res["coins"].items()
           if (r.get("taker") or {}).get("falling")
           or (r.get("cvd") or {}).get("flipped_down")]
    if bad:
        print(f"\n⚠ ухудшение по потоку: {', '.join(c for c, _ in bad)}")

    if a.write:
        try:
            OUT_PATH.write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                encoding="utf-8")
            print(f"\n✓ записано в {OUT_PATH}")
        except OSError as e:
            print(f"✗ не записалось: {e}")
            return 1
    else:
        print("\n(добавьте --write, чтобы записать coinglass.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
