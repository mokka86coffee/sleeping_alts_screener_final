#!/usr/bin/env python3
"""Срез биткоина на каждый прогон (04.09) — output/btc_pulse.json + строка в liq_log.

Заказ владельца: «заносим это всё в каждый прогон: расчёт перевеса шортов и
лонгов, приток ETF и т.д.». Урок дня: 03.09 карта Coinglass показывала
шорты плотно в одном проценте над ценой и пустоту на полтора процента под
ней — «сквиз скоро» читался с карты за часы; у нас были и часовой интерес,
и своя модель liq_zones_oi, но считали только суммы. Теперь считаем
распределение сами, каждый прогон.

Что пишет (всё из своих источников, чужие индексы не идут):
  map      — карта плеча по цене (liq_zones_oi на 200 часовых свечах Binance
             с интересом): ближайшая плотная полоса сверху/снизу, расстояние
             в %, доллары, «долларов на процент»; суммы над/под ценой в ±3%
             и ±10%; перевес (шорты/лонги) в обоих окнах
  oi       — интерес сейчас, за сутки в %, в монетах (интерес/цена)
  liq      — ликвидации за 24 ч по сторонам (Coinglass), если доступно
  premium  — премия Coinbase последняя и часовой ряд (Coinglass), если доступно
  etf      — последний дневной приток фондов BTC и сумма за 5 дней (Coinglass
             или уже скачанный срез etf_coinglass), если доступно
  read     — одна строка словами для брифа/Телеграма

Сбои источников не роняют: чего нет — null и причина в "missing".

    python3 btc_pulse.py            # печать среза
    python3 btc_pulse.py --write    # + запись output/btc_pulse.json и строки в liq_log.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from analytics_liqmap import liq_zones_oi  # noqa: E402

OUT = BASE_DIR / "output" / "btc_pulse.json"
LOG = BASE_DIR / "output" / "liq_log.jsonl"


def fnum(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


# ── карта плеча по цене ────────────────────────────────────────────
def leverage_map(missing: list[str]) -> dict:
    out: dict = {"px": None, "zones": [], "oi_usd": None, "oi_chg24_pct": None, "oi_btc": None}
    try:
        from core_binance import get_oi_history, klines_1h, ohlcv
    except Exception as e:  # noqa: BLE001
        missing.append(f"core_binance: {type(e).__name__}: {e}")
        return out
    try:
        kl = klines_1h("BTCUSDT")
        oh = get_oi_history("BTCUSDT", "1h", 200)
    except Exception as e:  # noqa: BLE001
        missing.append(f"binance: {type(e).__name__}: {e}")
        return out
    if not kl or not oh:
        missing.append("binance: пустые свечи или интерес")
        return out
    k = ohlcv(kl, tail=len(oh))
    oi = [fnum(r.get("sumOpenInterestValue")) or 0.0 for r in oh]
    m = min(len(k["close"]), len(oi))
    if m < 5:
        missing.append("binance: меньше пяти часов")
        return out
    h, l, c, oi = k["high"][-m:], k["low"][-m:], k["close"][-m:], oi[-m:]
    px = c[-1]
    zones = liq_zones_oi(h, l, c, oi, px)
    out.update(px=px, zones=zones, oi_usd=round(oi[-1], 0),
               oi_chg24_pct=round((oi[-1] / oi[-25] - 1) * 100, 2) if m > 25 and oi[-25] else None,
               oi_btc=round(oi[-1] / px, 0) if px else None)
    # свод по сторонам
    def side(sel):
        zs = [z for z in zones if sel(z["price"])]
        if not zs:
            return None
        near = min(zs, key=lambda z: abs(z["pct"]))
        dens = max(zs, key=lambda z: z["usd"])
        def pack(z):
            return {"price": round(z["price"], 0), "pct": z["pct"], "usd": z["usd"],
                    "usd_per_pct": round(z["usd"] / abs(z["pct"]), 0) if z["pct"] else None}
        return {"nearest": pack(near), "densest": pack(dens),
                "usd_3pct": round(sum(z["usd"] for z in zs if abs(z["pct"]) <= 3), 0),
                "usd_10pct": round(sum(z["usd"] for z in zs if abs(z["pct"]) <= 10), 0),
                "usd_total": round(sum(z["usd"] for z in zs), 0)}
    up, dn = side(lambda p: p > px), side(lambda p: p < px)
    out["above"], out["below"] = up, dn   # above = шорты (стопы над ценой), below = лонги
    def ratio(a, b, key):
        if not a or not b or not b[key]:
            return None
        return round(a[key] / b[key], 2)
    out["short_to_long_3pct"] = ratio(up, dn, "usd_3pct")
    out["short_to_long_10pct"] = ratio(up, dn, "usd_10pct")
    return out


# ── Coinglass: ликвидации, премия, ETF ─────────────────────────────
def _cg():
    try:
        from coinglass_fetch import _key, get
        return get, _key()
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _rows(data):
    """Достаёт список строк из ответа Coinglass любой формы."""
    if isinstance(data, dict):
        d = data.get("data", data)
        if isinstance(d, list):
            return [r for r in d if isinstance(r, dict)]
        if isinstance(d, dict):
            for v in d.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    return v
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


def _first(row: dict, *keys):
    for k in keys:
        if k in row and row[k] is not None:
            return fnum(row[k])
    return None


def coinglass_block(missing: list[str]) -> dict:
    out = {"liq": None, "premium": None, "etf": None}
    get, key = _cg()
    if get is None:
        missing.append(f"coinglass: {key}")
        return out
    # ликвидации за 24 ч по сторонам
    try:
        code, data = get("/futures/liquidation/aggregated-history",
                         {"exchange_list": "ALL", "symbol": "BTC", "interval": "1h", "limit": 24}, key)
        rows = _rows(data) if code == 200 else []
        if rows:
            lo = sum(_first(r, "aggregated_long_liquidation_usd", "long_liquidation_usd", "longLiquidationUsd") or 0 for r in rows)
            sh = sum(_first(r, "aggregated_short_liquidation_usd", "short_liquidation_usd", "shortLiquidationUsd") or 0 for r in rows)
            out["liq"] = {"long_24h_usd": round(lo, 0), "short_24h_usd": round(sh, 0),
                          "hours": len(rows)}
        else:
            missing.append(f"liq: код {code}: {str(data)[:120]}")
    except Exception as e:  # noqa: BLE001
        missing.append(f"liq: {type(e).__name__}: {e}")
    # премия Coinbase
    try:
        code, data = get("/index/coinbase-premium-index", {"interval": "1h", "limit": 30}, key)
        rows = _rows(data) if code == 200 else []
        if rows:
            ser = [_first(r, "premium", "premium_index", "premiumIndex", "value") for r in rows]
            ser = [x for x in ser if x is not None]
            if ser:
                pos = 0
                for x in reversed(ser):
                    if x > 0:
                        pos += 1
                    else:
                        break
                out["premium"] = {"last": ser[-1], "hours_positive": pos,
                                  "min_24h": min(ser[-24:]), "max_24h": max(ser[-24:])}
        else:
            missing.append(f"premium: код {code}: {str(data)[:120]}")
    except Exception as e:  # noqa: BLE001
        missing.append(f"premium: {type(e).__name__}: {e}")
    # приток ETF (сначала — уже скачанный срез проекта, потом API)
    etf = None
    for pth in sorted((BASE_DIR / "output").glob("*etf*.json")):
        try:
            j = json.loads(pth.read_text(encoding="utf-8"))
        except ValueError:
            continue
        rows = _rows(j)
        rows = [r for r in rows if any(k in r for k in ("flow_usd", "fund_flow_usd", "net_flow", "netFlow", "flow"))]
        if rows:
            vals = [(_first(r, "flow_usd", "fund_flow_usd", "net_flow", "netFlow", "flow"), r.get("date") or r.get("timestamp") or r.get("time")) for r in rows]
            vals = [v for v in vals if v[0] is not None]
            if vals:
                etf = {"last_usd": vals[-1][0], "last_at": vals[-1][1], "sum5_usd": round(sum(v[0] for v in vals[-5:]), 0),
                       "days_positive": sum(1 for v in vals[-5:] if v[0] > 0), "source": pth.name}
                break
    if etf is None:
        try:
            code, data = get("/etf/bitcoin/flow-history", {}, key)
            rows = _rows(data) if code == 200 else []
            vals = [(_first(r, "flow_usd", "fund_flow_usd", "net_flow", "netFlow", "flow", "total_flow_usd"), r.get("date") or r.get("timestamp")) for r in rows]
            vals = [v for v in vals if v[0] is not None]
            if vals:
                etf = {"last_usd": vals[-1][0], "last_at": vals[-1][1], "sum5_usd": round(sum(v[0] for v in vals[-5:]), 0),
                       "days_positive": sum(1 for v in vals[-5:] if v[0] > 0), "source": "coinglass"}
            else:
                missing.append(f"etf: код {code}: {str(data)[:120]}")
        except Exception as e:  # noqa: BLE001
            missing.append(f"etf: {type(e).__name__}: {e}")
    out["etf"] = etf
    return out


# ── строка словами ─────────────────────────────────────────────────
def _m(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    return f"${v / 1e9:.2f}B" if abs(v) >= 1e9 else f"${v / 1e6:.0f}M"


def read_line(p: dict) -> str:
    mp, parts = p["map"], []
    if mp.get("px"):
        parts.append(f"BTC {mp['px']:,.0f}")
    up, dn = mp.get("above"), mp.get("below")
    if up and dn:
        r3 = mp.get("short_to_long_3pct")
        su = "пусто" if not up["usd_3pct"] else _m(up["usd_3pct"])
        sd = "пусто" if not dn["usd_3pct"] else _m(dn["usd_3pct"])
        parts.append(f"плечо в 3%: шорты сверху {su} / лонги снизу {sd}"
                     + (f" (×{r3})" if r3 and up["usd_3pct"] and dn["usd_3pct"] else ""))
        parts.append(f"ближайшая плита сверху {up['nearest']['price']:,.0f} (+{up['nearest']['pct']}%), снизу {dn['nearest']['price']:,.0f} ({dn['nearest']['pct']}%)")
        if r3 and r3 >= 1.5 and up["nearest"]["pct"] <= 1.5:
            parts.append("ЗАРЯД НА СКВИЗ ВВЕРХ: шорты плотно в полутора процентах")
        elif r3 and r3 <= 0.67 and abs(dn["nearest"]["pct"]) <= 1.5:
            parts.append("ЗАРЯД НА ВЫНОС ВНИЗ: лонги плотно в полутора процентах")
    elif up and not dn:
        parts.append("плечо только сверху (шорты), снизу пусто")
    elif dn and not up:
        parts.append("плечо только снизу (лонги), сверху пусто")
    if mp.get("oi_chg24_pct") is not None:
        parts.append(f"интерес {mp['oi_chg24_pct']:+.1f}% за сутки")
    lq = p.get("liq")
    if lq:
        parts.append(f"ликвидации 24ч: шортов {_m(lq['short_24h_usd'])}, лонгов {_m(lq['long_24h_usd'])}")
    pr = p.get("premium")
    if pr:
        parts.append(f"премия Coinbase {pr['last']:+.0f}" + (f", плюс {pr['hours_positive']} ч подряд" if pr["hours_positive"] else ""))
    et = p.get("etf")
    if et:
        d = str(et.get("last_at") or "")[:10]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        when = ("за сегодня ещё не отчитано" if d and d < today and not et["last_usd"] else
                (f"за {d[8:10]}.{d[5:7]}" if d else "за день"))
        parts.append(f"ETF: {_m(et['last_usd'])} {when}, {_m(et['sum5_usd'])} за 5 дней ({et['days_positive']} из 5 в плюс)")
    return " · ".join(parts) if parts else "срез биткоина пуст"


def build() -> dict:
    missing: list[str] = []
    now = datetime.now(timezone.utc)
    p = {"at": now.strftime("%Y-%m-%d"), "hm": now.strftime("%H:%M"), "sym": "BTC"}
    p["map"] = leverage_map(missing)
    p.update(coinglass_block(missing))
    p["missing"] = missing
    p["read"] = read_line(p)
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    p = build()
    print(p["read"])
    if p["missing"]:
        print("нет данных: " + "; ".join(p["missing"]))
    if a.write:
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
        print(f"btc_pulse: записано {OUT.name} и строка в {LOG.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
