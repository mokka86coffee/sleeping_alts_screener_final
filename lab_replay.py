#!/usr/bin/env python3
"""ПЕРЕИГРОВКА КНИГ ПО ТРЁХМИНУТКАМ (23.09, владелец: «бот закрывает сделки раз в полчаса — закрывать на +5–10%
и брать снова, когда цена вернётся; запроси трёхминутки с биржи и прогони все стратегии»).

Берёт НАСТОЯЩИЕ входы бумажных книг (output/paper_*.jsonl, kind=entry) и проигрывает каждый по трёхминуткам
cq_v2/tick/<монета>.jsonl (tick_fetch, дозабор `--since`). Ничего не пишет, к бирже не ходит.

Две правды о входе:
  • «книга»  — цена входа как в журнале (закрытие сигнального бара), путь цены — с закрытия этого бара.
               Так считает сама книга; путь между закрытием бара и моментом записи входа (~полчаса) ей уже известен.
  • «честно» — вход по открытию первой трёхминутки ПОСЛЕ момента записи входа (at). Всё остальное — от неё.

Выходы (всё на трёхминутках, комиссия FEE за круг):
  • цель лимиткой: исполнена, если максимум (для шорта — минимум) трёхминутки её достал;
  • стоп книги, если он у книги есть; бар, где достали и стоп, и цель, — считается стопом (как у книги);
  • срок книги — закрытие по цене последней трёхминутки срока;
  • ПОВТОР (идея владельца): после цели лимитка на ту же цену входа; цена вернулась — снова вход,
    та же цель и тот же стоп от новой цены, пока не кончился срок исходной сделки.
Хеджа «картины» здесь нет — сравнение идёт с тем же вариантом без хеджа, записанным по книге.

    python3 lab_replay.py                     # все книги, сводка
    python3 lab_replay.py --book картина      # одна книга
    python3 lab_replay.py --days              # плюс разбивка по дням
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
try:
    from core_config import (PAPER_CROWD_STOP, PAPER_CROWD_HOLD, PAPER_END_HOLD, SIGHT_TARGET_LAB,
                             SIGHT_HOLD_LAB)
except ImportError:
    PAPER_CROWD_STOP, PAPER_CROWD_HOLD, PAPER_END_HOLD = 0.02, 6, 24
    SIGHT_TARGET_LAB, SIGHT_HOLD_LAB = 0.03, 48          # как в paper_sight.py (SIGHT_TARGET, SIGHT_HOLD_BARS)

TICK_DIR = BASE_DIR / "cq_v2" / "tick"
OUT = BASE_DIR / "output"
FEE = 0.001                    # круг: вход и выход, как SIGHT_FEE / PAPER_CROWD_FEE
BAR30 = 1800
STEP = 180
TARGETS = [0.03, 0.05, 0.07, 0.10]      # 3% — как у «картины» сейчас; 5–10% — диапазон владельца

BOOKS = {                       # файл → (метка, сторона по умолчанию, стоп и срок по умолчанию)
    "paper_sight": ("картина", None, None, SIGHT_HOLD_LAB),
    "paper_crowd": ("толпа", None, PAPER_CROWD_STOP, PAPER_CROWD_HOLD),
    "paper_end": ("конец", -1, None, PAPER_END_HOLD),
    "paper_bottom": ("дно", 1, None, 144),
}


def _ts(iso: str) -> int:
    return int(datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())


_cache: dict[str, list] = {}


def bars(sym: str) -> list[tuple]:
    """(время открытия, о, h, l, c) по возрастанию, без дублей: файл дописывался и дозабором, порядок не гарантирован"""
    base = sym.replace("USDT", "").lower()
    if base not in _cache:
        seen: dict[int, tuple] = {}
        p = TICK_DIR / f"{base}.jsonl"
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                    t = _ts(r["candle"])
                    seen[t] = (t, float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]))
                except (ValueError, KeyError, TypeError):
                    continue
        _cache[base] = [seen[t] for t in sorted(seen)]
    return _cache[base]


def _first(bs: list, t: int) -> int:
    lo, hi = 0, len(bs)
    while lo < hi:
        mid = (lo + hi) // 2
        if bs[mid][0] < t:
            lo = mid + 1
        else:
            hi = mid
    return lo


def play(bs: list, i0: int, t_end: int, px: float, side: int, target: float | None, stop: float | None,
         repeat: bool) -> list[float]:
    """результаты кругов в долях; первый вход по px на баре i0"""
    legs: list[float] = []
    i, e, inside = i0, px, True
    while i < len(bs) and bs[i][0] < t_end:
        t, o, h, l, c = bs[i]
        if inside:
            tgt = e * (1 + side * target) if target else None
            stp = e * (1 - side * stop) if stop else None
            hit_s = stp is not None and ((l <= stp) if side > 0 else (h >= stp))
            hit_t = tgt is not None and ((h >= tgt) if side > 0 else (l <= tgt))
            if hit_s:                                   # спорный бар — против позиции
                legs.append(-stop - FEE)
                return legs                             # после стопа не повторяем: картина сломалась
            if hit_t:
                legs.append(target - FEE)
                if not repeat:
                    return legs
                inside = False
            last_c = c
        else:                                           # ждём возврата к цене входа, со следующего бара
            if (l <= e) if side > 0 else (h >= e):
                inside = True
                last_c = c
                # вход на этом баре: цель/стоп проверяем со следующего, чтобы не брать ход внутри бара дважды
        i += 1
    if inside and i > i0:
        legs.append(side * (last_c / e - 1) - FEE)      # срок
    return legs


def entries() -> list[dict]:
    out = []
    for f, (label, side0, stop0, hold0) in BOOKS.items():
        p = OUT / f"{f}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("kind") != "entry" or not r.get("sym") or not r.get("px"):
                continue
            side = int(r.get("side") or side0 or 0)
            if not side:
                continue
            hold = int(r.get("hold") or hold0)
            stop = r.get("stop") if r.get("stop") is not None else stop0
            if f == "paper_sight":
                tgt, stop = SIGHT_TARGET_LAB, None
            else:
                tgt = r.get("target")
            out.append({"book": label, "sym": r["sym"], "side": side, "t": int(r["t"]) // 1000,
                        "at": int(r["at"]), "px": float(r["px"]), "hold": hold, "stop": stop, "target": tgt})
    return out


def run(es: list[dict]) -> dict:
    """ключ варианта → список (день, сумма кругов, число кругов)"""
    res: dict[str, list] = defaultdict(list)
    miss = 0
    for x in es:
        bs = bars(x["sym"])
        if not bs:
            miss += 1
            continue
        day = datetime.fromtimestamp(x["at"], timezone.utc).strftime("%m-%d")
        t_book = x["t"] + BAR30                      # закрытие сигнального бара
        t_end = t_book + x["hold"] * BAR30
        ib, ih = _first(bs, t_book), _first(bs, x["at"])
        if ib >= len(bs) or ih >= len(bs) or bs[ih][0] - x["at"] > 600:
            miss += 1
            continue
        px_h = bs[ih][1]                             # открытие первой трёхминутки после записи входа
        slip = x["side"] * (px_h / x["px"] - 1)      # сколько цена ушла к моменту записи, в пользу позиции +
        res["_slip"].append((day, slip, 1))
        for name, (i0, px) in {"книга": (ib, x["px"]), "честно": (ih, px_h)}.items():
            legs = play(bs, i0, t_end, px, x["side"], x["target"], x["stop"], False)
            res[f"{name} · как книга"].append((day, sum(legs), len(legs)))
        for tg in TARGETS:
            for rep in (False, True):
                legs = play(bs, ih, t_end, px_h, x["side"], tg, x["stop"], rep)
                res[f"честно · цель {tg * 100:.0f}%{' · повтор' if rep else ''}"].append((day, sum(legs), len(legs)))
    res["_miss"] = [("", 0.0, miss)]
    return res


def _line(name: str, xs: list) -> str:
    v = [s for _, s, _ in xs]
    n_leg = sum(k for _, _, k in xs)
    if not v:
        return f"  {name:32s} —"
    return (f"  {name:32s} сделок {len(v):5d} кругов {n_leg:5d} · в плюсе {sum(1 for a in v if a > 0) / len(v) * 100:3.0f}%"
            f" · средняя {st.mean(v) * 100:+6.2f}% · медиана {st.median(v) * 100:+6.2f}% · сумма {sum(v) * 100:+8.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book")
    ap.add_argument("--days", action="store_true")
    a = ap.parse_args()
    es = entries()
    books = sorted({x["book"] for x in es})
    for b in books:
        if a.book and b != a.book:
            continue
        sub = [x for x in es if x["book"] == b]
        res = run(sub)
        slip = [s for _, s, _ in res.pop("_slip", [])]
        miss = res.pop("_miss")[0][2]
        print(f"\n════════ {b} · входов {len(sub)} · без трёхминуток {miss}")
        if slip:
            print(f"  к моменту записи входа цена ушла: медиана {st.median(slip) * 100:+.2f}% в пользу позиции,"
                  f" в пользу {sum(1 for s in slip if s > 0) / len(slip) * 100:.0f}% входов")
        for k in sorted(res, key=lambda k: (not k.startswith("книга"), k)):
            print(_line(k, res[k]))
            if a.days:
                by = defaultdict(list)
                for d, s, n in res[k]:
                    by[d].append((d, s, n))
                for d in sorted(by):
                    print("      " + _line(d, by[d]).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
