#!/usr/bin/env python3
"""ЛАБОРАТОРИЯ СТЫКОВ У ЛИДЕРОВ (16.09; владелец: «видно по индикаторам и переход между сессиями как основа и
подтверждение и наоборот»; «между сессиями важны лидеры только, те, кто идёт, — на остальных монетах будет шум»).

ВОПРОС. Сигнал быстрых (клингер 30м, вортекс 30м) у монеты, которая ведёт доску, — подтверждается ли он ответом
следующей сессии? И наоборот: сессия открылась и не ответила — подтверждается ли это сломом внутри неё?

ЛИДЕР. Монета, которая идёт: на баре её ход за сутки ≥ --lead-min процентов и она в первых --lead-top доски по
этому ходу. Окно лидера — от первого такого бара до --tail часов после последнего (туда попадает разворот).
Остальные монеты считаются отдельной строкой — проверка, что там шум.

СИГНАЛЫ — ПО ЛИНИЯМ, КАК ЧИТАЕТ ВЛАДЕЛЕЦ (16.09: «рост вортекса от бара к следующему бару — давление продавцов;
клингер — следующий пик ниже предыдущего, и главное, с пика он упал; цена висит на плече»; 11.09: «направление
читать по каждой линии, не по разрыву»):
  • вортекс «давят продавцы» — VI− растёт --vx-bars баров подряд, VI+ за это время не вырос; сила — на сколько
    поднялась VI−; перегрев — место VI− среди её значений у этой монеты за последние двое суток (0–100);
    зеркально «давят покупатели» — VI+ растёт, VI− не растёт;
  • клингер «выдыхается» — пик KVO ниже предыдущего пика того же хода (не дальше --kl-gap баров), и KVO уже сошёл
    с этого пика: ниже сигнальной и падает; зеркально «продавцы выдыхаются» — впадина выше предыдущей, KVO выше
    сигнальной и растёт; срабатывает один раз на пик;
  • «оба» — вортекс и клингер в одну сторону не дальше --pair баров друг от друга;
  • плечо — по архиву получасовок: «держит», если интерес в пределах 1% от своего максимума за 6 часов и за бар
    не упал больше чем на 0.5%; иначе «уходит». Формулы вортекса и клингера — как в render_coin._fast_events.

СТЫК. Открытия сессий в UTC (SESS_OPEN near_move: Сидней 21, Токио 0, Лондон 7, Нью-Йорк 13).
  • «перед стыком» — сигнал на баре, закрывшемся не раньше чем за --near минут до открытия;
  • «начало сессии» — сигнал в первые --near минут после открытия;
  • «середина» — остальное.
ОТВЕТ СЕССИИ (для «перед стыком») — первые --answer баров после открытия: для сигнала вниз «откупили», если цена
закрылась на уровне сигнала или выше; «не откупили» — нет. Для сигнала вверх зеркально («продали» / «не продали»).
ОТВЕТ ДО СИГНАЛА (для «начало сессии») — бары от открытия до сигнала: для сигнала вниз «сессия не ответила», если
за них цена не обновила максимум двух часов до открытия; «ответила» — обновила.
ИНТЕРЕС В ОТВЕТЕ — за ответные бары: «ушёл», если упал больше чем на 1% (рука уходит), иначе «на месте».

ИСХОД. Ход от закрытия бара сигнала через 6 и 12 часов в сторону сигнала (вниз — плюс, если цена упала), и тот же
ход минус медиана доски за то же окно. Попадание — ход ≥ --hit процентов.

Время — только UTC. Ничего не пишет. Свечи — биржа (core_binance.get_klines, 30м) через общий лимитер.
  python3 lab_junctions.py --only BR          # одна монета: её сигналы и стыки, без доски
  python3 lab_junctions.py --days 4           # все монеты сводки, последние четыре дня
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
    from core_config import KLINGER_30M_EMA, VORTEX_N
except ImportError:
    KLINGER_30M_EMA, VORTEX_N = (34, 55, 13), 14
try:
    from core_config import (JUNCTION_LEAD_MIN, JUNCTION_LEAD_TOP, JUNCTION_TAIL_H, JUNCTION_NEAR_MIN,
                             JUNCTION_ANSWER_BARS, JUNCTION_VX_BARS, JUNCTION_KL_GAP, JUNCTION_PAIR, JUNCTION_HIT_PCT)
except ImportError:
    JUNCTION_LEAD_MIN, JUNCTION_LEAD_TOP, JUNCTION_TAIL_H, JUNCTION_NEAR_MIN = 20.0, 5, 12.0, 120
    JUNCTION_ANSWER_BARS, JUNCTION_VX_BARS, JUNCTION_KL_GAP, JUNCTION_PAIR, JUNCTION_HIT_PCT = 4, 3, 36, 4, 2.0
try:
    from near_move import SESS_OPEN
except Exception:  # noqa: BLE001
    SESS_OPEN = {21: "Сидней", 0: "Токио", 7: "Лондон", 13: "Нью-Йорк"}

BAR = 1800
UTC = timezone.utc


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def coins() -> list[str]:
    nm = _read(BASE_DIR / "output" / "near_move.json") or {}
    out = [str(s).upper() for s in (nm.get("coins") or {}).keys()]
    return sorted(set(s if s.endswith("USDT") else s + "USDT" for s in out))


def bars_of(sym: str, limit: int) -> list[tuple]:
    """закрытые получасовки биржи: (t сек, h, l, c, оборот $)"""
    import core_binance as cb
    from core_binance import get_klines
    K_T = getattr(cb, "K_OPEN_TIME", 0)
    K_H, K_L = getattr(cb, "K_HIGH", 2), getattr(cb, "K_LOW", 3)
    K_C, K_Q = getattr(cb, "K_CLOSE", 4), getattr(cb, "K_QUOTE_VOLUME", 7)
    now = datetime.now(UTC).timestamp()
    out = []
    for k in get_klines(sym, "30m", limit=limit) or []:
        t = int(k[K_T]) // 1000
        if t + BAR > now:
            continue                                   # свеча ещё открыта
        out.append((t, float(k[K_H]), float(k[K_L]), float(k[K_C]), float(k[K_Q])))
    return out


def archive_index(syms: set[str] | None, since: int) -> dict:
    """база монеты → {t сек: строка архива} за окно: живые файлы cq_v2/intraday и дневные cq_v2/archive/intraday/*.gz.
    syms — базы (ARB) или None — все монеты."""
    import gzip
    out: dict = defaultdict(dict)

    def put(base: str, r: dict):
        try:
            t = int(datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp())
        except (ValueError, KeyError, TypeError):
            return
        if t >= since:
            out[base][t] = r

    live = BASE_DIR / "cq_v2" / "intraday"
    for p in sorted(live.glob("*.jsonl")) if live.exists() else []:
        base = p.stem.upper()
        if syms is not None and base not in syms:
            continue
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                put(base, json.loads(ln))
            except ValueError:
                continue
    arch = BASE_DIR / "cq_v2" / "archive" / "intraday"
    day0 = datetime.fromtimestamp(since, UTC).strftime("%Y-%m-%d")
    for p in sorted(arch.glob("*/*.jsonl.gz")) if arch.exists() else []:
        if p.name[:10] < day0:
            continue
        try:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                for ln in f:
                    try:
                        r = json.loads(ln)
                    except ValueError:
                        continue
                    base = str(r.get("sym") or "").upper().replace("USDT", "")
                    if not base or (syms is not None and base not in syms):
                        continue
                    try:
                        t = int(datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp())
                    except (ValueError, KeyError, TypeError):
                        continue
                    if t >= since and t not in out[base]:      # живой файл главнее дневного
                        out[base][t] = r
        except OSError:
            continue
    return out


def oi_of(rows: dict) -> dict:
    """t → интерес из строк архива монеты"""
    return {t: float(r["oi"]) for t, r in rows.items() if r and r.get("oi")}


def delta_of(rows: dict) -> dict:
    """t → дельта тейкеров перпа за бар, $"""
    out = {}
    for t, r in rows.items():
        d = ((r or {}).get("fut") or {}).get("d")
        if d is not None:
            out[t] = float(d)
    return out


def _ema(xs: list, n: int) -> list:
    k, e, res = 2 / (n + 1), None, []
    for x in xs:
        e = x if e is None else x * k + e * (1 - k)
        res.append(e)
    return res


def vortex_lines(bars: list) -> dict:
    """t → (VI+, VI−) за VORTEX_N баров; окна с дырой больше двух баров пропускаются"""
    out = {}
    for i in range(VORTEX_N, len(bars)):
        if any(bars[k][0] - bars[k - 1][0] > 3 * BAR for k in range(i - VORTEX_N + 1, i + 1)):
            continue
        vp = vm = tr = 0.0
        for k in range(i - VORTEX_N + 1, i + 1):
            _, h, l, _, _ = bars[k]
            _, ph, pl, pc, _ = bars[k - 1]
            vp += abs(h - pl)
            vm += abs(l - ph)
            tr += max(h - l, abs(h - pc), abs(l - pc))
        if tr > 0:
            out[bars[i][0]] = (vp / tr, vm / tr)
    return out


def klinger_lines(bars: list) -> dict:
    """t → (KVO, сигнальная); первые 55 баров — разогрев"""
    f34, f55, f13 = KLINGER_30M_EMA
    sv, prev = [], None
    for _, h, l, c, v in bars:
        hlc = (h + l + c) / 3
        sv.append(v if (prev is None or hlc >= prev) else -v)
        prev = hlc
    kvo = [a - b for a, b in zip(_ema(sv, f34), _ema(sv, f55))]
    sig = _ema(kvo, f13)
    return {bars[i][0]: (kvo[i], sig[i]) for i in range(f55, len(bars))}


def vortex_events(vl: dict, n: int) -> list[tuple]:
    """(t, сторона, сила, перегрев): VI− растёт n баров подряд при не растущей VI+ (−1) и зеркально (+1)"""
    ts = sorted(vl)
    out = []
    run_dn = run_up = 0
    for i in range(1, len(ts)):
        if ts[i] - ts[i - 1] != BAR:
            run_dn = run_up = 0
            continue
        vp, vm = vl[ts[i]]
        pvp, pvm = vl[ts[i - 1]]
        run_dn = run_dn + 1 if vm > pvm else 0
        run_up = run_up + 1 if vp > pvp else 0
        hist_m = [vl[x][1] for x in ts[max(0, i - 96):i + 1]]
        hist_p = [vl[x][0] for x in ts[max(0, i - 96):i + 1]]
        if run_dn == n and i >= n and vp <= vl[ts[i - n]][0]:
            heat = 100 * sum(1 for x in hist_m if x <= vm) / len(hist_m)
            out.append((ts[i], -1, vm - vl[ts[i - n]][1], heat))
        if run_up == n and i >= n and vm <= vl[ts[i - n]][1]:
            heat = 100 * sum(1 for x in hist_p if x <= vp) / len(hist_p)
            out.append((ts[i], 1, vp - vl[ts[i - n]][0], heat))
    return out


def klinger_events(kl: dict, gap: int) -> list[tuple]:
    """(t, сторона, прошлый пик, этот пик): пик ниже прошлого и KVO сошёл с него под сигнальную и падает (−1);
    впадина выше прошлой и KVO поднялся над сигнальной и растёт (+1). Пик подтверждён двумя барами после."""
    ts = sorted(kl)
    kv = [kl[t][0] for t in ts]
    sg = [kl[t][1] for t in ts]
    n = len(ts)
    # пик j подтверждён, когда видны два бара после него (окно j−3…j+2) — на баре i берутся только j ≤ i − 2
    is_hi = [3 <= j <= n - 3 and kv[j] > 0 and kv[j] == max(kv[j - 3:j + 3]) for j in range(n)]
    is_lo = [3 <= j <= n - 3 and kv[j] < 0 and kv[j] == min(kv[j - 3:j + 3]) for j in range(n)]
    out = []
    hi, lo = [], []
    fired_hi, fired_lo = set(), set()
    for i in range(6, n):
        j = i - 2
        if is_hi[j]:
            hi.append(j)
        if is_lo[j]:
            lo.append(j)
        if ts[i] - ts[i - 1] != BAR:
            continue
        if len(hi) >= 2:
            j1, j2 = hi[-2], hi[-1]
            if j2 not in fired_hi and j2 - j1 <= gap and kv[j2] < kv[j1] and kv[i] < sg[i] and kv[i] < kv[i - 1]:
                fired_hi.add(j2)
                out.append((ts[i], -1, kv[j1], kv[j2]))
        if len(lo) >= 2:
            j1, j2 = lo[-2], lo[-1]
            if j2 not in fired_lo and j2 - j1 <= gap and kv[j2] > kv[j1] and kv[i] > sg[i] and kv[i] > kv[i - 1]:
                fired_lo.add(j2)
                out.append((ts[i], 1, kv[j1], kv[j2]))
    return out


def leverage(oi: dict, t: int):
    """плечо на баре: «держит» / «уходит» / None (архива нет) и отход интереса от максимума за 6 ч, %"""
    o = oi.get(t)
    if not o:
        return None, None
    win = [oi[t - k * BAR] for k in range(12) if oi.get(t - k * BAR)]
    prev = oi.get(t - BAR)
    off = (o / max(win) - 1) * 100
    bar = (o / prev - 1) * 100 if prev else 0.0
    return ("держит" if off > -1.0 and bar > -0.5 else "уходит"), round(off, 2)


def opens_around(t_close: int) -> tuple[int, int]:
    """ближайшее открытие сессии после момента и последнее до него (секунды UTC)"""
    day = (t_close // 86400) * 86400
    cands = sorted(day + d * 86400 + h * 3600 for d in (-1, 0, 1) for h in SESS_OPEN)
    nxt = min(x for x in cands if x > t_close)
    prv = max(x for x in cands if x <= t_close)
    return nxt, prv


def sess_name(t_open: int) -> str:
    return SESS_OPEN.get(datetime.fromtimestamp(t_open, UTC).hour, "?")


def pct(a, b):
    return (b / a - 1) * 100 if a else None


def med(v):
    return st.median(v) if v else None


def leader_windows(closes: dict, lead_min: float, lead_top: int, tail_h: float, solo: bool) -> dict:
    """sym → множество t баров, где монета в окне лидера"""
    ch24 = defaultdict(dict)                          # t → {sym: ход за сутки}
    for s, c in closes.items():
        for t, px in c.items():
            p0 = c.get(t - 48 * BAR)
            if p0:
                ch24[t][s] = (px / p0 - 1) * 100
    lead = defaultdict(set)
    for t, m in ch24.items():
        top = sorted(m.items(), key=lambda x: -x[1])
        top = top if solo else top[:lead_top]
        for s, v in top:
            if v >= lead_min:
                lead[s].add(t)
    win = {}
    for s, ts in lead.items():
        w = set()
        for t in ts:
            for k in range(int(tail_h * 2) + 1):
                w.add(t + k * BAR)
        win[s] = w
    return win


def junction(t: int, near_min: int) -> tuple[str, int | None]:
    """где сигнал относительно открытий сессий: категория и открытие, к которому он относится"""
    tc = t + BAR
    nxt, prv = opens_around(tc)
    if nxt - tc <= near_min * 60:
        return "перед стыком", nxt
    if tc - prv <= near_min * 60:
        return "начало сессии", prv
    return "середина", None


def answer(side: int, cat: str, t: int, t_open: int | None, px: float, c: dict, hi: dict, lo: dict, oi: dict,
           bars: int) -> tuple[str | None, str | None]:
    """ответ сессии и интерес в ответных барах; None — данных не хватает"""
    ans = oi_ans = None
    if cat == "перед стыком" and t_open:
        ab = [c.get(t_open + k * BAR) for k in range(bars)]
        ab = [x for x in ab if x]
        if len(ab) >= max(1, bars - 1):
            back = max(ab) >= px if side < 0 else min(ab) <= px
            ans = ("откупили" if back else "не откупили") if side < 0 else ("продали" if back else "не продали")
        o0, o1 = oi.get(t_open - BAR), oi.get(t_open + (bars - 1) * BAR)
        if o0 and o1:
            oi_ans = "ушёл" if pct(o0, o1) <= -1.0 else "на месте"
    elif cat == "начало сессии" and t_open:
        pre = [t_open - k * BAR for k in range(1, 5)]
        inn = list(range(t_open, t + 1, BAR))
        if side < 0:
            ref = max([hi[x] for x in pre if x in hi] or [0])
            got = max([hi[x] for x in inn if x in hi] or [0])
            ans = ("сессия ответила" if got > ref else "сессия не ответила") if ref else None
        else:
            ref = min([lo[x] for x in pre if x in lo] or [0])
            got = min([lo[x] for x in inn if x in lo] or [10 ** 18])
            ans = ("сессия продавила" if got < ref else "сессия не продавила") if ref else None
        o0, o1 = oi.get(t_open - BAR), oi.get(t)
        if o0 and o1:
            oi_ans = "ушёл" if pct(o0, o1) <= -1.0 else "на месте"
    return ans, oi_ans


def outcome(side: int, t: int, px: float, c: dict, board_med: dict, btc: dict) -> dict:
    """ход через 6 и 12 ч: в сторону сигнала (side ±1) или сырой (side 0), к доске, и биткоин за то же окно"""
    res = {}
    sgn = side if side else 1
    for hrs in (6, 12):
        t1 = t + hrs * 2 * BAR
        p1 = c.get(t1)
        if not p1:
            continue
        mv = pct(px, p1) * sgn
        b0, b1 = board_med.get(t), board_med.get(t1)
        rel = None if (b0 is None or b1 is None) else mv - (b1 - b0) * sgn
        bt = pct(btc[t], btc[t1]) if (btc.get(t) and btc.get(t1)) else None
        res[hrs] = (round(mv, 2), None if rel is None else round(rel, 2), None if bt is None else round(bt, 2))
    return res


def background(t: int, btc: dict, board_med: dict) -> dict:
    """фон на баре сигнала: биткоин и доска за 6 ч до него, день недели и текущая сессия (UTC)"""
    b6 = pct(btc[t - 12 * BAR], btc[t]) if (btc.get(t) and btc.get(t - 12 * BAR)) else None
    d6 = (board_med[t] - board_med[t - 12 * BAR]) if (t in board_med and (t - 12 * BAR) in board_med) else None
    _, prv = opens_around(t + BAR)
    return {"btc6": None if b6 is None else round(b6, 2), "board6": None if d6 is None else round(d6, 2),
            "btc_bg": None if b6 is None else ("↑" if b6 > 1 else "↓" if b6 < -1 else "ровно"),
            "wd": datetime.fromtimestamp(t, UTC).strftime("%a"), "sess_now": sess_name(prv)}


def signals_of(bars: list, a) -> list[tuple]:
    """все сигналы по линиям на барах монеты: (t, вид, сторона, подробности)"""
    ve = vortex_events(vortex_lines(bars), a.vx_bars)
    ke = klinger_events(klinger_lines(bars), a.kl_gap)
    sig = [(t, "вортекс", side, {"сила": round(st_, 3), "перегрев": round(h_)}) for t, side, st_, h_ in ve]
    sig += [(t, "клингер", side, {"пик был": round(p1), "пик стал": round(p2)}) for t, side, p1, p2 in ke]
    for tv, sv_, _, _ in ve:
        for tk, sk, _, _ in ke:
            if sv_ == sk and abs(tv - tk) <= a.pair * BAR:
                sig.append((max(tv, tk), "оба", sv_, {}))
    seen, out = set(), []
    for x in sorted(sig, key=lambda y: (y[0], y[1])):
        if (x[0], x[1], x[2]) not in seen:
            seen.add((x[0], x[1], x[2]))
            out.append(x)
    return out


def analyse(data: dict, board_med: dict, win: dict, a, btc: dict) -> list[dict]:
    """все сигналы: лидер или нет, стык, ответ сессии, плечо, фон, исход"""
    out = []
    for s, d in data.items():
        bars, oi = d["bars"], d["oi"]
        c = {t: x for t, _, _, x, _ in bars}
        hi = {t: h for t, h, _, _, _ in bars}
        lo = {t: l for t, _, l, _, _ in bars}
        for t, kind, side, extra in signals_of(bars, a):
            if t < d["since"]:
                continue
            px = c.get(t)
            if not px:
                continue
            cat, t_open = junction(t, a.near)
            ans, oi_ans = answer(side, cat, t, t_open, px, c, hi, lo, oi, a.answer)
            lev, lev_off = leverage(oi, t)
            top = max([c[t - k * BAR] for k in range(12) if c.get(t - k * BAR)] or [px])
            out.append({"sym": s, "t": t, "kind": kind, "side": side, "px": px, "extra": extra,
                        "leader": t in win.get(s, set()), "cat": cat,
                        "sess": sess_name(t_open) if t_open else "", "ans": ans, "oi_ans": oi_ans,
                        "lev": lev, "lev_off": lev_off, "from_top": round(pct(top, px), 2),
                        "bg": background(t, btc, board_med), "res": outcome(side, t, px, c, board_med, btc)})
    return out


def board_median(closes: dict) -> dict:
    """t → медиана по доске «индекса» цены (накопленный ход от первого общего бара), чтобы вычитать фон"""
    idx = defaultdict(list)
    for c in closes.values():
        ts = sorted(c)
        for i in range(1, len(ts)):
            if ts[i] - ts[i - 1] == BAR and c[ts[i - 1]]:
                idx[ts[i]].append((c[ts[i]] / c[ts[i - 1]] - 1) * 100)
    out, acc = {}, 0.0
    for t in sorted(idx):
        acc += st.median(idx[t])
        out[t] = acc
    return out


def _stats(v: list[dict], hit: float) -> str:
    m6 = [r["res"][6][0] for r in v if 6 in r["res"]]
    r6 = [r["res"][6][1] for r in v if 6 in r["res"] and r["res"][6][1] is not None]
    m12 = [r["res"][12][0] for r in v if 12 in r["res"]]
    r12 = [r["res"][12][1] for r in v if 12 in r["res"] and r["res"][12][1] is not None]
    hr = (100 * sum(1 for x in m12 if x >= hit) / len(m12)) if m12 else None
    f = lambda x: "—" if x is None else f"{x:+.2f}"
    return (f"{len(v):>4}{f(med(m6)):>8}{f(med(r6)):>9}{f(med(m12)):>8}{f(med(r12)):>9}"
            f"{('—' if hr is None else format(hr, '.0f') + '%'):>7}")


def table(rows: list[dict], title: str, hit: float, key, head: str) -> None:
    print(f"\n════ {title}")
    if not rows:
        print("   нет сигналов")
        return
    g = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    print(f"   {head}{'n':>4}{'6ч':>8}{'к доске':>9}{'12ч':>8}{'к доске':>9}{'≥' + format(hit, 'g') + '%':>7}")
    for k in sorted(g, key=lambda x: tuple(str(y) for y in x)):
        print("   " + "".join(f"{str(x):<{w}}" for x, w in zip(k, (9, 6, 15, 21, 10))) + _stats(g[k], hit))


def _dir(r):
    return "вниз" if r["side"] < 0 else "вверх"


def heat_bin(h) -> str:
    if h is None:
        return "—"
    return "до 50" if h < 50 else "50–85" if h < 85 else "85 и выше"


def _jl(path: Path) -> list[dict]:
    out = []
    if not path.exists():
        return out
    for ln in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def journal_report(a) -> int:
    """РАЗБОР ЖУРНАЛА НАБЛЮДЕНИЙ: сигналы и режим лидеров, созревшие (исход через 12 ч проставлен)"""
    rows = _jl(BASE_DIR / "output" / "junction_log.jsonl")
    outs = {r["id"]: r for r in rows if r.get("kind") == "outcome"}
    sig, reg = [], []
    for r in rows:
        o = outs.get(r.get("id"))
        if not o:
            continue
        res = {int(k): tuple(v) for k, v in (o.get("res") or {}).items()}
        x = dict(r, res=res, ans=o.get("ans"), oi_ans=o.get("oi_ans"))
        if r.get("kind") == "signal":
            sig.append(x)
        elif r.get("kind") == "regime":
            reg.append(x)
    waiting = sum(1 for r in rows if r.get("kind") in ("signal", "regime") and r.get("id") not in outs)
    print(f"журнал: сигналов с исходом {len(sig)} · замеров режима с исходом {len(reg)} · ждут исхода {waiting}")
    if not sig and not reg:
        print("созревших строк нет — исход проставляется через 12 ч после бара")
        return 0
    print("исход сигналов — ход в сторону сигнала; режима — сырой ход цены; «к доске» — минус медиана доски; время UTC")
    for r in sig:
        r.setdefault("extra", {})
        r["bg"] = r.get("bg") or {}
    K0 = lambda r: (r["sig"], _dir(r), "биткоин " + (r["bg"].get("btc_bg") or "—"))
    table(sig, "СИГНАЛЫ · ФОН ПЕРВЫМ: биткоин за 6 ч до сигнала", a.hit, K0, f"{'сигнал':<9}{'куда':<6}{'фон':<15}")
    K1 = lambda r: (r["sig"], _dir(r), r["cat"], r["ans"] or "—")
    table(sig, "СИГНАЛЫ · стык × ответ сессии", a.hit, K1, f"{'сигнал':<9}{'куда':<6}{'где':<15}{'ответ сессии':<21}")
    K2 = lambda r: (r["sig"], _dir(r), r["cat"], r["ans"] or "—", r["oi_ans"] or "—")
    table([r for r in sig if r["cat"] != "середина"], "СИГНАЛЫ · у стыка: ответ × интерес в ответе", a.hit, K2,
          f"{'сигнал':<9}{'куда':<6}{'где':<15}{'ответ сессии':<21}{'интерес':<10}")
    K3 = lambda r: (r["sig"], _dir(r), r.get("lev") or "нет архива")
    table(sig, "СИГНАЛЫ · плечо на баре сигнала", a.hit, K3, f"{'сигнал':<9}{'куда':<6}{'плечо':<15}")
    K5 = lambda r: (r["sig"], _dir(r), heat_bin((r.get("extra") or {}).get("перегрев")))
    table([r for r in sig if r["sig"] == "вортекс"], "СИГНАЛЫ · перегрев вортекса", a.hit, K5, f"{'сигнал':<9}{'куда':<6}{'перегрев':<15}")
    # меры режима — по одной, против сырого хода цены
    for r in sig + reg:
        r.setdefault("side", 0)
    if reg:
        print("\n════ РЕЖИМ ЛИДЕРОВ · каждая мера отдельно (исход — сырой ход цены; «≥» — доля ходов вверх на +2% и больше)")
        bins = (
            ("Хёрст к перемешанному", lambda m: _b((m.get("hurst") or {}).get("rel"), ((-0.08, "ход отменяется"), (0.08, "случайность")), "ход продолжается")),
            ("поглощение", lambda m: None if not m.get("flow") else ("да" if m["flow"].get("absorb", 0) >= 0.25 else "нет")),
            ("палка", lambda m: None if not m.get("flow") else ("да" if m["flow"].get("paint", 0) >= 0.25 else "нет")),
            ("загиб роста", lambda m: None if not m.get("curve") else ("парабола" if (m["curve"].get("c") or 0) > 0.5 and (m["curve"].get("r2") or 0) > 0.8
                                                                       else "загиб вниз" if (m["curve"].get("c") or 0) < -0.5 else "прямая")),
            ("энтропия", lambda m: _b(m.get("pe"), ((0.85, "порядок"),), "хаос")),
            ("выносы тянут друг друга", lambda m: None if not m.get("branch") else
             ("выносов нет" if "ratio" not in m["branch"] else "да" if m["branch"]["ratio"] >= 1.5 else "нет")),
            ("кто ведёт", lambda m: (m.get("lead") or {}).get("who")),
        )
        for name, fn in bins:
            g = defaultdict(list)
            for r in reg:
                k = fn(r.get("m") or {})
                if k is not None:
                    g[k].append(r)
            if not g:
                continue
            print(f"   ── {name}")
            for k in sorted(g):
                v = g[k]
                m6 = [x["res"][6][0] for x in v if 6 in x["res"]]
                m12 = [x["res"][12][0] for x in v if 12 in x["res"]]
                up = (100 * sum(1 for x in m12 if x >= a.hit) / len(m12)) if m12 else None
                dn = (100 * sum(1 for x in m12 if x <= -a.hit) / len(m12)) if m12 else None
                f = lambda x: "—" if x is None else f"{x:+.2f}"
                print(f"      {str(k):<18}{len(v):>5}  6ч {f(med(m6)):>7}  12ч {f(med(m12)):>7}"
                      f"  вверх≥{a.hit:g}% {('—' if up is None else format(up, '.0f') + '%'):>5}"
                      f"  вниз≥{a.hit:g}% {('—' if dn is None else format(dn, '.0f') + '%'):>5}")
    return 0


def _b(v, edges, last: str):
    if v is None:
        return None
    for lim, name in edges:
        if v < lim:
            return name
    return last


def main() -> int:
    ap = argparse.ArgumentParser(description="сигналы быстрых по линиям и стыки сессий у лидеров")
    ap.add_argument("--only", help="одна монета: её сигналы и стыки без доски")
    ap.add_argument("--days", type=int, default=4, help="окно сигналов, дней (по умолчанию 4)")
    ap.add_argument("--lead-min", type=float, default=JUNCTION_LEAD_MIN, help="ход за сутки для лидера, %%")
    ap.add_argument("--lead-top", type=int, default=JUNCTION_LEAD_TOP, help="мест доски для лидера")
    ap.add_argument("--tail", type=float, default=JUNCTION_TAIL_H, help="часов окна после последнего бара лидера")
    ap.add_argument("--near", type=int, default=JUNCTION_NEAR_MIN, help="минут до/после открытия — «у стыка»")
    ap.add_argument("--answer", type=int, default=JUNCTION_ANSWER_BARS, help="ответных баров после открытия")
    ap.add_argument("--hit", type=float, default=JUNCTION_HIT_PCT, help="попадание — ход в сторону сигнала за 12 ч, %%")
    ap.add_argument("--list", type=int, default=40, help="сколько последних сигналов лидеров вывести строками")
    ap.add_argument("--vx-bars", type=int, default=JUNCTION_VX_BARS, help="баров подряд растёт линия вортекса")
    ap.add_argument("--kl-gap", type=int, default=JUNCTION_KL_GAP, help="баров между пиками клингера одного хода")
    ap.add_argument("--pair", type=int, default=JUNCTION_PAIR, help="баров между вортексом и клингером для «оба»")
    ap.add_argument("--journal", action="store_true", help="разобрать накопленный журнал output/junction_log.jsonl")
    a = ap.parse_args()
    if a.journal:
        return journal_report(a)
    syms = ([x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in a.only.split(",")]
            if a.only else coins())
    if not syms:
        print("нет монет: output/near_move.json пуст — запусти после прогона или укажи --only")
        return 1
    need = (a.days + 2) * 48 + 60                     # окно + сутки на ход лидера + разогрев клингера
    since = int(datetime.now(UTC).timestamp()) - a.days * 86400
    arch = archive_index({x.replace("USDT", "") for x in syms}, since - 86400)
    try:
        btc = {t: c for t, _, _, c, _ in bars_of("BTCUSDT", min(1500, need))}
    except Exception as e:  # noqa: BLE001
        print(f"  биткоин: свечи не получены — {type(e).__name__}: {e}")
        btc = {}
    data, closes = {}, {}
    for i, s in enumerate(syms, 1):
        try:
            b = bars_of(s, min(1500, need))
        except Exception as e:  # noqa: BLE001
            print(f"  {s}: свечи не получены — {type(e).__name__}: {e}")
            continue
        if len(b) < 80:
            continue
        data[s] = {"bars": b, "oi": oi_of(arch.get(s.replace("USDT", ""), {})), "since": since}
        closes[s] = {t: c for t, _, _, c, _ in b}
        if i % 25 == 0:
            print(f"  свечи: {i}/{len(syms)}")
    if not data:
        print("свечей нет")
        return 1
    board = board_median(closes)
    win = leader_windows(closes, a.lead_min, a.lead_top, a.tail, solo=bool(a.only))
    rows = analyse(data, board, win, a, btc)
    lead = [r for r in rows if r["leader"]]
    rest = [r for r in rows if not r["leader"]]
    n_lead = sum(1 for s in win if win[s] and any(t >= since for t in win[s]))
    print(f"монет {len(data)} · дней {a.days} · лидеров в окне {n_lead} (ход за сутки ≥ {a.lead_min:g}%"
          + ("" if a.only else f", первые {a.lead_top} доски") + f") · сигналов у лидеров {len(lead)}, у остальных {len(rest)}")
    print("исход — ход от закрытия бара сигнала в сторону сигнала; «к доске» — минус медиана доски за то же окно; время UTC")
    K0 = lambda r: (r["kind"], _dir(r), "биткоин " + (r["bg"]["btc_bg"] or "—"))
    table(lead, "ЛИДЕРЫ · ФОН ПЕРВЫМ: биткоин за 6 ч до сигнала (↑ больше +1%, ↓ меньше −1%)", a.hit, K0,
          f"{'сигнал':<9}{'куда':<6}{'фон':<15}")
    K5 = lambda r: (r["kind"], _dir(r), heat_bin(r["extra"].get("перегрев")))
    table([r for r in lead if r["kind"] == "вортекс"], "ЛИДЕРЫ · перегрев вортекса (место линии среди своих значений за двое суток)",
          a.hit, K5, f"{'сигнал':<9}{'куда':<6}{'перегрев':<15}")
    K1 = lambda r: (r["kind"], _dir(r), r["cat"], r["ans"] or "—")
    H1 = f"{'сигнал':<9}{'куда':<6}{'где':<15}{'ответ сессии':<21}"
    table(lead, "ЛИДЕРЫ · сигнал × стык × ответ сессии", a.hit, K1, H1)
    K2 = lambda r: (r["kind"], _dir(r), r["cat"], r["ans"] or "—", r["oi_ans"] or "—")
    table([r for r in lead if r["cat"] != "середина"], "ЛИДЕРЫ · у стыка: ответ сессии × интерес в ответе", a.hit, K2,
          f"{'сигнал':<9}{'куда':<6}{'где':<15}{'ответ сессии':<21}{'интерес':<10}")
    K3 = lambda r: (r["kind"], _dir(r), r["lev"] or "нет архива")
    table(lead, "ЛИДЕРЫ · плечо на баре сигнала", a.hit, K3, f"{'сигнал':<9}{'куда':<6}{'плечо':<15}")
    if not a.only:
        K4 = lambda r: (r["kind"], _dir(r), r["cat"])
        table(rest, "ОСТАЛЬНЫЕ МОНЕТЫ — проверка на шум", a.hit, K4, f"{'сигнал':<9}{'куда':<6}{'где':<15}")
    if lead:
        print(f"\n════ СИГНАЛЫ ЛИДЕРОВ, последние {min(a.list, len(lead))}")
        for r in sorted(lead, key=lambda x: (x["t"], x["kind"]))[-a.list:]:
            tt = datetime.fromtimestamp(r["t"] + BAR, UTC).strftime("%d.%m %H:%M")
            r6 = r["res"].get(6, (None, None))[0]
            r12 = r["res"].get(12, (None, None))[0]
            ex = " ".join(f"{k} {v}" for k, v in r["extra"].items())
            print(f"   {r['sym'][:-4]:<9}{tt} UTC  {r['kind']:<8}{_dir(r):<6}{r['cat']:<14}{(r['sess'] or ''):<9}"
                  f"{(r['ans'] or '—'):<20}интерес {(r['oi_ans'] or '—'):<9}плечо {(r['lev'] or '—'):<7}"
                  f"от вершины {r['from_top']:+.1f}%  6ч {('—' if r6 is None else format(r6, '+.2f')):>7}"
                  f"  12ч {('—' if r12 is None else format(r12, '+.2f')):>7}  {ex}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
