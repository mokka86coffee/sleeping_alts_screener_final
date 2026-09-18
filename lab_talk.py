"""ЛАБОРАТОРИЯ РАЗГОВОРА (18.09, владелец: «давай алгоритмы применим и посчитаем по истории и выведем формулы»).

Считает по архиву получасовок три мерки кита и толпы — и сверяет их с тем, что цена сделала ПОСЛЕ:
  · цена движения  — долларов оборота на один процент хода (дорожает ход или дешевеет);
  · ответ толпы    — долларов плеча, пришедших на один процент хода (толпа лезет или кит тащит один);
  · состояние      — показал · ответили · ведёт · раздаёт · отпустили · не ответили · тихо.

Ничего не предсказывает и ничего не решает: на каждом баре берутся ТОЛЬКО прошлые бары, исход считается
на будущих и рядом с ним всегда стоит контроль — медиана доски за то же окно (правило владельца 04.09:
«пошла с биткоином» — это отбор, а не фон) и разбивка по сессии.

Руками:
    python3 lab_talk.py --only ONE            # одна монета, как велено проверять
    python3 lab_talk.py                       # вся доска из cq_v2/intraday
    python3 lab_talk.py --bars 6,12,24        # окна исхода в барах (по умолчанию 6, 12, 24)
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ARCH = next((p for p in (BASE_DIR / "cq_v2" / "intraday", Path("cq_v2") / "intraday") if p.exists()), None)
SESS = [(21, "Сидней"), (0, "Токио"), (7, "Лондон"), (13, "Нью-Йорк")]


def ms(c):
    try:
        return int(datetime.fromisoformat(str(c).replace("Z", "+00:00")).timestamp() * 1000)
    except (TypeError, ValueError):
        return None


def qv(r):
    v = float((r.get("kv") or {}).get("qv") or 0)
    if not v:
        f = r.get("fut") or {}
        v = float(f.get("b") or 0) + float(f.get("s") or 0)
    return v


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def sess_of(t_ms):
    h = datetime.fromtimestamp(t_ms / 1000, timezone.utc).hour
    cur = SESS[0][1]
    for oh, nm in SESS:
        if h >= oh:
            cur = nm
    if h < 7:
        cur = "Токио" if h >= 0 and h < 7 else cur
    if 21 <= h or h < 0:
        cur = "Сидней"
    return cur


def load(sym: str):
    p = ARCH / f"{sym.lower()}.jsonl"
    rows = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            t = ms(r.get("candle"))
            if t and r.get("px"):
                r["t"] = t
                rows.append(r)
    except OSError:
        return []
    rows.sort(key=lambda r: r["t"])
    return rows


def features(rows: list) -> list:
    """мерки на каждом баре — только по прошлым барам.
    СКОРОСТЬ (18.09): минимум и максимум окна — скользящими очередями, нормы монеты — раз в NORM_EVERY баров
    по прореженному окну. На доске в 138 монет прежний честный перебор окна давал сотни миллионов операций."""
    NORM_EVERY, WIN, LONG = 12, 336, 1440
    out = []
    pxs = [float(r["px"]) for r in rows]
    vols = [qv(r) for r in rows]
    moves = [0.0] + [((pxs[k] / pxs[k - 1] - 1) * 100 if pxs[k - 1] else 0.0) for k in range(1, len(rows))]
    # скользящие минимум и максимум за LONG баров
    mins, maxs = [], []
    dmin, dmax = deque(), deque()
    for k, v in enumerate(pxs):
        while dmin and pxs[dmin[-1]] >= v:
            dmin.pop()
        dmin.append(k)
        while dmax and pxs[dmax[-1]] <= v:
            dmax.pop()
        dmax.append(k)
        lo = k - LONG
        while dmin[0] < lo:
            dmin.popleft()
        while dmax[0] < lo:
            dmax.popleft()
        mins.append(pxs[dmin[0]]); maxs.append(pxs[dmax[0]])
    nv = nm = None
    for i in range(1, len(rows)):
        r = rows[i]
        if nv is None or i % NORM_EVERY == 0:
            w0 = max(0, i - WIN)
            nv = med([v for v in vols[w0:i:3] if v > 0]) or 0
            nm = med([abs(x) for x in moves[w0:i:3] if x]) or 0.2
        px, mv, v = pxs[i], moves[i], vols[i]
        oi = float(r["oi"]) if r.get("oi") else None
        oi0 = next((float(x["oi"]) for x in reversed(rows[max(0, i - 6):i]) if x.get("oi")), None)
        d_oi_usd = (oi - oi0) if (oi and oi0) else None                # интерес в архиве уже в долларах
        d_oi_pct = (oi / oi0 - 1) * 100 if (oi and oi0) else None
        den = max(abs(mv), 0.25)
        out.append(dict(i=i, t=r["t"], px=px, mv=mv, vol=v, volx=(v / nv if nv else None), normmv=nm,
                        cost=v / den, ans=(d_oi_usd / den if d_oi_usd is not None else None),
                        d_oi=d_oi_pct, fund=r.get("funding"), run=(px / mins[i] - 1) * 100 if mins[i] else 0,
                        dd=(px / maxs[i] - 1) * 100 if maxs[i] else 0, sess=sess_of(r["t"])))
    # цена движения: сглаживание и то, дорожает ли она к началу хода
    for k, b in enumerate(out):
        b["cost_s"] = med([x["cost"] for x in out[max(0, k - 3):k + 1]])
        c0 = med([x["cost"] for x in out[max(0, k - 24):max(1, k - 20)]])
        b["cost_x"] = (b["cost_s"] / c0) if (c0 and b["cost_s"]) else None      # >1 — дорожает
        b["ans_s"] = med([x["ans"] for x in out[max(0, k - 3):k + 1] if x["ans"] is not None])
    # состояние
    for k, b in enumerate(out):
        prev = out[k - 1]["state"] if k else None
        big = b["volx"] is not None and abs(b["mv"]) >= 2 * b["normmv"] and b["volx"] >= 1.5
        follow = b["d_oi"] is not None and b["mv"] > 0 and b["d_oi"] >= 0.5 * abs(b["mv"])
        near = b["dd"] >= -3
        after = b["dd"] < -10
        last3 = [x["d_oi"] for x in out[max(0, k - 2):k + 1] if x["d_oi"] is not None]
        oi_up = len(last3) >= 2 and sum(last3) > 0
        oi_flat = len(last3) >= 2 and sum(last3) <= 0
        if big and b["mv"] > 0 and not follow:
            s = "показал"
        elif follow:
            s = "ответили"
        elif near and oi_flat and (b["volx"] or 9) < 1:
            s = "раздаёт"
        elif near and oi_up:
            s = "ведёт"
        elif prev == "показал" and (b["mv"] < 0 or not oi_up):
            s = "не ответили"
        elif after and oi_flat:
            s = "отпустили"
        else:
            s = "тихо"
        b["state"] = s
    return out


def outcomes(rows: list, feats: list, bars: list) -> None:
    """что цена сделала после бара: ход и лучшая точка за N баров"""
    for b in feats:
        i = b["i"]
        for n in bars:
            nxt = rows[i + 1:i + 1 + n]
            if len(nxt) < n:
                b[f"fwd{n}"] = None
                b[f"max{n}"] = None
                continue
            px = b["px"]
            b[f"fwd{n}"] = (float(nxt[-1]["px"]) / px - 1) * 100
            b[f"max{n}"] = (max(float(x.get("h") or x["px"]) for x in nxt) / px - 1) * 100


def board_median(all_feats: dict, bars: list) -> dict:
    """медиана доски по каждому бару — контроль: сколько дала бы любая монета за то же окно"""
    per_t: dict = {}
    for sym, fs in all_feats.items():
        for b in fs:
            for n in bars:
                v = b.get(f"fwd{n}")
                if v is not None:
                    per_t.setdefault((b["t"], n), []).append(v)
    return {k: st.median(v) for k, v in per_t.items() if len(v) >= 5}


def bucket(b, name):
    if name == "состояние":
        return b["state"]
    if name == "цена движения":
        x = b["cost_x"]
        return None if x is None else ("дешевеет" if x < 0.7 else "ровно" if x < 1.4 else "дорожает" if x < 3 else "дорожает ×3+")
    if name == "ответ толпы":
        a = b["ans_s"]
        if a is None:
            return None
        return "плечо уходит" if a < -1000 else "нет ответа" if a < 1000 else "плечо идёт" if a < 50000 else "плечо валит"
    if name == "фандинг":
        f = b["fund"]
        return None if f is None else ("шорты платят" if f <= -0.5 else "около нуля" if f < 0.05 else "платят лонги")
    if name == "сессия":
        return b["sess"]
    return None


def main():
    ap = argparse.ArgumentParser(description="лаборатория разговора: мерки кита и толпы против исхода")
    ap.add_argument("--only", help="монета или несколько через запятую")
    ap.add_argument("--bars", default="6,12,24", help="окна исхода в барах (получасовки)")
    ap.add_argument("--min-n", type=int, default=20, help="сколько случаев нужно, чтобы строка печаталась")
    a = ap.parse_args()
    if ARCH is None:
        print("нет папки cq_v2/intraday"); return
    bars = [int(x) for x in a.bars.split(",") if x.strip()]
    syms = ([x.strip().upper().replace("USDT", "") for x in a.only.split(",")] if a.only
            else sorted(p.stem.upper() for p in ARCH.glob("*.jsonl")))
    feats: dict = {}
    import time as _tm
    t_start = _tm.monotonic()
    for k, s in enumerate(syms, 1):
        if len(syms) > 1:
            print(f"  {k}/{len(syms)} {s}", end="\r", file=__import__("sys").stderr, flush=True)
        rows = load(s)
        if len(rows) < 200:
            continue
        f = features(rows)
        outcomes(rows, f, bars)
        feats[s] = f
    if not feats:
        print("данных нет"); return
    board = board_median(feats, bars)
    if len(syms) > 1:
        print(f"  посчитано за {_tm.monotonic() - t_start:.0f} с", file=__import__("sys").stderr)
    flat = [b for fs in feats.values() for b in fs]
    print(f"монет {len(feats)} · баров {len(flat)} · окна {bars} получасовок\n")
    for name in ("состояние", "цена движения", "ответ толпы", "фандинг", "сессия"):
        groups: dict = {}
        for b in flat:
            k = bucket(b, name)
            if k:
                groups.setdefault(k, []).append(b)
        print(f"── {name.upper()}")
        head = "  " + "случай".ljust(16) + "N".rjust(7)
        for n in bars:
            head += f"{('ход ' + str(n) + 'б'):>10}{('против доски'):>14}{('лучшая'):>9}"
        print(head)
        for k, g in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            if len(g) < a.min_n:
                continue
            line = "  " + str(k)[:16].ljust(16) + str(len(g)).rjust(7)
            for n in bars:
                fwd = [b[f"fwd{n}"] for b in g if b.get(f"fwd{n}") is not None]
                rel = [b[f"fwd{n}"] - board[(b["t"], n)] for b in g
                       if b.get(f"fwd{n}") is not None and (b["t"], n) in board]
                mx = [b[f"max{n}"] for b in g if b.get(f"max{n}") is not None]
                line += f"{(med(fwd) or 0):>9.2f}%{(med(rel) or 0):>13.2f}%{(med(mx) or 0):>8.2f}%"
            print(line)
        print()
    # контроль: все бары разом
    line = "  " + "ВСЕ БАРЫ".ljust(16) + str(len(flat)).rjust(7)
    for n in bars:
        fwd = [b[f"fwd{n}"] for b in flat if b.get(f"fwd{n}") is not None]
        mx = [b[f"max{n}"] for b in flat if b.get(f"max{n}") is not None]
        line += f"{(med(fwd) or 0):>9.2f}%{0:>13.2f}%{(med(mx) or 0):>8.2f}%"
    print("── КОНТРОЛЬ")
    print(line)


if __name__ == "__main__":
    main()
