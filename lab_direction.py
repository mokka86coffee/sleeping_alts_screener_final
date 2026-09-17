#!/usr/bin/env python3
"""ПЕРЕБОР НАПРАВЛЕНИЯ (17.09, владелец: «все данные есть — ищи закономерности»). Вопрос один: какое определение
направления на закрытии получасовки предсказывает, куда цена пойдёт дальше. Вортекс+клингер дали ~48% на
следующие полчаса — монетка. Здесь перебираются другие определения и горизонты.

Данные — только наш архив получасовок (живой cq_v2/intraday + дневные gz): цена, размах, интерес, фандинг,
дельта, тейкер, тип бара. Каждое определение считается ТОЛЬКО из баров до t включительно; исход — по барам после.

Исходы на горизонтах 1, 2, 4, 8 получасовок (полчаса – четыре часа):
  • ЗНАК — закрытие через горизонт выше/ниже закрытия t, в сторону предсказания;
  • КАСАНИЕ — цена дошла до +1% (по размаху баров) раньше, чем до −1%; бар, где задеты оба, считается против.
Контроль — базовая частота того же исхода по всем барам без условия: край = попадание минус база. Отдельно
по лидерам (ход за сутки ≥ LEAD_PCT на момент t) и по всей доске, потому что шум есть только у лидеров.
    python3 lab_direction.py                 # все монеты, 30 дней архива
    python3 lab_direction.py --days 7 --only ONE,AVA,BULLA
    python3 lab_direction.py --touch 0.02    # касание ±2%
"""
from __future__ import annotations

import argparse
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
import lab_junctions as lj

BAR = 1800
HORIZONS = (1, 2, 4, 8)
LEAD_PCT = 20.0


def load_ticks(only: set | None) -> dict:
    """ПРОВЕРКА НА ЧИСТЫХ СВЕЧАХ (17.09): строки архива пишутся через 5–15 минут после закрытия получасовки, и цена
    в них — на момент прогона, а дельта и тейкер могут захватывать начало следующего бара. Если край «пузыря» и
    «тейкера» на 30 минутах — утечка будущего, на свечах биржи, собранных в получасовки из трёхминуток строго по
    границам, он исчезнет. Дельта и тейкер здесь — из покупок по рынку в самих свечах; интерес — последняя точка
    внутри получасовки (есть только у свежих трёхминуток)."""
    import json
    tick = BASE_DIR / "cq_v2" / "tick"
    out = {}
    for p in sorted(tick.glob("*.jsonl")):
        base = p.stem.upper()
        if only is not None and base not in only:
            continue
        by: dict = {}
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                t = int(datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
            except (ValueError, KeyError, TypeError):
                continue
            by.setdefault(t // BAR * BAR, {})[t] = r
        rows = []
        for w in sorted(by):
            g = [by[w][t] for t in sorted(by[w])]
            if len(g) < 10:
                continue
            qv = sum(float(x.get("qv") or 0) for x in g)
            tb = sum(float(x.get("tb") or 0) for x in g)
            oi = next((x.get("oi") for x in reversed(g) if x.get("oi")), None)
            fund = next((x.get("funding") for x in reversed(g) if x.get("funding") is not None), None)
            rows.append({"t": w, "px": float(g[-1]["c"]), "h": max(float(x["h"]) for x in g), "l": min(float(x["l"]) for x in g),
                         "oi": oi, "funding": fund,
                         "fut": {"b": tb, "s": qv - tb, "d": 2 * tb - qv, "tk": (tb / (qv - tb)) if qv > tb > 0 else None}})
        if len(rows) >= 60:
            out[base] = rows
    return out


def load(days: int, only: set | None) -> dict:
    since = int(datetime.now(timezone.utc).timestamp()) - days * 86400
    idx = lj.archive_index(only, since)
    out = {}
    for base, by in idx.items():
        rows = []
        for t in sorted(by):
            r = by[t]
            if r.get("px") and r.get("h") and r.get("l"):
                rows.append(dict(r, t=t))
        if len(rows) >= 80:
            out[base] = rows
    return out


def features(rows: list[dict], board: dict, btc: dict) -> list[dict]:
    """на каждый бар — словарь определений направления (+1/−1/0), считанных из баров до него включительно"""
    bars = [(r["t"], float(r["h"]), float(r["l"]), float(r["px"]), float((r.get("fut") or {}).get("b") or 0) + float((r.get("fut") or {}).get("s") or 0)) for r in rows]
    vl, kl = lj.vortex_lines(bars), lj.klinger_lines(bars)
    out = []
    dl = [float((r.get("fut") or {}).get("d") or 0) for r in rows]
    for i, r in enumerate(rows):
        t = r["t"]
        f: dict = {}
        c = float(r["px"])
        if i >= 48:
            f["ход 24ч ≥20%"] = 1 if c / float(rows[i - 48]["px"]) - 1 >= 0.20 else -1 if c / float(rows[i - 48]["px"]) - 1 <= -0.20 else 0
        if t in vl:
            p, m = vl[t]
            f["вортекс"] = 1 if p > m else -1
            if i >= 2 and bars[i - 1][0] in vl and bars[i - 2][0] in vl:
                pp, pm = vl[bars[i - 1][0]]
                p2, m2 = vl[bars[i - 2][0]]
                f["вортекс серия 3"] = 1 if (p > pp > p2 and p > m) else -1 if (m > pm > m2 and m > p) else 0
        if t in kl:
            k, s = kl[t]
            f["клингер"] = 1 if k > s else -1
            if i >= 1 and bars[i - 1][0] in kl:
                k0, s0 = kl[bars[i - 1][0]]
                f["клингер крест"] = 1 if (k > s and k0 <= s0) else -1 if (k < s and k0 >= s0) else 0
                f["клингер над и растёт"] = 1 if (k > s and k > k0) else -1 if (k < s and k < k0) else 0
        if t in vl and t in kl:
            p, m = vl[t]
            k, s = kl[t]
            f["вортекс+клингер"] = 1 if (p > m and k > s) else -1 if (m > p and k < s) else 0
        if i >= 6 and r.get("oi") and rows[i - 6].get("oi"):
            d_oi = float(r["oi"]) / float(rows[i - 6]["oi"]) - 1
            d_px = c / float(rows[i - 6]["px"]) - 1
            f["интерес↑ и цена↑ (3ч)"] = 1 if (d_oi > 0.01 and d_px > 0) else -1 if (d_oi > 0.01 and d_px < 0) else 0
            f["интерес быстрее цены"] = 1 if (d_px > 0.005 and d_oi > d_px) else -1 if (d_px < -0.005 and d_oi > -d_px) else 0
            f["интерес↓ (сброс плеча)"] = -1 if d_oi < -0.02 else 0
        fund = r.get("funding")
        if fund is not None:
            f["платят шорты"] = 1 if fund < -0.01 else -1 if fund > 0.01 else 0
            f["платят лонги (контр)"] = -f["платят шорты"]
        tk = (r.get("fut") or {}).get("tk")
        if tk is not None:
            f["тейкер бара"] = 1 if tk >= 1.15 else -1 if tk <= 0.87 else 0
        if i >= 48:
            w = dl[i - 48:i]
            mu, sd = st.mean(w), (st.pstdev(w) or 1.0)
            z = (dl[i] - mu) / sd
            oi_prev = next((float(x["oi"]) for x in rows[i - 1::-1] if x.get("oi")), None) if i else None
            ch = (float(r["oi"]) / oi_prev - 1) * 100 if (oi_prev and r.get("oi")) else 0
            f["пузырь ясный"] = 1 if (z >= 2 and ch >= 1.5) else -1 if (z <= -2 and ch >= 1.5) else 0
            f["пузырь любой"] = 1 if z >= 2 else -1 if z <= -2 else 0
        if i >= 4:
            m2 = c / float(rows[i - 4]["px"]) - 1
            f["ход за 2ч"] = 1 if m2 >= 0.01 else -1 if m2 <= -0.01 else 0
            f["ход за 2ч (контр)"] = -f["ход за 2ч"]
        ot = [x.get("oi_type") for x in rows[max(0, i - 2):i + 1]]
        f["3× лонги открывают (контр)"] = -1 if ot == ["long_open"] * 3 else 0
        f["3× шорты открывают (контр)"] = 1 if ot == ["short_open"] * 3 else 0
        if i >= 1 and r.get("oi") and rows[i - 1].get("oi"):
            ch1 = float(r["oi"]) / float(rows[i - 1]["oi"]) - 1
            f["конец (интерес −2%, дельта<0)"] = -1 if (ch1 <= -0.02 and dl[i] < 0) else 0
        bm = board.get(t)
        if bm:
            f["доска зелёная"] = 1 if (bm[0] > 0 and bm[1] >= 0.6) else -1 if (bm[0] < 0 and bm[1] <= 0.4) else 0
        if t in btc:
            f["биткоин за час"] = 1 if btc[t] >= 0.3 else -1 if btc[t] <= -0.3 else 0
        h = datetime.fromtimestamp(t, timezone.utc).hour
        f["час после открытия сессии"] = 0
        if h in (21, 0, 7, 13) or (h in (22, 1, 8, 14)):
            f["час после открытия сессии"] = 1 if f.get("ход за 2ч", 0) > 0 else -1 if f.get("ход за 2ч", 0) < 0 else 0
        out.append(f)
    return out


def board_series(data: dict) -> dict:
    closes = {b: {r["t"]: float(r["px"]) for r in rows} for b, rows in data.items()}
    ts = sorted({t for c in closes.values() for t in c})
    out = {}
    for t in ts:
        mv = [c[t] / c[t - 48 * BAR] - 1 for c in closes.values() if c.get(t) and c.get(t - 48 * BAR)]
        if len(mv) >= 20:
            out[t] = (st.median(mv) * 100, sum(1 for m in mv if m > 0) / len(mv))
    return out


def btc_series(data: dict) -> dict:
    c = {r["t"]: float(r["px"]) for r in data.get("BTC", [])}
    return {t: (p / c[t - 2 * BAR] - 1) * 100 for t, p in c.items() if c.get(t - 2 * BAR)}


def outcomes(rows: list[dict], i: int, touch: float) -> dict:
    """исходы после бара i: знак на горизонтах и касание ±touch (первым) на горизонтах"""
    c0 = float(rows[i]["px"])
    o = {}
    for hz in HORIZONS:
        if i + hz < len(rows) and rows[i + hz]["t"] - rows[i]["t"] == hz * BAR:
            o[("знак", hz)] = 1 if float(rows[i + hz]["px"]) > c0 else -1 if float(rows[i + hz]["px"]) < c0 else 0
            up, dn = c0 * (1 + touch), c0 * (1 - touch)
            res = 0
            for k in range(i + 1, i + hz + 1):
                h, l = float(rows[k]["h"]), float(rows[k]["l"])
                if h >= up and l <= dn:
                    res = 2; break                      # оба в одном баре — порядок неизвестен
                if h >= up:
                    res = 1; break
                if l <= dn:
                    res = -1; break
            o[("касание", hz)] = res
    return o


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--only")
    ap.add_argument("--touch", type=float, default=0.01)
    ap.add_argument("--min-n", type=int, default=80)
    ap.add_argument("--source", default="intraday", choices=["intraday", "tick"], help="tick — получасовки из трёхминуток биржи, чистая проверка")
    a = ap.parse_args()
    only = {x.strip().upper().replace("USDT", "") for x in a.only.split(",")} if a.only else None
    data = load_ticks(None if only is None else only | {"BTC"}) if a.source == "tick" else load(a.days, None if only is None else only | {"BTC"})
    board, btc = board_series(data), btc_series(data)
    if only:
        data = {b: r for b, r in data.items() if b in only}
    print(f"монет {len(data)} · баров {sum(len(r) for r in data.values())} · источник {a.source} · касание ±{a.touch * 100:.0f}%")
    # сбор: (определение, горизонт, исход, группа) → [попал?]; база: (горизонт, исход, группа, сторона) → [был ли исход в эту сторону]
    hits = defaultdict(list)
    base = defaultdict(list)
    for b, rows in data.items():
        F = features(rows, board, btc)
        for i in range(len(rows)):
            o = outcomes(rows, i, a.touch)
            if not o:
                continue
            lead = F[i].get("ход 24ч ≥20%", 0) == 1
            groups = ("все", "лидеры") if lead else ("все",)
            for (kind, hz), v in o.items():
                for g in groups:
                    base[(kind, hz, g, 1)].append(v == 1)
                    base[(kind, hz, g, -1)].append(v == -1)
            for name, d in F[i].items():
                if d == 0:
                    continue
                for (kind, hz), v in o.items():
                    for g in groups:
                        hits[(name, kind, hz, g, d)].append(v == d)
    # отчёт: по группе и исходу — таблица определение × горизонт: попадание и край к базе
    for g in ("все", "лидеры"):
        for kind in ("знак", "касание"):
            print(f"\n{'═' * 10} {g.upper()} · исход «{kind}» · база (сколько окон вообще идут вверх / вниз): "
                  + " · ".join(f"{hz * 30}м {100 * st.mean(base[(kind, hz, g, 1)]):.0f}/{100 * st.mean(base[(kind, hz, g, -1)]):.0f}%"
                               for hz in HORIZONS if base.get((kind, hz, g, 1))))
            names = sorted({k[0] for k in hits if k[1] == kind and k[3] == g})
            rows_out = []
            for name in names:
                cells = []
                best = 0.0
                for hz in HORIZONS:
                    parts = []
                    for d in (1, -1):
                        v = hits.get((name, kind, hz, g, d)) or []
                        if len(v) < a.min_n:
                            continue
                        b_ = st.mean(base[(kind, hz, g, d)])
                        e = st.mean(v) - b_
                        best = max(best, abs(e))
                        parts.append(f"{'↑' if d > 0 else '↓'}{100 * st.mean(v):.0f}%({100 * e:+.0f}) n{len(v)}")
                    cells.append(" ".join(parts) if parts else "—")
                rows_out.append((best, name, cells))
            rows_out.sort(key=lambda x: -x[0])
            print(f"{'определение':30s} " + " | ".join(f"{hz * 30:>3d}м".ljust(26) for hz in HORIZONS))
            for _, name, cells in rows_out:
                print(f"{name:30s} " + " | ".join(c.ljust(26) for c in cells))
    print("\nчитать так: ↑57%(+6) n120 — когда определение сказало «вверх», через горизонт цена была выше в 57% окон,"
          " это на 6 пунктов лучше базы по всем окнам, таких окон 120. Край от ±5 при n от 200 — стоит смотреть;"
          " большой минус — работает наоборот.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
