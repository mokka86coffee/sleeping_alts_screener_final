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


def oi_of(sym: str) -> dict:
    """интерес по барам из архива получасовок: t сек → oi"""
    p = BASE_DIR / "cq_v2" / "intraday" / f"{sym.replace('USDT', '').lower()}.jsonl"
    out = {}
    if not p.exists():
        return out
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
            t = int(datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp())
        except (ValueError, KeyError, TypeError):
            continue
        if r.get("oi"):
            out[t] = float(r["oi"])
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


def analyse(data: dict, board_med: dict, win: dict, a) -> list[dict]:
    """все сигналы: лидер или нет, стык, ответ сессии, плечо, исход"""
    out = []
    for s, d in data.items():
        bars, oi = d["bars"], d["oi"]
        c = {t: x for t, _, _, x, _ in bars}
        hi = {t: h for t, h, _, _, _ in bars}
        lo = {t: l for t, _, l, _, _ in bars}
        ve = vortex_events(vortex_lines(bars), a.vx_bars)
        ke = klinger_events(klinger_lines(bars), a.kl_gap)
        sig = [(t, "вортекс", side, {"сила": round(st_, 3), "перегрев": round(h_)}) for t, side, st_, h_ in ve]
        sig += [(t, "клингер", side, {"пик был": round(p1), "пик стал": round(p2)}) for t, side, p1, p2 in ke]
        # «оба»: вортекс и клингер в одну сторону рядом — событие на более позднем баре
        for tv, sv_, _, _ in ve:
            for tk, sk, _, _ in ke:
                if sv_ == sk and abs(tv - tk) <= a.pair * BAR:
                    sig.append((max(tv, tk), "оба", sv_, {}))
        seen = set()
        for t, kind, side, extra in sig:
            if t < d["since"] or (t, kind, side) in seen:
                continue
            seen.add((t, kind, side))
            px = c.get(t)
            if not px:
                continue
            tc = t + BAR                                   # сигнал известен на закрытии бара
            nxt, prv = opens_around(tc)
            if nxt - tc <= a.near * 60:
                cat, t_open = "перед стыком", nxt
            elif tc - prv <= a.near * 60:
                cat, t_open = "начало сессии", prv
            else:
                cat, t_open = "середина", None
            ans = oi_ans = None
            if cat == "перед стыком":
                ab = [c.get(t_open + k * BAR) for k in range(a.answer)]
                ab = [x for x in ab if x]
                if len(ab) >= max(1, a.answer - 1):
                    back = max(ab) >= px if side < 0 else min(ab) <= px
                    ans = ("откупили" if back else "не откупили") if side < 0 else ("продали" if back else "не продали")
                o0, o1 = oi.get(t_open - BAR), oi.get(t_open + (a.answer - 1) * BAR)
                if o0 and o1:
                    oi_ans = "ушёл" if pct(o0, o1) <= -1.0 else "на месте"
            elif cat == "начало сессии":
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
            lev, lev_off = leverage(oi, t)
            top = max([c[t - k * BAR] for k in range(12) if c.get(t - k * BAR)] or [px])
            res = {}
            for hrs in (6, 12):
                p1 = c.get(t + hrs * 2 * BAR)
                if p1:
                    mv = pct(px, p1) * (1 if side > 0 else -1)
                    b0, b1 = board_med.get(t), board_med.get(t + hrs * 2 * BAR)
                    rel = None if (b0 is None or b1 is None) else mv - (b1 - b0) * (1 if side > 0 else -1)
                    res[hrs] = (round(mv, 2), None if rel is None else round(rel, 2))
            out.append({"sym": s, "t": t, "kind": kind, "side": side, "px": px, "extra": extra,
                        "leader": t in win.get(s, set()), "cat": cat,
                        "sess": sess_name(t_open) if t_open else "", "ans": ans, "oi_ans": oi_ans,
                        "lev": lev, "lev_off": lev_off, "from_top": round(pct(top, px), 2), "res": res})
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


def main() -> int:
    ap = argparse.ArgumentParser(description="сигналы быстрых по линиям и стыки сессий у лидеров")
    ap.add_argument("--only", help="одна монета: её сигналы и стыки без доски")
    ap.add_argument("--days", type=int, default=4, help="окно сигналов, дней (по умолчанию 4)")
    ap.add_argument("--lead-min", type=float, default=20.0, help="ход за сутки для лидера, %% (20)")
    ap.add_argument("--lead-top", type=int, default=5, help="мест доски для лидера (5)")
    ap.add_argument("--tail", type=float, default=12.0, help="часов окна после последнего бара лидера (12)")
    ap.add_argument("--near", type=int, default=120, help="минут до/после открытия — «у стыка» (120)")
    ap.add_argument("--answer", type=int, default=4, help="ответных баров после открытия (4 = 2 ч)")
    ap.add_argument("--hit", type=float, default=2.0, help="попадание — ход в сторону сигнала за 12 ч, %% (2)")
    ap.add_argument("--list", type=int, default=40, help="сколько последних сигналов лидеров вывести строками")
    ap.add_argument("--vx-bars", type=int, default=3, help="баров подряд растёт линия вортекса (3)")
    ap.add_argument("--kl-gap", type=int, default=36, help="баров между пиками клингера одного хода (36 = 18 ч)")
    ap.add_argument("--pair", type=int, default=4, help="баров между вортексом и клингером для «оба» (4)")
    a = ap.parse_args()
    syms = ([x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in a.only.split(",")]
            if a.only else coins())
    if not syms:
        print("нет монет: output/near_move.json пуст — запусти после прогона или укажи --only")
        return 1
    need = (a.days + 2) * 48 + 60                     # окно + сутки на ход лидера + разогрев клингера
    since = int(datetime.now(UTC).timestamp()) - a.days * 86400
    data, closes = {}, {}
    for i, s in enumerate(syms, 1):
        try:
            b = bars_of(s, min(1500, need))
        except Exception as e:  # noqa: BLE001
            print(f"  {s}: свечи не получены — {type(e).__name__}: {e}")
            continue
        if len(b) < 80:
            continue
        data[s] = {"bars": b, "oi": oi_of(s), "since": since}
        closes[s] = {t: c for t, _, _, c, _ in b}
        if i % 25 == 0:
            print(f"  свечи: {i}/{len(syms)}")
    if not data:
        print("свечей нет")
        return 1
    board = board_median(closes)
    win = leader_windows(closes, a.lead_min, a.lead_top, a.tail, solo=bool(a.only))
    rows = analyse(data, board, win, a)
    lead = [r for r in rows if r["leader"]]
    rest = [r for r in rows if not r["leader"]]
    n_lead = sum(1 for s in win if win[s] and any(t >= since for t in win[s]))
    print(f"монет {len(data)} · дней {a.days} · лидеров в окне {n_lead} (ход за сутки ≥ {a.lead_min:g}%"
          + ("" if a.only else f", первые {a.lead_top} доски") + f") · сигналов у лидеров {len(lead)}, у остальных {len(rest)}")
    print("исход — ход от закрытия бара сигнала в сторону сигнала; «к доске» — минус медиана доски за то же окно; время UTC")
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
