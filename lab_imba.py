#!/usr/bin/env python3
"""ПРИНЦИП IMBA НА НАШЕМ АРХИВЕ (24.09, владелец: «мне нужен принцип, по которому определяются лонг или шорт,
прогнать его на нашем архиве intraday и посмотреть, насколько точно будет попадание, сделки минимум +5%»).

Принцип — из открытого кода автора ([imba]lance algo, IMBA_TRADER; перенос на ThinkScript):
  • коридор: максимум максимумов и минимум минимумов за N последних баров (текущий бар входит);
  • верхний уровень = максимум − 0.236·коридор, нижний = минимум + 0.236·коридор;
  • ЛОНГ — закрытие бара на верхнем уровне или выше, ШОРТ — на нижнем или ниже; между ними направление держится.
N = чувствительность × 10 часовых баров. Сверено с экраном владельца 24.09: зелёная линия IMBA на ONE (1h,
чувствительность 18) стояла на 0.0029385 = середина между 0.00523 (21.09) и 0.000647 (16.09) — коридор 180 часов.

Бары: получасовки cq_v2/intraday + cq_v2/archive/intraday (дни .jsonl.gz), склеены в часовые, как на графике.
Вход — по открытию часа ПОСЛЕ сигнального (сигнал известен только на закрытии). Сделка живёт до обратного сигнала.

Мерки на каждый сигнал:
  • попадание — цена дошла до +TARGET в сторону сигнала раньше обратного сигнала;
  • сколько цена ушла ПРОТИВ до попадания (на баре попадания его худшая сторона тоже считается — порядок внутри
    часа неизвестен, спорное против нас); свой стоп не вводится;
  • итог системы как есть — выход по закрытию бара с обратным сигналом, минус комиссия FEE за круг;
  • случайный вход — та же монета, та же сторона, та же длина сделки, случайный час; RANDOM_K проб на сигнал.
    Без этого процент попаданий ничего не значит: на мелочи +5% за сутки бывает само собой.

    python3 lab_imba.py                  # N = 180, сводка
    python3 lab_imba.py --n 18           # другой коридор
    python3 lab_imba.py --only ONE       # сигналы одной монеты построчно (сверка с графиком)
    python3 lab_imba.py --days           # плюс разбивка по дням сигнала
Пишет output/lab_imba_<N>.csv — все сигналы для разбора руками. К бирже не ходит.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import random
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
try:
    from core_config import SIGHT_FEE as FEE
except ImportError:
    FEE = 0.001                 # круг: вход и выход, как SIGHT_FEE

LIVE_DIR = BASE_DIR / "cq_v2" / "intraday"
ARCH_DIR = BASE_DIR / "cq_v2" / "archive" / "intraday"
OUT = BASE_DIR / "output"
FIB = 0.236                     # уровень из кода IMBA
TARGET = 0.05                   # порог владельца: «сделки минимум +5%»
N_DEFAULT = 180                 # чувствительность 18 × 10, сверено с экраном (см. шапку)
RANDOM_K = 20                   # проб случайного входа на один сигнал; зерно постоянное — прогон повторяем
HOUR = 3600


def _ts(iso: str) -> int:
    return int(datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())


def _day(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%m-%d")


def load_30m() -> dict[str, dict[int, tuple]]:
    """{монета: {время открытия: (o, h, l, c)}} — живые файлы поверх архива, дубли по времени схлопнуты"""
    out: dict[str, dict[int, tuple]] = defaultdict(dict)

    def put(r: dict) -> None:
        try:
            t = _ts(r["candle"])
            c = float(r["px"])
            h, l = float(r.get("h") or c), float(r.get("l") or c)
            o = float(r["o"]) if r.get("o") else None
        except (KeyError, TypeError, ValueError):
            return
        out[r["sym"]][t] = (o, h, l, c)

    for p in sorted(ARCH_DIR.glob("*/*.jsonl.gz")):
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            for line in fh:
                try:
                    put(json.loads(line))
                except ValueError:
                    continue
    for p in sorted(LIVE_DIR.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                put(json.loads(line))
            except ValueError:
                continue
    return out


def to_hours(b30: dict[int, tuple]) -> list[tuple]:
    """[(час, o, h, l, c)] — только полные часы (обе получасовки на месте), иначе дыра в коридоре"""
    hrs = []
    for t in sorted(b30):
        if t % HOUR:
            continue
        a, b = b30.get(t), b30.get(t + 1800)
        if not a or not b:
            continue
        o = a[0] if a[0] is not None else a[3]
        hrs.append((t, o, max(a[1], b[1]), min(a[2], b[2]), b[3]))
    return hrs


def signals(hrs: list[tuple], n: int) -> list[tuple[int, int]]:
    """[(индекс бара, сторона)] — смены направления по принципу IMBA"""
    out, trend = [], 0
    for i in range(n - 1, len(hrs)):
        win = hrs[i - n + 1:i + 1]
        hh, ll = max(x[2] for x in win), min(x[3] for x in win)
        rng = hh - ll
        if rng <= 0:
            continue
        c = hrs[i][4]
        up, dn = hh - FIB * rng, ll + FIB * rng
        if c >= up and trend != 1:
            trend = 1
            out.append((i, 1))
        elif c <= dn and trend != -1:
            trend = -1
            out.append((i, -1))
    return out


def walk(hrs: list[tuple], i0: int, i1: int, side: int, e: float) -> dict:
    """путь от бара i0 (вход по его открытию e) до бара i1 включительно: попадание, против до него, лучший ход"""
    tgt = e * (1 + side * TARGET)
    worst, best, hit_at = 0.0, 0.0, None
    for j in range(i0, i1 + 1):
        _, _, h, l, _ = hrs[j]
        adv = side * ((l if side > 0 else h) / e - 1)
        fav = side * ((h if side > 0 else l) / e - 1)
        worst, best = min(worst, adv), max(best, fav)
        if (h >= tgt) if side > 0 else (l <= tgt):
            hit_at = j
            break
    if hit_at is not None:                       # лучший ход — по всему пути, не только до попадания
        for j in range(hit_at + 1, i1 + 1):
            _, _, h, l, _ = hrs[j]
            best = max(best, side * ((h if side > 0 else l) / e - 1))
    return {"hit": hit_at is not None, "bars_to_hit": None if hit_at is None else hit_at - i0 + 1,
            "mae": worst, "mfe": best}


def run(data: dict[str, list[tuple]], n: int, only: str | None) -> tuple[list[dict], list[dict]]:
    rnd = random.Random(24)
    rows, base = [], []
    for sym, hrs in sorted(data.items()):
        if only and sym.replace("USDT", "") != only.upper().replace("USDT", ""):
            continue
        sg = signals(hrs, n)
        for k, (i, side) in enumerate(sg):
            i0 = i + 1
            if i0 >= len(hrs):
                continue
            closed = k + 1 < len(sg)
            i1 = sg[k + 1][0] if closed else len(hrs) - 1
            if i1 < i0:
                continue
            e = hrs[i0][1]
            w = walk(hrs, i0, i1, side, e)
            res = side * (hrs[i1][4] / e - 1) - FEE if closed else None
            rows.append(dict(sym=sym.replace("USDT", ""), side=side, t=hrs[i][0], px_in=e, bars=i1 - i0 + 1,
                             closed=closed, res=res, **w))
            span = i1 - i0 + 1                   # случайный вход той же длины на той же монете
            if len(hrs) - span > n:
                for _ in range(RANDOM_K):
                    j0 = rnd.randrange(n, len(hrs) - span + 1)
                    base.append(dict(side=side, **walk(hrs, j0, j0 + span - 1, side, hrs[j0][1])))
    return rows, base


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def report(rows: list[dict], base: list[dict], title: str) -> None:
    if not rows:
        print(f"  {title}: сигналов нет")
        return
    hit = [r for r in rows if r["hit"]]
    miss_closed = [r for r in rows if not r["hit"] and r["closed"]]
    open_miss = [r for r in rows if not r["hit"] and not r["closed"]]
    decided = len(hit) + len(miss_closed)
    acc = len(hit) / decided * 100 if decided else 0
    b_acc = sum(1 for b in base if b["hit"]) / len(base) * 100 if base else 0
    print(f"  {title}: сигналов {len(rows)} · решённых {decided} · открытых без попадания {len(open_miss)}")
    print(f"    попадание +{TARGET * 100:.0f}% до обратного сигнала: {acc:.0f}%   · случайный вход той же длины: {b_acc:.0f}%")
    if hit:
        mae = [r["mae"] for r in hit]
        bt = [r["bars_to_hit"] for r in hit]
        print(f"    у попавших против до попадания: медиана {_pct(st.median(mae))} · худший {_pct(min(mae))}"
              f" · часов до попадания: медиана {st.median(bt):.0f}")
    if miss_closed:
        print(f"    у промахов лучший ход: медиана {_pct(st.median([r['mfe'] for r in miss_closed]))}"
              f" · против: медиана {_pct(st.median([r['mae'] for r in miss_closed]))}")
    res = [r["res"] for r in rows if r["res"] is not None]
    if res:
        print(f"    система как есть (до обратного сигнала, комиссия {FEE * 100:.1f}%): сделок {len(res)} · в плюсе "
              f"{sum(1 for x in res if x > 0) / len(res) * 100:.0f}% · средняя {_pct(st.mean(res))} · медиана "
              f"{_pct(st.median(res))} · худшая {_pct(min(res))} · лучшая {_pct(max(res))} · сумма {_pct(sum(res))}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_DEFAULT)
    ap.add_argument("--only")
    ap.add_argument("--days", action="store_true")
    a = ap.parse_args()
    raw = load_30m()
    data = {s: to_hours(b) for s, b in raw.items()}
    data = {s: h for s, h in data.items() if len(h) > a.n}
    t0 = min(h[0][0] for h in data.values())
    t1 = max(h[-1][0] for h in data.values())
    rows, base = run(data, a.n, a.only)
    print(f"IMBA · коридор {a.n} ч · уровень {FIB} · цель +{TARGET * 100:.0f}% · монет {len(data)} · "
          f"часы {datetime.fromtimestamp(t0, timezone.utc):%d.%m %H:%M} — {datetime.fromtimestamp(t1, timezone.utc):%d.%m %H:%M} UTC"
          f" · первые {a.n} ч каждой монеты уходят на коридор")
    report(rows, base, "все")
    for side, nm in ((1, "лонги"), (-1, "шорты")):
        report([r for r in rows if r["side"] == side], [b for b in base if b["side"] == side], nm)
    if a.days:
        by = defaultdict(list)
        for r in rows:
            by[_day(r["t"])].append(r)
        for d in sorted(by):
            v = by[d]
            dec = [r for r in v if r["hit"] or r["closed"]]
            acc = sum(1 for r in dec if r["hit"]) / len(dec) * 100 if dec else 0
            print(f"    {d}: сигналов {len(v):3d} · лонгов {sum(1 for r in v if r['side'] > 0):3d} · попадание {acc:3.0f}%")
    if a.only:
        for r in rows:
            print(f"    {datetime.fromtimestamp(r['t'], timezone.utc):%d.%m %H:%M} {'ЛОНГ' if r['side'] > 0 else 'ШОРТ'}"
                  f" вход {r['px_in']:.6g} · часов {r['bars']} · {'попал' if r['hit'] else 'мимо '} · против {_pct(r['mae'])}"
                  f" · лучший {_pct(r['mfe'])} · итог {'открыта' if r['res'] is None else _pct(r['res'])}")
    OUT.mkdir(exist_ok=True)
    p = OUT / f"lab_imba_{a.n}{'_' + a.only.lower() if a.only else ''}.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["монета", "сторона", "сигнал UTC", "вход", "часов", "закрыта", "попал", "часов до попадания",
                    "против %", "лучший %", "итог %"])
        for r in rows:
            w.writerow([r["sym"], "лонг" if r["side"] > 0 else "шорт",
                        datetime.fromtimestamp(r["t"], timezone.utc).strftime("%Y-%m-%d %H:%M"), r["px_in"], r["bars"],
                        r["closed"], r["hit"], r["bars_to_hit"] or "", round(r["mae"] * 100, 2), round(r["mfe"] * 100, 2),
                        "" if r["res"] is None else round(r["res"] * 100, 2)])
    print(f"  сигналы: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
