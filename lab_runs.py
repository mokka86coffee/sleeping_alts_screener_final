#!/usr/bin/env python3
"""ЧТО ВЫЖАТЬ ИЗ ТОГО, ЧТО УЖЕ ЛЕЖИТ (16.09; владелец: «выборка почти за месяц — что росло и в какие часы, по
сессиям и дням недели, медиана и куча всего; логика для сделок от 30 минут до нескольких часов, в шорты и лонги,
не растягивая на недели и не ища иксы»).

Источник — самый первый журнал проекта: output/runs/<дата>.jsonl.gz, с 19.08, строка на кандидата за прогон:
sym, t, price, vol_1h/4h/1d, rvol_1h, atr_pct, obv, funding, oi_usd, oi_x, oi_held, up_low, ch_24h, vi_p, vi_m,
vx_dir, vx_strength, buy_share, delta_slope, rel_vol, score (+ что появилось позже — берётся, если есть).
Плюс output/runs/daily/run-<дата>.json — ширина доски по дням (tradable / strong / good) как фон дня.

Форвард по цене — из следующих снимков той же монеты: +1, +2, +4, +6, +12, +24 ч (ближайший снимок не дальше
чем на четверть окна). Контроль — медиана форварда всех снимков того же часа UTC.
Срезы: час (по 2), день недели, выходной, сессия (последняя открывшаяся) и часов от её открытия, и все признаки
снимка полосами: rvol_1h, atr_pct, фандинг, oi_x, oi_held, up_low, ch_24h, разрыв вортекса и vx_dir, buy_share,
наклон дельты, rel_vol, score, ширина доски дня. Одиночные и пары. Отбор: n ≥ --min, край ≥ --edge к контролю,
знак края одинаков в обеих половинах периода. Вывод: верхние окна лонг и шорт на горизонте --h часов, плюс таблица
«день недели × час» по всей выборке и по сессиям.
Ничего не пишет (кроме --write → output/windows_runs.json). `python3 lab_runs.py --h 4`, `--h 2`, `--min 150`.
"""
from __future__ import annotations

import argparse
import glob
import gzip
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

OPENS = [21, 0, 7, 13]
SESS = {21: "Сидней", 0: "Токио", 7: "Лондон", 13: "Нью-Йорк"}
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
H_ALL = (1, 2, 4, 6, 12, 24)


def load_runs() -> list[dict]:
    """output/runs/*.jsonl.gz и output/pulse_archive/*.jsonl.gz — один формат строки (sym, t, price, …); пульс шире:
    если там вся доска, форвард и контроль считаются по всем монетам. Дубли (sym, t) схлопываются."""
    rows = []
    seen = set()
    # папки ищутся по всему проекту (16.09: у владельца pulse_archive лежит не в output/): любой *.jsonl.gz, кроме
    # venv и .git; какие папки нашлись — печатается
    paths = []
    for p in BASE_DIR.rglob("*.jsonl.gz"):
        sp = str(p)
        if "/venv" in sp or "/.git" in sp or "/node_modules" in sp:
            continue
        paths.append(str(p))
    paths.sort()
    print("файлы: " + ", ".join(sorted({str(Path(p).parent.relative_to(BASE_DIR)) for p in paths})) + f" · {len(paths)} шт.")
    for p in paths:
        try:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if r.get("sym") and r.get("t") and r.get("price"):
                        key = (r["sym"], int(r["t"]))
                        if key in seen:
                            continue
                        seen.add(key)
                        rows.append(r)
        except OSError:
            continue
    return rows


def load_daily() -> dict:
    out = {}
    for p in glob.glob(str(BASE_DIR / "output" / "runs" / "daily" / "run-*.json")):
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        day = Path(p).stem.replace("run-", "")
        c = d.get("counts") or {}
        out[f"{day[:4]}-{day[4:6]}-{day[6:8]}"] = c
    return out


def band(x, lo, hi, big=None, labels=("↓", "ровно", "↑")):
    if x is None:
        return None
    if big is not None and x <= -big:
        return "сильно " + labels[0]
    if big is not None and x >= big:
        return "сильно " + labels[2]
    return labels[0] if x < lo else labels[2] if x > hi else labels[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--h", type=int, default=4, help="горизонт для отбора, часов")
    ap.add_argument("--min", type=int, default=150)
    ap.add_argument("--edge", type=float, default=0.5)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    rows = load_runs()
    daily = load_daily()
    if not rows:
        print("output/runs/*.jsonl.gz пусто")
        return 0
    by = defaultdict(list)
    for r in rows:
        by[r["sym"]].append((int(r["t"]), float(r["price"])))
    for s in by:
        by[s].sort()
    import bisect

    def fwd(sym, t, h):
        arr = by[sym]
        tt = t + h * 3600
        i = bisect.bisect_left(arr, (tt, 0.0))
        if i < len(arr) and arr[i][0] - tt <= h * 900:
            p0 = next((p for tt0, p in arr if tt0 == t), None)
            return (arr[i][1] / p0 - 1) * 100 if p0 else None
        return None

    ts = sorted(set(int(r["t"]) for r in rows))
    t_mid = ts[len(ts) // 2]
    days = sorted(set(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d") for t in ts))
    print(f"снимков {len(ts)} · строк {len(rows)} · монет {len(by)} · дней {len(days)} ({days[0]} → {days[-1]}) · дневных сводок {len(daily)}\n")

    # ── признаки
    obs = []
    for r in rows:
        t = int(r["t"])
        d = datetime.fromtimestamp(t, timezone.utc)
        f = {}
        f["час"] = f"{(d.hour // 2) * 2:02d}–{(d.hour // 2) * 2 + 1:02d}"
        f["день"] = WD[d.weekday()]
        f["выходной"] = "да" if d.weekday() >= 5 else "нет"
        last_open = max(OPENS, key=lambda o: -((d.hour - o) % 24))
        since = ((d.hour - last_open) % 24) + d.minute / 60
        f["сессия"] = SESS[last_open]
        f["после открытия"] = "0–1 ч" if since < 1 else "1–2 ч" if since < 2 else "2–4 ч" if since < 4 else "4+ ч"
        g = r.get
        f["rvol_1h"] = band(g("rvol_1h"), 0.7, 1.5, big=None, labels=("тихо", "норма", "×1.5+")) if g("rvol_1h") is not None else None
        if g("rvol_1h") is not None and g("rvol_1h") >= 3:
            f["rvol_1h"] = "×3+"
        f["atr"] = band(g("atr_pct"), 3, 8, labels=("<3%", "3–8%", ">8%"))
        fu = g("funding")
        f["фандинг"] = None if fu is None else ("−" if fu < -0.005 else "+" if fu > 0.02 else "0")
        f["oi_x"] = band(g("oi_x"), 0.9, 1.5, labels=("<0.9", "0.9–1.5", ">1.5")) if g("oi_x") is not None else None
        f["oi_held"] = band(g("oi_held"), 60, 95, labels=("<60", "60–95", "95+")) if g("oi_held") is not None else None
        f["up_low"] = band(g("up_low"), 10, 40, labels=("<10%", "10–40%", ">40%")) if g("up_low") is not None else None
        f["ch_24h"] = band(g("ch_24h"), -3, 3, big=10)
        if g("vi_p") is not None and g("vi_m") is not None:
            gap = g("vi_p") - g("vi_m")
            f["вортекс"] = "покупатели сильно" if gap > 0.25 else "покупатели" if gap > 0.05 else "продавцы сильно" if gap < -0.25 else "продавцы" if gap < -0.05 else "ровно"
        if g("vx_dir"):
            f["vx_dir"] = str(g("vx_dir"))
        f["buy_share"] = band(g("buy_share"), 0.47, 0.53, labels=("продают", "ровно", "покупают")) if g("buy_share") is not None else None
        f["дельта"] = band(g("delta_slope"), -0.002, 0.002, labels=("↓", "ровно", "↑")) if g("delta_slope") is not None else None
        f["rel_vol"] = band(g("rel_vol"), 2, 5, labels=("<2", "2–5", "5+")) if g("rel_vol") is not None else None
        f["score"] = band(g("score"), 60, 80, labels=("<60", "60–80", "80+")) if g("score") is not None else None
        c = daily.get(d.strftime("%Y-%m-%d")) or {}
        if c.get("tradable") is not None:
            f["доска (tradable)"] = band(c["tradable"], 50, 90, labels=("узкая", "средняя", "широкая"))
        fw = {h: fwd(r["sym"], t, h) for h in H_ALL}
        obs.append((f, fw, t < t_mid, r["sym"], t))
    H = a.h
    valid = [o for o in obs if o[1].get(H) is not None]
    print(f"наблюдений с форвардом {H} ч: {len(valid)}\n")
    ctrl = defaultdict(list)
    for f, fw, _, _, _ in valid:
        ctrl[f["час"]].append(fw[H])
    ctrl_med = {k: st.median(v) for k, v in ctrl.items()}

    # ── 1. что росло и в какие часы: день недели × час, по всей выборке
    print(f"── 1. ДЕНЬ НЕДЕЛИ × ЧАС UTC → медиана хода за {H} ч (%), n в скобках")
    cell = defaultdict(list)
    for f, fw, _, _, t in valid:
        d = datetime.fromtimestamp(t, timezone.utc)
        cell[(d.weekday(), (d.hour // 2) * 2)].append(fw[H])
    print("      " + " ".join(f"{h:>7}" for h in range(0, 24, 2)))
    for wd in range(7):
        line = []
        for h in range(0, 24, 2):
            v = cell.get((wd, h), [])
            line.append(f"{st.median(v):+5.1f}" if len(v) >= 15 else "    ·")
        print(f"  {WD[wd]}  " + " ".join(f"{x:>7}" for x in line))
    print("\n── по сессиям и часам после открытия:")
    sess_cell = defaultdict(list)
    for f, fw, _, _, _ in valid:
        sess_cell[(f["сессия"], f["после открытия"])].append(fw[H])
    for s_ in SESS.values():
        parts = [f"{k[1]}: {st.median(v):+.2f}% ({100 * sum(1 for x in v if x > 0) / len(v):.0f}%↑, n={len(v)})" for k, v in sorted(sess_cell.items()) if k[0] == s_ and len(v) >= 15]
        print(f"  {s_:<9} " + (" · ".join(parts) if parts else "—"))

    # ── 2. перебор условий
    keys = sorted(set(k for f, *_ in valid for k in f))
    conds = defaultdict(list)
    for f, fw, first, sym, t in valid:
        items = [(k, f[k]) for k in keys if f.get(k) is not None]
        rel = fw[H] - ctrl_med[f["час"]]
        for it in items:
            conds[(it,)].append((fw[H], rel, first))
        for pair in itertools.combinations(items, 2):
            conds[pair].append((fw[H], rel, first))
    res = []
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
        if abs(e) < a.edge or (e1 > 0) != (e2 > 0) or (e > 0) != (e1 > 0):
            continue
        raw = [x[0] for x in v]
        res.append((e, cond, len(v), st.median(raw), 100 * sum(1 for x in raw if x >= 2) / len(v), 100 * sum(1 for x in raw if x <= -2) / len(v), e1, e2))
    res.sort(key=lambda r: -abs(r[0]))
    longs = [r for r in res if r[0] > 0][:a.top]
    shorts = [r for r in res if r[0] < 0][:a.top]

    def show(title, lst, sign):
        print(f"\n── {title} · горизонт {H} ч · n ≥ {a.min} · край ≥ {a.edge}% · знак в обеих половинах")
        if not lst:
            print("   ничего не прошло")
        for e, cond, n, m, up2, dn2, e1, e2 in lst:
            name = " · ".join(f"{k}={v}" for k, v in cond)
            print(f"  {name:<58} n={n:>5} · край {e:+.2f}% ({e1:+.2f} / {e2:+.2f}) · ход {sign * m:+.2f}% · ≥2% {(up2 if sign > 0 else dn2):3.0f}%")
    show("ЛОНГ", longs, 1)
    show("ШОРТ (ход со стороны шорта)", shorts, -1)
    if a.write:
        import time as _t
        out = {"at": _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime()), "h": H, "n_obs": len(valid), "days": days,
               "windows": [{"side": "лонг" if e > 0 else "шорт", "cond": dict(cond), "n": n, "edge": round(e, 2), "half1": round(e1, 2), "half2": round(e2, 2), "move": round(m, 2), "hit": round(up2 if e > 0 else dn2)}
                           for e, cond, n, m, up2, dn2, e1, e2 in longs + shorts]}
        pth = BASE_DIR / "output" / "windows_runs.json"
        pth.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nзаписано: {pth}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
