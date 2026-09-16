#!/usr/bin/env python3
"""ЗАКОНОМЕРНОСТЬ И АНОМАЛИИ ПО ДАТАМ (16.09; цикл владельца: «прогнать всё, дать разбор — что и в какие даты
закономерность, а что аномалия; я нахожу фон; прогоняем снова; так слой за слоем: дни, сессии, стыки, биткоин,
новости»).

Берёт правило или окно и отдаёт не сумму, а КАЖДУЮ ДАТУ: результат правила в этот день и то, что машина сама
знает про день — ход биткоина за сутки, медиана доски за сутки, доля растущих, сколько спайков (+8%/2 ч) было по
доске, день недели, и запись владельца из fon.json, если есть. Внизу — даты-аномалии (правило сломалось: день в
нижних 10%) и даты-удачи (верхние 10%), сгруппированные по тому, что у них общего.
Правила: спайк (шорт +8%/2ч), провал (лонг −8%/2ч), z-шорт, окно (`--window "чт,Нью-Йорк,лонг"` — одна монета на
окно, как в lab_daily). Держание HOLD ч, без стопа, потолок CAP, комиссия 0.1%.
fon.json — файл владельца: {"2026-08-26": "минутки ФРС, лонги вынесли", "2026-05-20": "взлом X"}; строки читаются как
ещё один признак: даты с записью выделяются, и считается, объясняет ли запись аномалии.
Источник — hourly/*.json. `python3 lab_anomaly.py --rule спайк --days 180`, `--window "чт,Нью-Йорк,лонг"`.
"""
from __future__ import annotations

import argparse
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

FEE = 0.001
H = 3600000
OPENS = {"Сидней": 21, "Токио": 0, "Лондон": 7, "Нью-Йорк": 13}
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def load_hourly(days: int) -> dict:
    data = {}
    for p in (BASE_DIR / "hourly").glob("*.json"):
        try:
            arr = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        d = {int(b["t"]): float(b["c"]) for b in arr if isinstance(b, dict) and b.get("t") and b.get("c")}
        if len(d) < 200:
            continue
        keys = sorted(d)[-(days * 24 + 48):]
        data[p.stem.upper() + "USDT"] = {k: d[k] for k in keys}
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule", default="спайк", help="спайк | провал | z-шорт | окно")
    ap.add_argument("--window", default=None, help="для правила «окно»: день,сессия,сторона[,смещение ч] — например \"чт,Нью-Йорк,лонг,2\"")
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--hold", type=int, default=6)
    ap.add_argument("--cap", type=float, default=0.25)
    a = ap.parse_args()
    data = load_hourly(a.days)
    btc = data.pop("BTCUSDT", None) or {}
    if not data:
        print("hourly/*.json пусто")
        return 0
    fon = {}
    for p in (BASE_DIR / "fon.json", BASE_DIR / "output" / "fon.json"):
        if p.exists():
            try:
                fon = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                pass
            break
    times = sorted(set(t for d in data.values() for t in d))

    def r(d, t0, t1):
        return (d[t1] / d[t0] - 1) if (t0 in d and t1 in d) else None

    # ── фон дня (машина знает сама)
    day_bg = {}
    days = sorted(set(datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d") for t in times))
    for day in days:
        t0 = int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
        t1 = t0 + 24 * H
        moves = [r(d, t0, t1) for d in data.values()]
        moves = [x for x in moves if x is not None]
        spikes = 0
        for d in data.values():
            for t in range(t0, t1, H):
                if t in d and (t - 2 * H) in d and d[t] / d[t - 2 * H] - 1 >= 0.08:
                    spikes += 1
        moves_pre = [r(d, t0 - 24 * H, t0) for d in data.values()]
        moves_pre = [x for x in moves_pre if x is not None]
        day_bg[day] = {
            "биткоин": (r(btc, t0, t1) * 100 if btc and r(btc, t0, t1) is not None else None),
            "доска": (st.median(moves) * 100 if moves else None),
            "BTC до": (r(btc, t0 - 24 * H, t0) * 100 if btc and r(btc, t0 - 24 * H, t0) is not None else None),
            "доска до": (st.median(moves_pre) * 100 if moves_pre else None),
            "растущих": (100 * sum(1 for x in moves if x > 0) / len(moves) if moves else None),
            "спайков": spikes,
            "режим": None,
            "день": WD[datetime.strptime(day, "%Y-%m-%d").weekday()],
            "фон": fon.get(day),
        }

    # режим доски на начало каждого дня: трое суток, |ход| / путь по медиане доски
    for day in days:
        t0 = int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
        seq = []
        for h in range(72, -1, -6):
            tt = t0 - h * H
            mv = [(d[tt] / d[tt - 24 * H] - 1) for d in data.values() if tt in d and (tt - 24 * H) in d]
            if len(mv) >= 8:
                seq.append(st.median(mv))
        if len(seq) >= 8:
            net = seq[-1] - seq[0]
            path = sum(abs(seq[q] - seq[q - 1]) for q in range(1, len(seq))) or 1e-9
            day_bg[day]["режим"] = "флэт" if abs(net) / path < 0.25 else ("рост" if net > 0 else "слив")

    # ── сделки правила
    trades = []      # (t, sym, res)

    def hold_res(d, te, side):
        e = d[te]
        for k in range(1, a.hold + 1):
            tk = te + k * H
            if tk not in d:
                return None
            cur = side * (d[tk] / e - 1)
            if cur <= -a.cap:
                return cur - FEE
        return side * (d[te + a.hold * H] / e - 1) - FEE

    if a.rule in ("спайк", "провал", "z-шорт"):
        for sym, d in data.items():
            ks = sorted(d)
            last = -1
            for i in range(24, len(ks) - a.hold - 1):
                if i <= last:
                    continue
                t = ks[i]
                r2 = d[t] / d[ks[i - 2]] - 1
                side = None
                if a.rule == "спайк" and r2 >= 0.08:
                    side = -1
                elif a.rule == "провал" and r2 <= -0.08:
                    side = 1
                elif a.rule == "z-шорт" and i >= 20:
                    w = [d[ks[j]] for j in range(i - 20, i)]
                    m = sum(w) / 20
                    sd = (sum((x - m) ** 2 for x in w) / 20) ** .5 or 1e-9
                    if (d[t] - m) / sd > 2:
                        side = -1
                if side is None:
                    continue
                res = hold_res(d, t, side)
                if res is None:
                    continue
                trades.append((t, sym, res))
                last = i + a.hold
    elif a.rule == "окно" and a.window:
        parts = [x.strip() for x in a.window.split(",")]
        wd_s, sess, side_s = parts[:3]
        off = int(parts[3]) if len(parts) > 3 else 0
        wd = WD.index(wd_s)
        side = 1 if side_s.startswith("лонг") else -1
        hour = OPENS[sess]
        for t0_ in times:
            dt = datetime.fromtimestamp(t0_ / 1000, timezone.utc)
            if dt.weekday() != wd or dt.hour != hour or dt.minute != 0:
                continue
            t = t0_ + off * H
            cands = []
            for sym, d in data.items():
                r6 = r(d, t - 6 * H, t)
                if r6 is None:
                    continue
                if side > 0 and -0.25 <= r6 < 0:
                    cands.append((sym, r6))
                if side < 0 and 0 < r6 <= 0.40:
                    cands.append((sym, r6))
            if not cands:
                continue
            sym, _ = min(cands, key=lambda c: c[1]) if side > 0 else max(cands, key=lambda c: c[1])
            res = hold_res(data[sym], t, side)
            if res is not None:
                trades.append((t, sym, res))
    if not trades:
        print("сделок нет")
        return 0

    # ── по датам
    per_day = defaultdict(list)
    for t, sym, res in trades:
        per_day[datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d")].append((sym, res))
    rows = []
    for day, v in sorted(per_day.items()):
        tot = sum(x[1] for x in v) * 100
        rows.append((day, len(v), tot, 100 * sum(1 for x in v if x[1] > 0) / len(v), day_bg.get(day, {})))
    tots = sorted(x[2] for x in rows)
    lo_cut, hi_cut = tots[int(len(tots) * .1)], tots[int(len(tots) * .9)]
    all_res = [res for _, _, res in trades]
    print(f"правило: {a.rule}{(' ' + a.window) if a.window else ''} · монет {len(data)} · дней {len(rows)} · сделок {len(trades)} · попаданий {100 * sum(1 for x in all_res if x > 0) / len(all_res):.0f}% · средняя {100 * st.mean(all_res):+.2f}% · сумма {100 * sum(all_res):+.1f}% (на сделку размера 1)\n")
    def f_(x, fmt):
        return "   —" if x is None else format(x, fmt)
    print("── ПО ДАТАМ (сумма % за день · сделок · попаданий | ДО входа: BTC и доска за предыдущие сутки | в день: BTC · доска · растущих · спайков · день · фон владельца)")
    for day, n, tot, hit, bg in rows:
        mark = "  АНОМАЛИЯ" if tot <= lo_cut else ("  удача" if tot >= hi_cut else "")
        print(f"  {day}  {tot:+6.1f}%  n={n:>3}  {hit:3.0f}%  | до: BTC {f_(bg.get('BTC до'), '+.1f'):>5}% доска {f_(bg.get('доска до'), '+.1f'):>5}% | день: BTC {f_(bg.get('биткоин'), '+.1f'):>5}% доска {f_(bg.get('доска'), '+.1f'):>5}% растущих {f_(bg.get('растущих'), '.0f'):>3}% спайков {bg.get('спайков', 0):>3} {bg.get('день', '')} {str(bg.get('режим') or '—'):<5}{mark}" + (f"  · {bg['фон']}" if bg.get("фон") else ""))

    def group(name, sel):
        if not sel:
            return
        print(f"\n── {name} ({len(sel)} дней): что у них общего")
        bt = [x[4]["биткоин"] for x in sel if x[4].get("биткоин") is not None]
        bd = [x[4]["доска"] for x in sel if x[4].get("доска") is not None]
        sp = [x[4]["спайков"] for x in sel]
        wds = defaultdict(int)
        for x in sel:
            wds[x[4].get("день")] += 1
        fons = [x[4]["фон"] for x in sel if x[4].get("фон")]
        bt0 = [x[4]["BTC до"] for x in sel if x[4].get("BTC до") is not None]
        bd0 = [x[4]["доска до"] for x in sel if x[4].get("доска до") is not None]
        print(f"   ДО входа — биткоин за предыдущие сутки: медиана {st.median(bt0):+.1f}%, доска {st.median(bd0):+.1f}%" if bt0 and bd0 else "   до входа: данных нет")
        print(f"   В ДЕНЬ — биткоин: медиана {st.median(bt):+.1f}%, доска {st.median(bd):+.1f}%" if bt and bd else "")
        print(f"   спайков за день: медиана {st.median(sp):.0f} (по всем дням {st.median([x[4]['спайков'] for x in rows]):.0f})")
        print(f"   дни недели: " + ", ".join(f"{k} {v}" for k, v in sorted(wds.items(), key=lambda kv: -kv[1])))
        rg = defaultdict(int)
        for x in sel:
            rg[x[4].get("режим") or "—"] += 1
        rg_all = defaultdict(int)
        for x in rows:
            rg_all[x[4].get("режим") or "—"] += 1
        print("   режим доски (трое суток): " + ", ".join(f"{k} {n_} из {rg_all[k]}" for k, n_ in sorted(rg.items(), key=lambda kv: -kv[1])))
        print(f"   с фоном владельца: {len(fons)} из {len(sel)}" + (" — " + "; ".join(fons[:6]) if fons else ""))
    group("АНОМАЛИИ — правило сломалось", [x for x in rows if x[2] <= lo_cut])
    group("УДАЧИ — сработало лучше обычного", [x for x in rows if x[2] >= hi_cut])
    if fon:
        with_f = [x[2] for x in rows if x[4].get("фон")]
        no_f = [x[2] for x in rows if not x[4].get("фон")]
        if with_f and no_f:
            print(f"\n── ФОН ВЛАДЕЛЬЦА КАК ПРИЗНАК: дни с записью {len(with_f)} — медиана {st.median(with_f):+.1f}% в день; без записи {len(no_f)} — {st.median(no_f):+.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
