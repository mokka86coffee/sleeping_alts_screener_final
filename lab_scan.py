#!/usr/bin/env python3
"""ПЕРЕБОР ЗАКОНОМЕРНОСТЕЙ БЕЗ ПОДСКАЗКИ (16.09; владелец: «ты же сам всё это можешь увидеть, почему видишь только
после моих слов?»). Машина строит условия сама и проверяет каждое против контроля; человек отбирает.

Данные: получасовки биржи по монетам сводки (core_binance.get_klines, до LAB_BARS баров) + архив
cq_v2/intraday (интерес, тип бара, фандинг, оборот) там, где есть.
Признаки на каждом баре монеты:
  время:    час UTC (группами по 2), день недели, «выходной», часов от последнего открытия сессии (0–1, 1–2, 2–4, 4+),
            какая сессия последней открылась;
  монета:   ход за 2 / 6 / 12 / 24 ч (вниз <−3, ровно, вверх >+3 — и «сильно» ±8), z-score(20), размах бара к норме,
            оборот бара к норме (архив), тип бара по плечу и серия из трёх, интерес за сутки, фандинг (архив);
  доска:    медиана хода доски за 6 ч, доля растущих, их ход за 4 ч (разворот вниз / вверх), биткоин за 12 ч.
Условия: каждый признак по отдельности и все пары признаков. Для каждого — форвард 2 / 6 / 12 ч, лонг и шорт.
Отбор: n ≥ SCAN_MIN_N, край к контролю того же часа ≥ SCAN_MIN_EDGE, знак края одинаков в обеих половинах периода.
Печатает верхние SCAN_TOP по краю на 6 ч — отдельно лонг и шорт, с n, медианой, долей ≥+2% и обеими половинами.
Ничего не пишет. `python3 lab_scan.py --days 30`.
"""
from __future__ import annotations

import argparse
import itertools
import json
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

LAB_BARS = 1500
SCAN_MIN_N = 100
SCAN_MIN_EDGE = 0.4      # % к контролю на 6 ч
SCAN_TOP = 30
OPENS = [21, 0, 7, 13]
SESS_NAME = {21: "Сидней", 0: "Токио", 7: "Лондон", 13: "Нью-Йорк"}
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def coins() -> list[str]:
    nm = _read(BASE_DIR / "output" / "near_move.json") or {}
    out = [str(s).upper() for s in (nm.get("coins") or {}).keys()]
    return sorted(set(s if s.endswith("USDT") else s + "USDT" for s in out))


def klines(sym: str, limit: int, hourly: bool = False):
    if hourly:
        p = BASE_DIR / "hourly" / f"{sym.replace('USDT', '').lower()}.json"
        try:
            arr = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        out = sorted((int(b["t"]), float(b["h"]), float(b["l"]), float(b["c"])) for b in arr if isinstance(b, dict) and b.get("t") and b.get("c"))
        return out[-limit:] if limit else out
    import core_binance as cb
    from core_binance import K_HIGH, K_LOW, K_OPEN_TIME, get_klines
    KC = getattr(cb, "K_CLOSE", 4)
    ks = get_klines(sym, "30m", limit=limit) or []
    return sorted((int(k[K_OPEN_TIME]), float(k[K_HIGH]), float(k[K_LOW]), float(k[KC])) for k in ks)


def archive(sym: str) -> dict:
    p = BASE_DIR / "cq_v2" / "intraday" / f"{sym.replace('USDT', '').lower()}.jsonl"
    out = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            t = int(datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
            f = r.get("fut") or {}
            out[t] = (r.get("oi_type"), r.get("oi_chg_pct"), r.get("funding"), (f.get("b") or 0) + (f.get("s") or 0))
        except (ValueError, KeyError):
            continue
    return out


def regime(C, i, bars, flat_days_bars=None):
    """РЕЖИМ ПО БАРУ, без заглядывания вперёд (16.09, владелец: «видишь ли ты — был флэт, слив, долгий или недолгий
    рост»): за последние `bars` баров эффективность хода = |конец−начало| / сумма |шагов|. Высокая — направленный
    ход (рост/слив), низкая — флэт, сколько бы ни дёргалось. Плюс длительность: сколько баров подряд держится."""
    if i < bars:
        return None
    w = C[i - bars:i + 1]
    net = w[-1] / w[0] - 1
    path = sum(abs(w[k] / w[k - 1] - 1) for k in range(1, len(w))) or 1e-9
    eff = abs(net) / path
    if eff < 0.25:
        return "флэт"
    return ("рост" if net > 0 else "слив") + (" сильный" if abs(net) >= 0.25 else "")


def regime_len(C, i, bars, cur):
    """сколько баров подряд держится тот же режим — «долгий» или «недолгий»"""
    n = 0
    j = i
    while j > bars and n < 240:
        if regime(C, j, bars) != cur:
            break
        n += 1
        j -= 1
    return n


def band(x, lo, hi, big=None):
    if x is None:
        return None
    if big and x <= -big:
        return "сильно ↓"
    if big and x >= big:
        return "сильно ↑"
    return "↓" if x < lo else "↑" if x > hi else "ровно"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--only")
    ap.add_argument("--min", type=int, default=SCAN_MIN_N)
    ap.add_argument("--top", type=int, default=SCAN_TOP)
    ap.add_argument("--write", action="store_true", help="записать верхние окна в output/windows.json для карточки и ботов")
    ap.add_argument("--hourly", action="store_true", help="часовые свечи из hourly/*.json (полгода) вместо получасовок биржи")
    ap.add_argument("--archive", action="store_true", help="всё из cq_v2/intraday: цена, размах, интерес, фандинг, тип бара — без запросов к бирже")
    a = ap.parse_args()
    BPH = 1 if a.hourly else 2        # баров в часе
    if a.hourly:
        syms = [x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in a.only.split(",")] if a.only else \
               sorted(p.stem.upper() + "USDT" for p in (BASE_DIR / "hourly").glob("*.json") if p.stem.lower() != "btc")
        bars = a.days * 24 + 60
    else:
        syms = [x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in a.only.split(",")] if a.only else coins()
        bars = min(LAB_BARS, a.days * 48 + 60)
    data, arch = {}, {}
    for s in syms:
        try:
            k = klines(s, bars, a.hourly)
        except Exception as ex:  # noqa: BLE001
            print(f"{s}: клайны не получены — {type(ex).__name__}")
            continue
        if len(k) >= 200:
            data[s] = k
            arch[s] = archive(s)
    try:
        btc = klines("BTCUSDT", bars, a.hourly)
        btc_c = {t: c for t, _, _, c in btc}
    except Exception:  # noqa: BLE001
        btc_c = {}
    if not data:
        print("нет данных")
        return 0
    # ── доска по барам
    idx = {s: {t: i for i, (t, *_) in enumerate(k)} for s, k in data.items()}

    def ret(s, t, h):
        k, ix = data[s], idx[s]
        if t not in ix:
            return None
        i = ix[t]
        j = i - int(h * BPH)
        return (k[i][3] / k[j][3] - 1) * 100 if j >= 0 else None

    times = sorted(set(t for k in data.values() for t, *_ in k))
    board = {}
    for t in times:
        v = [ret(s, t, 6) for s in data]
        v = [x for x in v if x is not None]
        if len(v) >= max(8, len(data) // 3):
            board[t] = (st.median(v), 100 * sum(1 for x in v if x > 0) / len(v))
    t_mid = times[len(times) // 2]

    # ── признаки и форварды
    rows = []
    for s, k in data.items():
        ar = arch[s]
        rng = [h - l for _, h, l, _ in k]
        for i in range(60, len(k) - 12 * BPH):
            t, h, l, c = k[i]
            d = datetime.fromtimestamp(t / 1000, timezone.utc)
            f = {}
            f["час"] = f"{(d.hour // 2) * 2:02d}–{(d.hour // 2) * 2 + 1:02d}"
            f["день"] = WD[d.weekday()]
            f["выходной"] = "да" if d.weekday() >= 5 else "нет"
            last_open = max((o for o in OPENS if (d.hour - o) % 24 <= 12), key=lambda o: -((d.hour - o) % 24))
            since = ((d.hour - last_open) % 24) + d.minute / 60
            f["после открытия"] = "0–1 ч" if since < 1 else "1–2 ч" if since < 2 else "2–4 ч" if since < 4 else "4+ ч"
            f["сессия"] = SESS_NAME[last_open]
            for hh in (2, 6, 12, 24):
                f[f"монета {hh}ч"] = band(ret(s, t, hh), -3, 3, big=8)
            w = [x[3] for x in k[i - 20:i]]
            m = sum(w) / 20
            sd = (sum((x - m) ** 2 for x in w) / 20) ** .5 or 1e-9
            z = (c - m) / sd
            f["z20"] = "<−2" if z < -2 else "<−1" if z < -1 else ">+2" if z > 2 else ">+1" if z > 1 else "0"
            # режим монеты: окно трёх суток и его длительность
            rb = 72 if BPH == 1 else 144        # трое суток в барах
            reg = regime([x[3] for x in k], i, rb)
            if reg:
                ln = regime_len([x[3] for x in k], i, rb, reg)
                f["режим монеты"] = reg
                f["режим длит."] = ("долгий" if ln >= rb // 2 else "недолгий") + " " + reg
            rn = st.median(rng[i - 24 * BPH:i]) or 1e-12
            f["размах бара"] = "×3+" if rng[i] / rn >= 3 else "×1.5+" if rng[i] / rn >= 1.5 else "обычный"
            # режим доски: та же мера по медианному ходу доски за трое суток
            if t in board and (t - 72 * 3600000) in board:
                seq = [board[t - h * 3600000][0] for h in range(72, -1, -6) if (t - h * 3600000) in board]
                if len(seq) >= 8:
                    net = seq[-1] - seq[0]
                    path = sum(abs(seq[q] - seq[q - 1]) for q in range(1, len(seq))) or 1e-9
                    e_ = abs(net) / path
                    f["режим доски"] = "флэт" if e_ < 0.25 else ("рост" if net > 0 else "слив")
            if t in board and (t - 4 * 3600000) in board:
                m6, up = board[t]
                m0, up0 = board[t - 4 * 3600000]
                f["доска 6ч"] = "↓" if m6 < -1 else "↑" if m6 > 1 else "ровно"
                f["растущих"] = "<35%" if up < 35 else ">65%" if up > 65 else "35–65%"
                f["доска за 4ч"] = "разворот ↓" if (m6 < m0 and up < up0 and m6 < 0) else "разворот ↑" if (m6 > m0 and up > up0 and m6 > 0) else "без"
            if btc_c and t in btc_c and (t - 12 * 3600000) in btc_c:
                b = (btc_c[t] / btc_c[t - 12 * 3600000] - 1) * 100
                f["биткоин 12ч"] = band(b, -0.7, 0.7)
            if t in ar:
                ot, oi24, fund, vol = ar[t]
                f["тип бара"] = ot
                seq = [ar.get(k[i - j][0], (None,))[0] for j in (2, 1, 0)]
                f["3 бара"] = ot if seq == [ot] * 3 and ot else "нет"
                f["интерес 24ч"] = band(oi24, -5, 5)
                f["фандинг"] = None if fund is None else ("−" if fund < -0.01 else "+" if fund > 0.02 else "0")
                vols = [ar.get(k[j][0], (None, None, None, 0))[3] for j in range(i - 48, i)]
                vols = [v for v in vols if v]
                if vols and vol:
                    vn = st.median(vols) or 1e-9
                    f["оборот бара"] = "×3+" if vol / vn >= 3 else "×1.5+" if vol / vn >= 1.5 else "обычный"
            fw = {hh: (k[i + int(hh * BPH)][3] / c - 1) * 100 for hh in (2, 6, 12)}
            rows.append((f, fw, t < t_mid))
    print(f"монет {len(data)} · баров-наблюдений {len(rows)} · признаков {len(set(kk for f, _, _ in rows for kk in f))}\n"
          + (" · источник: cq_v2/intraday, без запросов к бирже" if a.archive else ""))

    # ── контроль по часу
    ctrl = defaultdict(list)
    for f, fw, _ in rows:
        ctrl[f["час"]].append(fw[6])
    ctrl_med = {h: st.median(v) for h, v in ctrl.items()}

    # ── условия: одиночные и пары
    keys = sorted(set(kk for f, _, _ in rows for kk in f))
    conds = defaultdict(list)
    for f, fw, first in rows:
        items = [(kk, f[kk]) for kk in keys if f.get(kk) is not None]
        rel6 = fw[6] - ctrl_med[f["час"]]
        for it in items:
            conds[(it,)].append((fw, rel6, first))
        for pair in itertools.combinations(items, 2):
            conds[pair].append((fw, rel6, first))
    results = []
    for cond, v in conds.items():
        if len(v) < a.min:
            continue
        rel = [x[1] for x in v]
        e = st.median(rel)
        h1 = [x[1] for x in v if x[2]]
        h2 = [x[1] for x in v if not x[2]]
        if len(h1) < a.min // 4 or len(h2) < a.min // 4:
            continue
        e1, e2 = st.median(h1), st.median(h2)
        if abs(e) < SCAN_MIN_EDGE or (e1 > 0) != (e2 > 0) or (e > 0) != (e1 > 0):
            continue
        f6 = [x[0][6] for x in v]
        f2 = [x[0][2] for x in v]
        f12 = [x[0][12] for x in v]
        results.append((e, cond, len(v), st.median(f2), st.median(f6), st.median(f12), 100 * sum(1 for x in f6 if x >= 2) / len(v), 100 * sum(1 for x in f6 if x <= -2) / len(v), e1, e2))
    results.sort(key=lambda r: -abs(r[0]))
    longs = [r for r in results if r[0] > 0][:a.top]
    shorts = [r for r in results if r[0] < 0][:a.top]

    def show(title, lst, sign):
        print(f"── {title} (n ≥ {a.min}, край ≥ {SCAN_MIN_EDGE}% к контролю часа на 6 ч, знак в обеих половинах периода)")
        if not lst:
            print("   ничего не прошло отбор")
        for e, cond, n, m2, m6, m12, up2, dn2, e1, e2 in lst:
            name = " · ".join(f"{k}={v}" for k, v in cond)
            print(f"  {name:<62} n={n:>5} · край {e:+.2f}% (половины {e1:+.2f} / {e2:+.2f}) · ход 2ч {sign * m2:+.2f} · 6ч {sign * m6:+.2f} · 12ч {sign * m12:+.2f} · ≥+2% {(up2 if sign > 0 else dn2):3.0f}%")
    show("ЛОНГ — условия с положительным краем", longs, 1)
    print()
    show("ШОРТ — условия с отрицательным краем (ход показан со стороны шорта)", shorts, -1)
    if a.write:
        import time as _t
        out = {"at": _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime()), "days": a.days, "coins": len(data), "bars": len(rows), "min_n": a.min,
               "windows": [{"side": "лонг" if e > 0 else "шорт", "cond": dict(cond), "n": n, "edge6": round(e, 2), "half1": round(e1, 2), "half2": round(e2, 2),
                            "move2": round(m2, 2), "move6": round(m6, 2), "move12": round(m12, 2), "hit": round(up2 if e > 0 else dn2)}
                           for e, cond, n, m2, m6, m12, up2, dn2, e1, e2 in longs + shorts]}
        pth = BASE_DIR / "output" / "windows.json"
        pth.parent.mkdir(parents=True, exist_ok=True)
        tmp = pth.with_suffix(".tmp")
        tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(pth)
        print(f"\nокна записаны: {pth} · {len(out['windows'])} строк")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
