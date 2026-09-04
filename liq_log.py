#!/usr/bin/env python3
"""Лог сбора ликвидности — одна строка на монету за прогон (техдолг Л, §8, 04.09).

Заказ владельца: «давай писать каждый прогон по нашим монетам, потом через
пару дней пройдём по графикам и разработаем формулу». Ничего не решает,
не отбирает и не показывает — только пишет числа, из которых потом
выводится формула «куда идут за ликвидностью и когда».

Источники (все свои):
  cq_v2/<coin>.json      — дневки: ohlcv, oi, funding, trade, liq
  pulse.json             — ряд прогонов (t, price, oi_usd, funding) — часовая
                           карта по приросту интереса (liq_zones_oi)
  output/coinglass_crowd.json — доля толпы в лонге (если есть)
  analytics_liqmap       — liq_zones (дневная карта), liq_zones_oi
                           (часовая по приросту OI), fuel_to_cap

Схемы источников читаются мягко: ключи ищутся по нескольким именам,
чего нет — пишется null и попадает в список «нет данных» в конце строки.
Так первый прогон на одной монете сам покажет, какие поля не нашлись.

    python3 liq_log.py --only BLESS            # одна монета, печать строки
    python3 liq_log.py --only BLESS --write    # то же + дописать в лог
    python3 liq_log.py --write                 # все монеты cq_v2/ (после
                                               # того как на одной сошлось)
    python3 liq_log.py --only BLESS --cap 22e6 # капа руками, если снимка нет
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from analytics_liqmap import fuel_to_cap, liq_zones, liq_zones_oi
except ImportError:  # запуск не из корня проекта
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from analytics_liqmap import fuel_to_cap, liq_zones, liq_zones_oi

# «сбор» по дневкам: high ≥ старт×(1+HARVEST_PCT) за ≤HARVEST_DAYS дней,
# затем откат ≥ RETRACE доли хода за ≤RETRACE_DAYS дней (техдолг Л, §8)
HARVEST_PCT = 0.5     # ход ≥ +50% от базы…
HARVEST_DAYS = 10     # …за ≤10 дней (BLESS 21–30.08: ×2 за 7 дней; 01–06.08: ×3.7 за 5)
RETRACE = 0.5         # откат ≥ половины хода…
RETRACE_DAYS = 7      # …за ≤7 дней после пика
BASE_DAYS = 5         # база сбора = минимум low за 5 дней до старта
VOL_CAP = 3.0         # срез оборота бара в карте: ×3 медианы окна (калибровка 04.09 на BLESS:
                      # без среза бары пампа давят все зоны, карта теряет плиту лонгов у базы
                      # и полосу шортов 0.012–0.013, которые видны на R2D2; со срезом — обе есть)
BAND_TOL = 3.0        # % — пик «лёг в полосу», если ближе этого
NORM_DAYS = 30

KEYS = {
    "t": ("datetime", "time", "t", "ts", "date", "open_time"),
    "o": ("open", "o"),
    "h": ("high", "h", "max"),
    "l": ("low", "l", "min"),
    "c": ("close", "c", "price"),
    "v": ("quote_volume", "volume_usd", "vol_usd", "turnover", "volume", "v", "vol"),
    "oi": ("open_interest", "oi", "oi_usd", "openInterest"),
    "fund": ("funding_rate", "funding", "rate", "f"),
}


def pick(row: dict, key: str):
    for k in KEYS[key]:
        if k in row and row[k] is not None:
            return row[k]
    return None


def fnum(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def ts_of(v) -> float | None:
    """Время строки в секундах: ISO-строка, миллисекунды или секунды."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) / (1000 if v > 1e11 else 1)
    s = str(v).replace("Z", "+00:00")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.timestamp()
        except ValueError:
            continue
    return None


def rows_of(obj, section: str | None = None) -> list[dict]:
    """Ряд свечей из файла любой формы: список, {section:[...]}, {data:[...]}."""
    if isinstance(obj, list):
        return [r for r in obj if isinstance(r, dict)]
    if isinstance(obj, dict):
        for k in ((section,) if section else ()) + ("data", "rows", "candles", "klines"):
            if k and isinstance(obj.get(k), list):
                return [r for r in obj[k] if isinstance(r, dict)]
    return []


def series(rows: list[dict], key: str) -> list[float | None]:
    return [fnum(pick(r, key)) for r in rows]


def clean_ohlc(rows: list[dict]) -> dict:
    """Согласованные ряды h/l/c/v/t; строки без close выбрасываются."""
    out = {"t": [], "h": [], "l": [], "c": [], "v": []}
    rows = sorted(rows, key=lambda r: ts_of(pick(r, "t")) or 0)   # cq_v2 лежит вразнобой
    for r in rows:
        c = fnum(pick(r, "c"))
        if not c:
            continue
        h, lo, v = fnum(pick(r, "h")), fnum(pick(r, "l")), fnum(pick(r, "v"))
        out["t"].append(ts_of(pick(r, "t")))
        out["c"].append(c)
        out["h"].append(h if h else c)
        out["l"].append(lo if lo else c)
        out["v"].append(v if v else 0.0)
    return out


# ── признаки ─────────────────────────────────────────────────────
def find_harvests(d: dict) -> list[dict]:
    """Все «сборы» по дневкам: старт, пик, откат."""
    c, h, lo, t = d["c"], d["h"], d["l"], d["t"]
    n, out, i = len(c), [], 0
    while i < n - 1:
        start = min(lo[max(0, i - BASE_DAYS):i + 1])          # база: дно перед стартом
        peak_j, peak = None, start
        for j in range(i + 1, min(n, i + HARVEST_DAYS + 1)):
            if h[j] > peak:
                peak, peak_j = h[j], j
        if peak_j is not None and peak >= start * (1 + HARVEST_PCT) and c[i] < start * 1.15:
            move = peak - start
            back_j, low_after = None, peak
            for j in range(peak_j + 1, min(n, peak_j + RETRACE_DAYS + 1)):
                low_after = min(low_after, lo[j])
                if peak - low_after >= move * RETRACE:
                    back_j = j
                    break
            if back_j is not None:
                out.append({"i_start": i, "i_peak": peak_j, "i_back": back_j,
                            "date": _dstr(t[peak_j]), "from": start, "peak": peak,
                            "x": round(peak / start, 2),
                            "retrace_pct": round((low_after / peak - 1) * 100, 1)})
                i = back_j
                continue
        i += 1
    return out


def _dstr(ts) -> str | None:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if ts else None


def capped(v: list[float], upto: int | None = None) -> list[float]:
    """Оборот со срезом ×VOL_CAP медианы окна карты (60 бар до точки)."""
    w = v[:upto] if upto is not None else v
    tail = [x for x in w[-60:] if x] or [0.0]
    lim = statistics.median(tail) * VOL_CAP
    return [min(x, lim) for x in w]


def band_hit(d: dict, hv: dict) -> dict:
    """Карта на день СТАРТА сбора и в какую полосу лёг пик (допуск BAND_TOL %)."""
    i0 = hv["i_start"]
    z = liq_zones(d["h"][:i0 + 1], d["l"][:i0 + 1], d["c"][:i0 + 1], capped(d["v"], i0 + 1),
                  d["c"][i0]) if i0 >= 5 else []
    ups = [q for q in z if q["price"] > d["c"][i0]]
    if not ups:
        return {"bands_above": 0}
    peak = hv["peak"]
    near = min(ups, key=lambda q: abs(q["price"] / peak - 1))
    dist = abs(near["price"] / peak - 1) * 100
    top = max(ups, key=lambda q: q["weight"])
    farthest = max(ups, key=lambda q: q["price"])
    return {"bands_above": len(ups), "hit": dist <= BAND_TOL,
            "hit_price": round(near["price"], 8), "hit_dist_pct": round(dist, 2),
            "hit_is_densest": near is top, "hit_is_farthest": near is farthest,
            "hit_is_nearest": near is min(ups, key=lambda q: q["price"]),
            "hit_weight": near["weight"]}


def vol_after(d: dict, i_peak: int, days: int = 4) -> float | None:
    """Оборот через 3–5 дней после пика к норме 30 дн до старта (ENA-признак)."""
    v = d["v"]
    base = [x for x in v[max(0, i_peak - NORM_DAYS):i_peak] if x]     # 30 дн до пика, среднее
    win = [x for x in v[i_peak + 3:i_peak + 3 + days] if x]
    if not base or not win:
        return None
    return round(statistics.mean(win) / statistics.mean(base) * 100, 1)


def targets(zones: list[dict], price: float, wkey: str) -> dict:
    """Плотнейшая и ближайшая полоса над/под ценой + доллары (вес) на процент."""
    def side(sel):
        zs = [z for z in zones if sel(z["price"])]
        if not zs:
            return None, None
        dens = max(zs, key=lambda z: z.get(wkey) or 0)
        near = min(zs, key=lambda z: abs(z["pct"]))
        def pack(z):
            w = z.get(wkey) or 0
            return {"price": round(z["price"], 8), "pct": z["pct"], wkey: w,
                    "per_pct": round(w / abs(z["pct"]), 4) if z["pct"] else None}
        return pack(dens), pack(near)
    up_d, up_n = side(lambda p: p > price)
    dn_d, dn_n = side(lambda p: p < price)
    return {"target_up": up_d, "nearest_up": up_n, "target_dn": dn_d, "nearest_dn": dn_n}


# ── капитализация: ищем в последнем снимке прогона ──────────────
CAP_KEYS = ("market_cap", "mcap", "cap_usd", "marketcap", "marketCap", "market_cap_usd", "cap")


def _walk_caps(obj, out: dict, sym_hint: str | None = None, depth: int = 0) -> None:
    """Обходит любой JSON: у узла с тикером ищет ключ капитализации."""
    if depth > 6:
        return
    if isinstance(obj, dict):
        sym = None
        for k in ("sym", "symbol", "ticker", "coin"):
            v = obj.get(k)
            if isinstance(v, str) and v.isupper() and 2 <= len(v) <= 14:
                sym = v.upper().replace("USDT", "")
                break
        sym = sym or sym_hint
        if sym:
            for k in CAP_KEYS:
                c = fnum(obj.get(k))
                if c and 1e4 <= c <= 1e13:
                    out.setdefault(sym, c)
                    break
        for k, v in obj.items():
            hint = k.upper().replace("USDT", "") if (isinstance(k, str) and k.isupper() and 2 <= len(k) <= 14) else sym_hint
            _walk_caps(v, out, hint, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            _walk_caps(v, out, sym_hint, depth + 1)


def find_caps(base: Path) -> dict:
    """{SYM: cap_usd} из последнего output/runs/run-*.json, иначе из output/reputation.json."""
    out: dict = {}
    runs = sorted((base / "output" / "runs").glob("run-*.json"))
    for pth in ([runs[-1]] if runs else []) + [base / "output" / "reputation.json"]:
        if pth.exists():
            try:
                _walk_caps(json.loads(pth.read_text(encoding="utf-8")), out)
            except ValueError:
                continue
        if out:
            break
    return out


# ── сборка строки ────────────────────────────────────────────────
def build(sym: str, base: Path, cap: float | None, crowd: dict) -> dict:
    missing: list[str] = []
    now = datetime.now(timezone.utc)
    row: dict = {"at": now.strftime("%Y-%m-%d"), "hm": now.strftime("%H:%M"), "sym": sym}

    # капа: сначала external_data.get_fundamentals — CoinGecko через кэш
    # прогона cache_fundamental/ (12 ч); прогон её уже качал, сети ноль.
    # Потом снимок прогона, потом --cap.
    if not cap:
        try:
            from external_data import get_fundamentals
            cap = fnum(get_fundamentals(sym + "USDT").mcap_usd) or None
            if not cap:
                missing.append("cap: external_data вернул 0 (нет CoinGecko id или кэша)")
        except Exception as e:
            cap = None
            missing.append(f"cap: external_data — {type(e).__name__}: {e}")
    cq_path = base / "cq_v2" / f"{sym.lower()}.json"
    if not cq_path.exists():
        return {**row, "error": f"нет {cq_path}"}
    cq = json.loads(cq_path.read_text(encoding="utf-8"))
    d = clean_ohlc(rows_of(cq, "ohlcv"))
    if len(d["c"]) < 10:
        return {**row, "error": "дневок меньше десяти"}
    if all(h == c for h, c in zip(d["h"], d["c"])):
        missing.append("high/low в дневках (карта по close)")
    px = d["c"][-1]
    row["px"] = px

    # интерес, фандинг, оборот
    oi_rows = sorted(rows_of(cq, "oi"), key=lambda r: ts_of(pick(r, "t")) or 0)
    oi = [fnum(pick(r, "oi")) for r in oi_rows]
    oi = [x for x in oi if x is not None]
    row["oi_usd"] = round(oi[-1], 2) if oi else None
    if not oi:
        missing.append("oi")
    fund = [fnum(pick(r, "fund")) for r in sorted(rows_of(cq, "funding"), key=lambda r: ts_of(pick(r, "t")) or 0)]
    fund = [x for x in fund if x is not None]
    row["funding"] = fund[-1] if fund else None
    if not fund:
        missing.append("funding")
    v = d["v"]
    row["vol24_usd"] = round(v[-1], 2) if v[-1] else None
    base30 = [x for x in v[-NORM_DAYS - 1:-1] if x]
    row["vol_to_norm30"] = round(v[-1] / statistics.median(base30), 3) if base30 and v[-1] else None
    row["vol_to_oi"] = round(v[-1] / oi[-1], 3) if oi and v[-1] else None
    # ENA-ПРИЗНАК ЖИВЬЁМ (04.09): после дня-всплеска оборот в следующие дни —
    # «покупатель остался» (ENA: 140% нормы через 3–5 дн) или «колыхание»
    # (BLESS/ONG/BMT: 13–35%). Порог выводится по логу, здесь только числа.
    win = v[-8:-1]
    if win and max(win):
        sp = len(v) - 8 + win.index(max(win))
        row["spike_day"] = _dstr(d["t"][sp])
        row["days_since_spike"] = len(v) - 1 - sp
        row["spike_vol_to_norm"] = round(v[sp] / statistics.median(base30), 2) if base30 else None
        row["vol_to_spike_pct"] = round(v[-1] / v[sp] * 100, 1) if v[-1] else None
        row["vol_to_yesterday_pct"] = round(v[-1] / v[-2] * 100, 1) if len(v) > 1 and v[-2] and v[-1] else None
    else:
        row["spike_day"] = row["days_since_spike"] = row["spike_vol_to_norm"] = row["vol_to_spike_pct"] = row["vol_to_yesterday_pct"] = None
    row["cap_usd"] = cap          # из снимка прогона (output/runs/run-*.json) или --cap
    row["oi_to_cap"] = round(oi[-1] / cap, 4) if oi and cap else None
    if not cap:
        missing.append("cap")
    # output/coinglass_crowd.json: {"BLESS": {"crowd": {"longPct", "chg1d"}, "top": {...}}}
    cr = crowd.get(sym) or crowd.get(sym + "USDT") or {}
    c_all = cr.get("crowd") if isinstance(cr.get("crowd"), dict) else cr
    c_top = cr.get("top") if isinstance(cr.get("top"), dict) else {}
    row["crowd_long_pct"] = fnum(c_all.get("longPct") or c_all.get("long_pct") or c_all.get("long")) if c_all else None
    row["crowd_long_chg1d"] = fnum(c_all.get("chg1d")) if c_all else None
    row["top_long_pct"] = fnum(c_top.get("longPct")) if c_top else None
    if row["crowd_long_pct"] is None:
        missing.append("crowd")

    # сборы, флэт, оборот после сбора
    hv = find_harvests(d)
    row["harvests"] = len(hv)
    if hv:
        last = hv[-1]
        row["flat_days"] = len(d["c"]) - 1 - last["i_back"]
        row["last_harvest"] = {**{k: last[k] for k in ("date", "from", "peak", "x", "retrace_pct")},
                               **band_hit(d, last), "vol_after_pct": vol_after(d, last["i_peak"])}
        row["harvest_bands"] = [band_hit(d, h) | {"date": h["date"], "x": h["x"]} for h in hv]
    else:
        row["flat_days"] = None
        row["last_harvest"] = None

    # карты сейчас
    zd = liq_zones(d["h"], d["l"], d["c"], capped(d["v"]), px)
    row["zones_day"] = zd
    row["zones_day_raw"] = liq_zones(d["h"], d["l"], d["c"], d["v"], px)   # без среза — для калибровки
    row.update(targets(zd, px, "weight"))

    # ЧАСОВАЯ КАРТА, вариант 1 — живьём с Binance через core_binance (кэш
    # прогона: если метрики уже качали klines_1h и историю интереса, сети
    # ноль): 200 часовых свечей с high/low и sumOpenInterestValue по часам.
    zh, src_h = [], None
    try:
        from core_binance import get_oi_history, klines_1h, ohlcv as _ohlcv
        kl = klines_1h(sym + "USDT")
        oh = get_oi_history(sym + "USDT", "1h", 200)
        if kl and oh:
            k = _ohlcv(kl, tail=len(oh))
            oi_h = [fnum(r.get("sumOpenInterestValue")) or 0.0 for r in oh]
            m = min(len(k["close"]), len(oi_h))
            if m >= 5:
                zh = liq_zones_oi(k["high"][-m:], k["low"][-m:], k["close"][-m:], oi_h[-m:], px)
                src_h = "binance"
    except Exception as e:     # нет модуля / нет сети / не из корня — идём в pulse
        zh = []
        missing.append(f"часы binance: {type(e).__name__}: {e}")
    # ЧАСОВАЯ КАРТА, вариант 2 — из pulse.json (ряд прогонов: t, price, oi_usd, funding;
    # свечей там нет — high/low = price, это карта по приросту интереса, не по
    # барам). hourly/ с Binance интереса не содержит, поэтому не годится.
    prow = None
    for pp in ((base / "pulse.json", base / "output" / "pulse.json") if not zh else ()):
        if pp.exists():
            try:
                pj = json.loads(pp.read_text(encoding="utf-8"))
            except ValueError:
                continue
            prow = pj.get(sym + "USDT") or pj.get(sym) or (pj.get("coins") or {}).get(sym + "USDT")
            if prow:
                break
    if prow:
        prow = sorted((r for r in prow if fnum(r.get("price")) and fnum(r.get("oi_usd"))),
                      key=lambda r: fnum(r.get("t")) or 0)
        pc = [fnum(r["price"]) for r in prow]
        po = [fnum(r["oi_usd"]) for r in prow]
        pf = [fnum(r.get("funding")) or 0.0 for r in prow]
        if len(pc) >= 5:
            zh = liq_zones_oi(pc[-200:], pc[-200:], pc[-200:], po[-200:], px, pf[-200:])
            src_h = "pulse"
            row["pulse_points"] = len(pc)
            row["oi_x_8d"] = round(po[-1] / po[0], 3) if po[0] else None      # интерес за окно пульса
        else:
            missing.append("pulse: точек меньше пяти")
    elif not zh:
        missing.append("часовая карта: ни binance, ни pulse")
    row["zones_hour"] = zh
    row["zones_hour_src"] = src_h
    f2c = fuel_to_cap(zh, px, cap) if zh and cap else None
    row["fuel_above_cap"] = f2c["above"] if f2c else None
    row["fuel_below_cap"] = f2c["below"] if f2c else None
    row["missing"] = missing
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="монеты (BLESS ONG …)")
    ap.add_argument("--write", action="store_true", help="дописать в output/liq_log.jsonl")
    ap.add_argument("--cap", type=float, help="капитализация руками (одна монета)")
    ap.add_argument("--base", default=".", help="корень проекта")
    a = ap.parse_args()
    base = Path(a.base)
    crowd = {}
    cp = base / "output" / "coinglass_crowd.json"
    if cp.exists():
        try:
            j = json.loads(cp.read_text(encoding="utf-8"))
            crowd = j.get("coins", j) if isinstance(j, dict) else {}
        except ValueError:
            pass
    caps = find_caps(base)
    sp = base / "cq_v2" / "_summary.json"
    if sp.exists():
        try:
            j = json.loads(sp.read_text(encoding="utf-8"))
            for k, vv in (j.get("coins", j) if isinstance(j, dict) else {}).items():
                if isinstance(vv, dict):
                    c = fnum(vv.get("cap_usd") or vv.get("market_cap") or vv.get("mcap"))
                    if c:
                        caps[str(k).upper().replace("USDT", "")] = c
        except ValueError:
            pass
    syms = [s.upper().replace("USDT", "") for s in a.only] if a.only else \
        sorted(p.stem.upper() for p in (base / "cq_v2").glob("*.json") if not p.name.startswith("_"))
    out = base / "output" / "liq_log.jsonl"
    n_ok = 0
    for s in syms:
        row = build(s, base, a.cap or None, crowd) if a.cap else build(s, base, None, crowd)
        if row.get("cap_usd") is None and caps.get(s):        # запас: из снимка прогона
            row = build(s, base, caps[s], crowd)
        if "error" in row:
            print(f"{s}: {row['error']}")
            continue
        n_ok += 1
        if a.only:
            print(json.dumps(row, ensure_ascii=False, indent=1))
        if a.write:
            out.parent.mkdir(exist_ok=True)
            with out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"liq_log: монет {n_ok} из {len(syms)}" + (f" → {out}" if a.write else " (без записи)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
