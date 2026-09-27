#!/usr/bin/env python3
"""ПЛИТЫ СТАКАНА — ЧТО ДАЛЬШЕ С ЦЕНОЙ (27.09, владелец: «половина позиций в плюс, половина в минус при одних и тех же
условиях; снятие плиты само по себе разное — если рядом стоят ещё, снятие одной ничего не показывает, её могут переставить
ниже; съедание тоже смотря сколько рядом; какой размер плит к объёму или капитализации влияет; не мешать в одну кучу»).

Архив: получасовые снимки стакана фьючерса cq_v2/depth/*.jsonl (24.09–27.09, список плит — как в depth_fetch: плита = уровень
≥ ×8 медианы и ≥ 20K$, 24 крупнейшие на монету). Цена/оборот — свечи 30m Binance (свежие), интерес — cq_v2/hist30.

Событие = одна сторона (пол/потолок) одной монеты между двумя снимками подряд (≤ 40 мин). Плита ушла: «съели», если цена
между снимками дошла до неё (хай/лоу свечей), иначе «убрали». Классы:
  съели последнюю · съели, дальше стоит ещё (дальше по ходу есть плита)
  убрали всю опору · убрали одну из стопки (соседи остались) · переставили дальше от цены · переставили ближе к цене
  поставили первую (стороны не было) · поставили к стопке ближе к цене · поставили к стопке дальше от цены
Плиты меньше последней из 24 (могли выпасть из списка, а не уйти) не считаются.

Исход — ход цены через 30 мин, 1, 2, 6 ч от снимка; «к своей норме» = ход минус медиана хода этой же монеты за весь архив
на том же горизонте (монета сравнивается с собой). Разрезы: сторона, размер плиты к обороту суток / часа / интересу /
капитализации (квартили по самим событиям), зона (до 5% / дальше), монета в ходу/спит, доска 6 ч, сессия.
Сделки: закрытые сделки книг, открытые в окне архива, — события за сделку / против неё и итог сделки.

    .venv/bin/python claude/research/walls_effect.py        # → walls_effect.md, walls_events.json
"""
from __future__ import annotations

import json
import statistics as st
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import core_binance as cb  # noqa: E402

DEPTH = ROOT / "cq_v2" / "depth"
H30 = ROOT / "cq_v2" / "hist30"
OUT_MD = Path(__file__).with_name("walls_effect.md")
OUT_JS = Path(__file__).with_name("walls_events.json")
FAR = 30.0
SAME = 0.5 / 200            # та же плита: цена ± половина шага 0.5% (depth_fetch.fate)
NEAR = 5.0
HOR = (("30м", 1), ("1ч", 2), ("2ч", 4), ("6ч", 12))     # в получасовых барах
BAR = 1800_000
MSK = timezone(timedelta(hours=3))
SES = (("Сидней", 0, 9), ("Токио", 3, 12), ("Лондон", 10, 19), ("Нью-Йорк", 16, 25))   # book_fon.SES, часы UTC+3


def session(ms: int) -> str:
    h = datetime.fromtimestamp(ms / 1000, MSK).hour
    cur = None
    for name, a, b in SES:                   # последняя открывшаяся из идущих
        if a <= h < b or a <= h + 24 < b:
            cur = name
    return cur or "?"


def load_depth() -> dict[str, list[dict]]:
    out = {}
    for p in sorted(DEPTH.glob("*.jsonl")):
        rows = []
        for ln in p.open(encoding="utf-8"):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("kind", "perp") == "perp" and r.get("walls") is not None and r.get("mid"):
                rows.append(r)
        if len(rows) >= 10:
            rows.sort(key=lambda r: r["t"])
            out[rows[0]["sym"]] = rows
    return out


def load_bars(sym: str) -> dict[int, tuple]:
    kl = cb.get_klines(sym, "30m", 400)
    return {int(k[0]): (float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7])) for k in kl or []}


def bar_at(bars: dict, ms: int):
    return bars.get(ms // BAR * BAR)


def close_at(bars: dict, ms: int):
    b = bar_at(bars, ms)
    return b[3] if b else None


def load_oi(sym: str) -> dict[int, float]:
    p = H30 / (sym[:-4].lower() + ".json")
    try:
        return {int(r["t"]): float(r["oi"]) for r in json.loads(p.read_text()) if r.get("oi")}
    except (OSError, ValueError):
        return {}


def mcap_supply() -> dict:
    p = ROOT / "output" / "depth_mcap.json"
    try:
        cs = json.loads(p.read_text()).get("cs") or {}
        if cs:
            return cs
    except (OSError, ValueError):
        pass
    import urllib.request as u
    with u.urlopen("https://www.binance.com/bapi/asset/v2/public/asset-service/product/get-products?includeEtf=true", timeout=15) as r:
        rows = json.loads(r.read().decode()).get("data") or []
    return {str(x.get("b")): float(x["cs"]) for x in rows if x.get("cs")}


def supply_of(sym: str, cs: dict):
    b = sym[:-4]
    if b in cs:
        return cs[b], 1.0
    for pre, m in (("1000000", 1e6), ("1000", 1e3), ("1M", 1e6)):
        if b.startswith(pre) and b[len(pre):] in cs:
            return cs[b[len(pre):]], m
    return None, 1.0


def same(a, b):
    return abs(a["px"] - b["px"]) / max(1e-12, b["px"]) <= SAME


def events_for(sym: str, snaps: list[dict], bars: dict, oi: dict, cs: dict) -> list[dict]:
    out = []
    sup, mult = supply_of(sym, cs)
    for prev, cur in zip(snaps, snaps[1:]):
        if not (0 < cur["t"] - prev["t"] <= 40 * 60_000):
            continue
        cut = min((w["usd"] for w in cur["walls"]), default=0) if len(cur["walls"]) >= 24 else 0
        pcut = min((w["usd"] for w in prev["walls"]), default=0) if len(prev["walls"]) >= 24 else 0
        # путь цены между снимками — хай/лоу получасовок, задевших промежуток
        hs, ls = [], []
        for bt in range(prev["t"] // BAR * BAR, cur["t"] + 1, BAR):
            b = bars.get(bt)
            if b:
                hs.append(b[1]); ls.append(b[2])
        hi = max(hs + [cur["mid"], prev["mid"]]); lo = min(ls + [cur["mid"], prev["mid"]])
        for side in ("bid", "ask"):
            ok = lambda w: w["side"] == side and abs(w.get("dist_pct") or 0) <= FAR  # noqa: E731
            before = [w for w in prev["walls"] if ok(w)]
            after = [w for w in cur["walls"] if ok(w)]
            gone = [w for w in before if not any(same(w, x) for x in after) and w["usd"] >= cut]
            new = [w for w in after if not any(same(w, x) for x in before) and w["usd"] >= pcut]
            left = [w for w in before if any(same(w, x) for x in after)]
            if not gone and not new:
                continue
            crossed = (lambda w: hi >= w["px"]) if side == "ask" else (lambda w: lo <= w["px"])
            eaten = [g for g in gone if crossed(g)]
            removed = [g for g in gone if not crossed(g)]
            fwd = (lambda w, ref: w["px"] > ref) if side == "ask" else (lambda w, ref: w["px"] < ref)
            side_usd = sum(w["usd"] for w in before) or None
            if eaten:
                edge = max(g["px"] for g in eaten) if side == "ask" else min(g["px"] for g in eaten)
                nxt = sorted([w for w in after if fwd(w, edge)], key=lambda w: abs(w["px"] - cur["mid"]))
                cls = "съели, дальше стоит ещё" if nxt else "съели последнюю"
                hit = eaten
            elif removed:
                if new:
                    dn = min(abs(w["px"] / cur["mid"] - 1) for w in new)
                    dr = min(abs(w["px"] / prev["mid"] - 1) for w in removed)
                    cls = "переставили дальше от цены" if dn > dr else "переставили ближе к цене"
                elif left:
                    cls = "убрали одну из стопки"
                else:
                    cls = "убрали всю опору"
                hit = removed
                nxt = []
            else:
                if not before:
                    cls = "поставили первую"
                else:
                    dn = min(abs(w["px"] / cur["mid"] - 1) for w in new)
                    db = min(abs(w["px"] / cur["mid"] - 1) for w in before)
                    cls = "поставили к стопке ближе к цене" if dn < db else "поставили к стопке дальше от цены"
                hit = new
                nxt = []
            usd = sum(w["usd"] for w in hit)
            dist = min(abs(w.get("dist_pct") or 0) for w in hit)
            t = cur["t"]
            b0 = t // BAR * BAR
            qv24 = sum((bars.get(b0 - i * BAR) or (0, 0, 0, 0, 0))[4] for i in range(1, 49)) or None
            vol1h = sum((bars.get(b0 - i * BAR) or (0, 0, 0, 0, 0))[4] for i in range(1, 3)) or None
            oik = max((k for k in oi if k <= t), default=None)
            oi_usd = oi[oik] * cur["mid"] if oik and t - oik <= 2 * BAR else None
            mcap = sup * cur["mid"] / mult if sup else None
            lows = [(bars.get(b0 - i * BAR) or (0, 0, 1e18))[2] for i in range(1, 97)]
            mn48 = min([x for x in lows if x < 1e17] or [cur["mid"]])
            ret = {}
            for name, k in HOR:
                c = close_at(bars, t + k * BAR)
                if c and bars.get((t + k * BAR) // BAR * BAR + BAR):   # бар горизонта закрыт
                    ret[name] = round((c / cur["mid"] - 1) * 100, 3)
            out.append({
                "sym": sym, "t": t, "side": side, "cls": cls, "n_hit": len(hit), "n_before": len(before), "n_left": len(left),
                "usd": usd, "dist": dist, "share_side": round(usd / side_usd, 3) if side_usd and hit is not new else None,
                "next_dist": round(abs(nxt[0]["px"] / cur["mid"] - 1) * 100, 2) if nxt else None,
                "next_usd": nxt[0]["usd"] if nxt else None, "mid": cur["mid"],
                "r_qv24": usd / qv24 * 100 if qv24 else None, "r_vol1h": usd / vol1h * 100 if vol1h else None,
                "r_oi": usd / oi_usd * 100 if oi_usd else None, "r_mcap": usd / mcap * 100 if mcap else None,
                "run48": round((cur["mid"] / mn48 - 1) * 100, 1), "ses": session(t), "ret": ret,
            })
    return out


def base_ret(sym: str, snaps: list[dict], bars: dict) -> dict:
    """медиана хода монеты на каждом горизонте по всем её снимкам архива — её собственная норма"""
    out = {}
    for name, k in HOR:
        v = []
        for s in snaps:
            c = close_at(bars, s["t"] + k * BAR)
            if c and bars.get((s["t"] + k * BAR) // BAR * BAR + BAR):
                v.append((c / s["mid"] - 1) * 100)
        out[name] = st.median(v) if v else 0.0
    return out


def board6(all_bars: dict) -> dict[int, float]:
    """медиана хода за 6 ч по монетам архива на каждой получасовке (доска по 88 монетам, не по всей выборке)"""
    ts = sorted({t for b in all_bars.values() for t in b})
    out = {}
    for t in ts:
        v = []
        for b in all_bars.values():
            a, z = b.get(t - 12 * BAR), b.get(t)
            if a and z and a[3]:
                v.append((z[3] / a[3] - 1) * 100)
        if len(v) >= 20:
            out[t] = st.median(v)
    return out


def q_edges(vals: list[float]) -> list[float]:
    v = sorted(x for x in vals if x is not None)
    if len(v) < 8:
        return []
    return [v[len(v) // 4], v[len(v) // 2], v[3 * len(v) // 4]]


def q_of(x, edges) -> str | None:
    if x is None or not edges:
        return None
    i = sum(1 for e in edges if x > e)
    return ["Q1 мелкие", "Q2", "Q3", "Q4 крупные"][i]


def stat(evs: list[dict], h: str) -> tuple | None:
    x = [e["ex"][h] for e in evs if h in e["ex"]]
    if not x:
        return None
    up = sum(1 for v in x if v > 0)
    return len(x), round(up / len(x) * 100), round(st.median(x), 2)


def fmt(evs: list[dict]) -> str:
    cells = []
    for h, _ in HOR:
        s = stat(evs, h)
        cells.append(f"{s[2]:+.2f}% · {s[1]}% (n{s[0]})" if s else "—")
    return " | ".join(cells)


def trades_part(evs_by_sym: dict, t_lo: int, t_hi: int) -> list[str]:
    """закрытые сделки книг, открытые в окне архива: события за / против за время сделки и итог"""
    out = []
    for_ = {  # для лонга; у шорта наоборот
        ("bid", "поставили первую"): 1, ("bid", "поставили к стопке ближе к цене"): 1, ("bid", "поставили к стопке дальше от цены"): 1,
        ("bid", "съели последнюю"): -1, ("bid", "съели, дальше стоит ещё"): -1, ("bid", "убрали всю опору"): -1,
        ("bid", "убрали одну из стопки"): -1, ("bid", "переставили дальше от цены"): -1, ("bid", "переставили ближе к цене"): 1,
        ("ask", "поставили первую"): -1, ("ask", "поставили к стопке ближе к цене"): -1, ("ask", "поставили к стопке дальше от цены"): -1,
        ("ask", "съели последнюю"): 1, ("ask", "съели, дальше стоит ещё"): 1, ("ask", "убрали всю опору"): 1,
        ("ask", "убрали одну из стопки"): 1, ("ask", "переставили дальше от цены"): 1, ("ask", "переставили ближе к цене"): -1,
    }
    trades = []
    for p in sorted((ROOT / "output").glob("paper_*.jsonl")):
        book = p.stem[len("paper_"):]
        for ln in p.open(encoding="utf-8"):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if not str(r.get("kind", "")).startswith("exit") or r.get("result_pct") is None:
                continue
            sym = r.get("sym")
            op = r.get("opened_at") or (r.get("t") / 1000 if r.get("t") else None)
            ex = r.get("at")
            if not (sym in evs_by_sym and op and ex):
                continue
            op, ex = int(op * 1000), int(ex * 1000)
            if op < t_lo or op > t_hi:
                continue
            side = r.get("side") or (-1 if book == "end" else (-1 if r.get("kind") == "exit_short" else 1))
            trades.append({"book": book, "sym": sym, "side": side, "op": op, "ex": ex, "res": float(r["result_pct"])})
    out.append(f"Сделок в окне архива с монетами архива: {len(trades)} (книги: "
               + ", ".join(f"{b} {n}" for b, n in sorted(_count(t['book'] for t in trades).items(), key=lambda x: -x[1])) + ")")
    if not trades:
        return out
    groups = defaultdict(list)
    for tr in trades:
        evs = [e for e in evs_by_sym[tr["sym"]] if tr["op"] < e["t"] < tr["ex"]]
        f = sum(1 for e in evs if for_.get((e["side"], e["cls"]), 0) * tr["side"] > 0)
        a = sum(1 for e in evs if for_.get((e["side"], e["cls"]), 0) * tr["side"] < 0)
        key = "без событий" if not evs else ("против больше" if a > f else "за больше" if f > a else "поровну")
        groups[key].append(tr)
        for e in evs:
            k = ("ЗА" if for_.get((e["side"], e["cls"]), 0) * tr["side"] > 0 else "ПРОТИВ") + f" · {e['side']} · {e['cls']}"
            groups[k].append(tr)
    out.append("")
    out.append("| что было за время сделки | сделок | в плюс | медиана итога |")
    out.append("|---|---|---|---|")
    for k in ["без событий", "за больше", "поровну", "против больше"] + sorted(k for k in groups if "·" in k):
        g = groups.get(k)
        if not g:
            continue
        uniq = {(x["book"], x["sym"], x["op"]): x for x in g}.values()
        n = len(uniq)
        out.append(f"| {k} | {n} | {round(sum(1 for x in uniq if x['res'] > 0) / n * 100)}% | {st.median([x['res'] for x in uniq]):+.2f}% |")
    return out


def _count(it):
    c = defaultdict(int)
    for x in it:
        c[x] += 1
    return c


def main() -> int:
    t0 = time.time()
    depth = load_depth()
    cs = mcap_supply()
    all_bars, evs, base = {}, [], {}
    for sym, snaps in depth.items():
        bars = load_bars(sym)
        if not bars:
            continue
        all_bars[sym] = bars
        base[sym] = base_ret(sym, snaps, bars)
        evs += events_for(sym, snaps, bars, load_oi(sym), cs)
    b6 = board6(all_bars)
    for e in evs:
        e["ex"] = {h: round(v - base[e["sym"]][h], 3) for h, v in e["ret"].items()}
        bt = e["t"] // BAR * BAR
        e["board6"] = b6.get(bt) if bt in b6 else b6.get(bt - BAR)
        e["state"] = "в ходу ≥+40%/48ч" if e["run48"] >= 40 else "спит <+20%" if e["run48"] < 20 else "между"
        e["zone"] = "до 5%" if e["dist"] < NEAR else "дальше 5%"
    edges = {k: q_edges([e[k] for e in evs]) for k in ("r_qv24", "r_vol1h", "r_oi", "r_mcap")}
    for e in evs:
        for k in edges:
            e["q_" + k] = q_of(e[k], edges[k])
    OUT_JS.write_text(json.dumps(evs, ensure_ascii=False))
    t_lo = min(s[0]["t"] for s in depth.values())
    t_hi = max(s[-1]["t"] for s in depth.values())
    L = [f"# Плиты стакана — что дальше с ценой ({datetime.now(MSK):%d.%m %H:%M})", "",
         f"Архив: {len(depth)} монет, получасовые снимки фьючерса {datetime.fromtimestamp(t_lo / 1000, MSK):%d.%m %H:%M} – "
         f"{datetime.fromtimestamp(t_hi / 1000, MSK):%d.%m %H:%M}; событий (сторона × пара снимков): {len(evs)}.",
         "В клетке: медиана хода К СВОЕЙ НОРМЕ (ход минус медиана хода этой монеты на том же горизонте) · доля событий, где ход выше нормы · n.",
         "Для пола (bid) ожидание «опора ушла» — вниз, для потолка (ask) «путь свободен» — вверх: читать по стороне.",
         "Допущения: 3.5 дня (одни выходные), шаг снимка 30 мин (что было внутри получаса — не видно), только фьючерсный стакан, "
         "24 крупнейшие плиты на монету, доска — медиана по монетам архива, капитализация — нынешнее обращение × цена.", "",
         "Квартили размера (граница Q1|Q2|Q3|Q4, % плиты к базе): "
         + "; ".join(f"{k[2:]}: " + " | ".join(f"{x:.3g}" for x in v) for k, v in edges.items() if v), ""]
    H = "| " + " | ".join(h for h, _ in HOR) + " |"
    classes = ["съели последнюю", "съели, дальше стоит ещё", "убрали всю опору", "убрали одну из стопки",
               "переставили дальше от цены", "переставили ближе к цене", "поставили первую",
               "поставили к стопке ближе к цене", "поставили к стопке дальше от цены"]
    L += ["## 1. Классы × сторона", "", "| сторона | класс " + H, "|---|---" + "|---" * len(HOR) + "|"]
    for side in ("bid", "ask"):
        for c in classes:
            g = [e for e in evs if e["side"] == side and e["cls"] == c]
            if g:
                L.append(f"| {'пол' if side == 'bid' else 'потолок'} | {c} | {fmt(g)} |")
    L.append("")
    cuts = [("размер к обороту суток", "q_r_qv24"), ("размер к обороту часа", "q_r_vol1h"), ("размер к интересу", "q_r_oi"),
            ("размер к капитализации", "q_r_mcap"), ("зона", "zone"), ("монета", "state"), ("сессия", "ses"),
            ("доска 6 ч", "_b6")]
    for e in evs:
        e["_b6"] = None if e["board6"] is None else ("доска6 > 0" if e["board6"] > 0 else "доска6 ≤ 0")
    L += ["## 2. Разрезы внутри каждого класса (только где n ≥ 20)", ""]
    for side in ("bid", "ask"):
        for c in classes:
            g = [e for e in evs if e["side"] == side and e["cls"] == c]
            if len(g) < 20:
                continue
            L += [f"### {'пол' if side == 'bid' else 'потолок'} · {c} (n {len(g)})", "", "| разрез | группа " + H,
                  "|---|---" + "|---" * len(HOR) + "|"]
            for title, key in cuts:
                vals = sorted({e[key] for e in g if e.get(key)})
                for v in vals:
                    sub = [e for e in g if e.get(key) == v]
                    if len(sub) >= 5:
                        L.append(f"| {title} | {v} | {fmt(sub)} |")
            L.append("")
    # съели: сколько до следующей плиты по ходу
    L += ["## 3. «Съели, дальше стоит ещё» — по расстоянию до следующей плиты", "", "| сторона | до следующей " + H,
          "|---|---" + "|---" * len(HOR) + "|"]
    for side in ("bid", "ask"):
        g = [e for e in evs if e["side"] == side and e["cls"] == "съели, дальше стоит ещё" and e["next_dist"] is not None]
        ed = q_edges([e["next_dist"] for e in g])
        for q in ("Q1 мелкие", "Q2", "Q3", "Q4 крупные"):
            sub = [e for e in g if q_of(e["next_dist"], ed) == q]
            if sub:
                lab = {"Q1 мелкие": "ближе всего", "Q4 крупные": "дальше всего"}.get(q, q)
                L.append(f"| {'пол' if side == 'bid' else 'потолок'} | {lab} ({' | '.join(f'{x:.1f}%' for x in ed)}) | {fmt(sub)} |")
    L.append("")
    # по монетам: где событий больше всего — монета против себя
    L += ["## 4. По монетам (≥ 15 событий) — класс с самым сильным ходом к норме за 1 ч, n ≥ 5", ""]
    by = defaultdict(list)
    for e in evs:
        by[e["sym"]].append(e)
    for sym, g in sorted(by.items(), key=lambda x: -len(x[1])):
        if len(g) < 15:
            continue
        best = []
        for side in ("bid", "ask"):
            for c in classes:
                sub = [e for e in g if e["side"] == side and e["cls"] == c]
                s = stat(sub, "1ч")
                if s and s[0] >= 5:
                    best.append((abs(s[2]), f"{'пол' if side == 'bid' else 'потолок'} · {c}: {s[2]:+.2f}% · {s[1]}% (n{s[0]})"))
        best.sort(reverse=True)
        if best:
            L.append(f"- {sym[:-4]} ({len(g)}): " + "; ".join(x[1] for x in best[:2]))
    L += ["", "## 5. Сделки книг и события стакана за время сделки", "",
          "За/против: для лонга «за» — поставили пол, съели или убрали потолок, пол переставили ближе; «против» — пол съели/убрали/"
          "переставили дальше, поставили потолок. У шорта наоборот. Длинные сделки собирают больше событий — учитывать.", ""]
    evs_by_sym = defaultdict(list)
    for e in evs:
        evs_by_sym[e["sym"]].append(e)
    L += trades_part(evs_by_sym, t_lo, t_hi)
    L += ["", f"_Посчитано за {time.time() - t0:.0f} с. События — walls_events.json._"]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:40]))
    print(f"… → {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
