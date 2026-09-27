#!/usr/bin/env python3
"""БЫСТРЫЕ СДЕЛКИ ВНУТРИ ОДНОЙ СЕССИИ (27.09, владелец: «каждая сессия поднимает и забирает перед следующей, за исключением очень
малого количества монет; контекст одной сессии — это условия; сессия сначала ждёт, набирает, много сквизов, так как предыдущая уходит —
± час после открытия подождать; вечно расти во время сессии ничего не будет — открывают позиции и потом закрывают»; «разбей по дням —
пт сб вс может быть лучше, чем пн вт»).

Окна сессий (UTC+3, от открытия до открытия следующей; стыки владельца 21/0/7/13 UTC): Сидней 00–03, Токио 03–10, Лондон 10–16,
Нью-Йорк 16–24. Первый час каждой — «ждём».

А. Доска (cq_v2/hist30, 158 монет, 30 дн, получасовки + свежие свечи до сейчас): медиана хода монет от цены открытия сессии —
   первый час, подъём после часа до максимума сессии, что осталось к открытию следующей. По сессиям и по дням недели.
Б. Сделки: всплеск как в fast_tier (3м бар ≥ ×5 медианы 30 прошлых, ≥ 50K$, бар ≥ +1% → лонг по закрытию бара, +5 / −5, комиссия 0.1%;
   монета — одна позиция, после выхода пауза 2 ч; всплеск при интересе за час ≥ +6% бот переворачивает в шорт — здесь не берётся)
   на cq_v2/hist3m (144 лидера, 14 дн). Ворота: после часа ожидания; медиана сессии > 0 и выше, чем получасом раньше.
   Выходы: срок 2 ч (как сейчас) / до открытия следующей сессии / за час до него.
В. Живые сделки «пробуждения» и «всплеск/вынос» 27.09: что прошло бы через ворота.

    .venv/bin/python claude/research/session_fast.py      # → session_fast.md
"""
from __future__ import annotations

import json
import statistics as st
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import core_binance as cb  # noqa: E402

H30, H3 = ROOT / "cq_v2" / "hist30", ROOT / "cq_v2" / "hist3m"
OUT = Path(__file__).with_name("session_fast.md")
MSK = timezone(timedelta(hours=3))
HB, B3 = 1800_000, 180_000
WIN = (("Сидней", 0, 3), ("Токио", 3, 10), ("Лондон", 10, 16), ("Нью-Йорк", 16, 24))
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
X, MINQ, PCT, TP, SL, FEE, FLIP = 5.0, 50_000, 0.01, 0.05, 0.05, 0.001, 6.0


def sess(ms: int):
    """(имя, открытие ms, следующее открытие ms, день недели открытия)"""
    d = datetime.fromtimestamp(ms / 1000, MSK)
    for name, a, b in WIN:
        if a <= d.hour < b:
            o = d.replace(hour=a, minute=0, second=0, microsecond=0)
            return name, int(o.timestamp() * 1000), int((o + timedelta(hours=b - a)).timestamp() * 1000), WD[o.weekday()]
    raise ValueError


# ── доска ──
def load_board() -> dict[str, dict[int, tuple]]:
    out = {}
    for p in sorted(H30.glob("*.json")):
        try:
            rows = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        out[p.stem.upper() + "USDT"] = {int(r["t"]): (float(r.get("o") or r["px"]), float(r["px"])) for r in rows if r.get("px")}

    def fresh(sym):
        return sym, cb.get_klines(sym, "30m", 100)
    with ThreadPoolExecutor(6) as ex:
        for sym, kl in ex.map(fresh, list(out)):
            for k in kl or []:
                out[sym][int(k[0])] = (float(k[1]), float(k[4]))
    return out


class Board:
    def __init__(self, bars):
        self.bars = bars
        self.cache: dict[tuple, float | None] = {}

    def med(self, s_open: int, bar_t: int):
        """медиана хода монет от открытия сессии до закрытия получасовки bar_t"""
        k = (s_open, bar_t)
        if k not in self.cache:
            v = []
            for b in self.bars.values():
                o, z = b.get(s_open), b.get(bar_t)
                if o and z and o[0]:
                    v.append((z[1] / o[0] - 1) * 100)
            self.cache[k] = st.median(v) if len(v) >= 30 else None
        return self.cache[k]

    def state(self, t_ms: int):
        """на момент t: медиана сессии по последней закрытой получасовке и получасом раньше"""
        name, s_open, _, _ = sess(t_ms)
        b = t_ms // HB * HB - HB
        if b < s_open:
            return None, None
        m = self.med(s_open, b)
        mp = self.med(s_open, b - HB) if b - HB >= s_open else 0.0
        return m, mp


def part_a(bd: Board) -> list[str]:
    ts = sorted({t for b in bd.bars.values() for t in b})
    lo, hi = ts[0], ts[-1]
    rows = []
    t = (lo // 3600_000 + 1) * 3600_000
    seen = set()
    while t < hi:
        name, so, nx, wd = sess(t)
        if so not in seen and so >= lo and nx - HB <= hi:
            seen.add(so)
            m1 = bd.med(so, so + HB)                               # к концу первого часа (две получасовки: so и so+30)
            path = [bd.med(so, b) for b in range(so + 2 * HB, nx, HB)]
            path = [x for x in path if x is not None]
            mend = bd.med(so, nx - HB)
            if m1 is not None and path and mend is not None:
                rows.append(dict(name=name, wd=wd, first=m1, rise=max(path) - m1, back=mend - max(path), net=mend - m1, t=so))
        t += 3600_000
    L = [f"## А. Доска по сессиям ({len(rows)} сессий, {datetime.fromtimestamp(lo / 1000, MSK):%d.%m} – {datetime.fromtimestamp(hi / 1000, MSK):%d.%m}, "
         f"{len(bd.bars)} монет, медиана хода монет от цены открытия сессии, %)", "",
         "первый час — медиана к концу первого часа; подъём — от конца первого часа до максимума сессии; отдали — от максимума до конца сессии; "
         "итог после часа — конец сессии минус конец первого часа (в скобках доля сессий с итогом > 0).", "",
         "| сессия | n | первый час (доля < 0) | подъём после часа | отдали к концу | итог после часа (> 0) |", "|---|---|---|---|---|---|"]

    def line(lab, g):
        return (f"| {lab} | {len(g)} | {st.median([r['first'] for r in g]):+.2f} ({round(sum(r['first'] < 0 for r in g) / len(g) * 100)}%) | "
                f"{st.median([r['rise'] for r in g]):+.2f} | {st.median([r['back'] for r in g]):+.2f} | "
                f"{st.median([r['net'] for r in g]):+.2f} ({round(sum(r['net'] > 0 for r in g) / len(g) * 100)}%) |")
    for name, _, _ in WIN:
        g = [r for r in rows if r["name"] == name]
        if g:
            L.append(line(name, g))
    L.append(line("все", rows))
    L += ["", "По дням недели (день — по открытию сессии; итог после часа, медиана и доля > 0):", "",
          "| день | " + " | ".join(n for n, _, _ in WIN) + " | все |", "|---|" + "---|" * (len(WIN) + 1)]
    for wd in WD:
        cells = []
        for name, _, _ in WIN + (("все", 0, 0),):
            g = [r for r in rows if r["wd"] == wd and (name == "все" or r["name"] == name)]
            cells.append(f"{st.median([r['net'] for r in g]):+.2f} ({sum(r['net'] > 0 for r in g)}/{len(g)})" if g else "—")
        L.append(f"| {wd} | " + " | ".join(cells) + " |")
    return L


# ── сделки ──
def spikes() -> list[dict]:
    out = []
    for p in sorted(H3.glob("*.json")):
        if p.stem.startswith("_"):
            continue
        try:
            k = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        sym = p.stem.upper() + "USDT"
        qv = [float(x[5]) for x in k]
        c = [float(x[4]) for x in k]
        oi = [float(x[7] or 0) for x in k]
        for i in range(31, len(k)):
            med = st.median(qv[i - 30:i])
            if med <= 0 or qv[i] < X * med or qv[i] < MINQ or c[i] / c[i - 1] - 1 < PCT:
                continue
            oi1h = (oi[i] / oi[i - 20] - 1) * 100 if oi[i - 20] else None
            out.append(dict(sym=sym, i=i, t=int(k[i][0]) + B3, px=c[i], oi1h=oi1h, k=k))
    return out


def run(sp: list[dict], bd: Board, gate, exit_mode: str) -> list[dict]:
    """сделки по порядку времени; одна позиция на монету, пауза 2 ч после выхода"""
    busy: dict[str, int] = {}
    res = []
    for s in sorted(sp, key=lambda x: x["t"]):
        if s["oi1h"] is not None and s["oi1h"] >= FLIP:
            continue
        if busy.get(s["sym"], 0) > s["t"]:
            continue
        name, so, nx, wd = sess(s["t"])
        m, mp = bd.state(s["t"])
        if not gate(s, so, m, mp):
            continue
        end = s["t"] + 2 * 3600_000 if exit_mode == "2ч" else nx if exit_mode == "до следующей" else nx - 3600_000
        if end <= s["t"]:
            continue
        k, e = s["k"], s["px"]
        r, why, j = None, None, s["i"] + 1
        while j < len(k) and int(k[j][0]) + B3 <= end:
            if float(k[j][3]) <= e * (1 - SL):
                r, why = -SL, "стоп"; break
            if float(k[j][2]) >= e * (1 + TP):
                r, why = TP, "цель"; break
            j += 1
        if r is None:
            if j >= len(k) or j - 1 <= s["i"]:
                continue                                             # архив кончился раньше срока
            r, why = float(k[j - 1][4]) / e - 1, "срок"
        r -= FEE
        res.append(dict(sym=s["sym"], t=s["t"], ses=name, wd=wd, r=r * 100, why=why, m=m))
        busy[s["sym"]] = int(k[min(j, len(k) - 1)][0]) + 2 * 3600_000
    return res


def summ(g: list[dict]) -> str:
    if not g:
        return "—"
    n = len(g)
    return f"{n} · {round(sum(x['r'] > 0 for x in g) / n * 100)}% · {sum(x['r'] for x in g):+.1f}% · {sum(x['r'] for x in g) * 5:+.0f}$"


def part_b(bd: Board) -> tuple[list[str], dict]:
    sp = spikes()
    gates = {
        "все всплески (как сейчас)": lambda s, so, m, mp: True,
        "после часа ожидания": lambda s, so, m, mp: s["t"] - so >= 3600_000,
        "медиана сессии растёт": lambda s, so, m, mp: m is not None and m > 0 and m > mp,
        "час ожидания + медиана растёт": lambda s, so, m, mp: s["t"] - so >= 3600_000 and m is not None and m > 0 and m > mp,
        "в час ожидания": lambda s, so, m, mp: s["t"] - so < 3600_000,
        "после часа, медиана НЕ растёт": lambda s, so, m, mp: s["t"] - so >= 3600_000 and not (m is not None and m > 0 and m > mp),
    }
    runs = {}
    for gname, g in gates.items():
        for ex in ("2ч", "до следующей", "за час до следующей"):
            runs[(gname, ex)] = run(sp, bd, g, ex)
    t_lo = min(s["t"] for s in sp); t_hi = max(s["t"] for s in sp)
    L = ["", f"## Б. Всплески на 144 лидерах ({len(sp)} всплесков, {datetime.fromtimestamp(t_lo / 1000, MSK):%d.%m} – "
         f"{datetime.fromtimestamp(t_hi / 1000, MSK):%d.%m}; клетка: сделок · в плюс · сумма % · $ при 500 $)", "",
         "Допущение: лидеры — монеты, которые потом ходили, итог завышен; сравнивать группы между собой.", "",
         "| ворота | выход 2 ч | до следующей сессии | за час до следующей |", "|---|---|---|---|"]
    for gname in gates:
        L.append(f"| {gname} | " + " | ".join(summ(runs[(gname, ex)]) for ex in ("2ч", "до следующей", "за час до следующей")) + " |")
    for gname in ("все всплески (как сейчас)", "час ожидания + медиана растёт"):
        for ex in ("2ч", "до следующей"):
            r = runs[(gname, ex)]
            L += ["", f"### {gname} · выход {ex} — по сессиям и дням", "", "| день | " + " | ".join(n for n, _, _ in WIN) + " | все |",
                  "|---|" + "---|" * (len(WIN) + 1)]
            for wd in WD + ["все"]:
                cells = [summ([x for x in r if (wd == "все" or x["wd"] == wd) and (n == "все" or x["ses"] == n)]) for n, _, _ in WIN + (("все", 0, 0),)]
                L.append(f"| {wd} | " + " | ".join(cells) + " |")
    return L, runs


def part_c(bd: Board) -> list[str]:
    t0 = datetime(2026, 9, 27, 7, 15, tzinfo=MSK).timestamp()
    tr = []
    for f in ("paper_wake.jsonl", "paper_fast3.jsonl"):
        for ln in (ROOT / "output" / f).open(encoding="utf-8"):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if str(r.get("kind", "")).startswith("exit") and r.get("opened_at") and r["opened_at"] >= t0 and r.get("side") == 1:
                tr.append(dict(book=r["book"], sym=r["sym"], t=int(r["opened_at"] * 1000), r=float(r["result_pct"])))
    L = ["", f"## В. Живые лонги трёхминутных книг 27.09 с 07:15 ({len(tr)} закрытых)", "",
         "| группа | сделок · в плюс · сумма % · $ |", "|---|---|"]
    groups = defaultdict(list)
    for x in tr:
        name, so, nx, wd = sess(x["t"])
        m, mp = bd.state(x["t"])
        wait = x["t"] - so < 3600_000
        up = m is not None and m > 0 and m > mp
        x["ses"] = name
        groups["все"].append(x)
        groups["в час ожидания" if wait else "после часа"].append(x)
        groups["медиана сессии растёт" if up else "медиана не растёт"].append(x)
        if not wait and up:
            groups["оба условия (прошли бы)"].append(x)
        groups[f"сессия {name}"].append(x)
    for k in ["все", "в час ожидания", "после часа", "медиана сессии растёт", "медиана не растёт", "оба условия (прошли бы)"] + \
            [f"сессия {n}" for n, _, _ in WIN]:
        L.append(f"| {k} | {summ(groups.get(k, []))} |")
    return L


def exit_at(s: dict, end: int):
    """выход по цели/стопу до end, иначе по закрытию последнего бара до end; None — архив кончился раньше"""
    k, e, j = s["k"], s["px"], s["i"] + 1
    while j < len(k) and int(k[j][0]) + B3 <= end:
        if float(k[j][3]) <= e * (1 - SL):
            return -SL - FEE
        if float(k[j][2]) >= e * (1 + TP):
            return TP - FEE
        j += 1
    if j >= len(k) or j - 1 <= s["i"]:
        return None
    return float(k[j - 1][4]) / e - 1 - FEE


def part_d() -> list[str]:
    """27.09 владелец: «не уверен, что выход ровно на открытии следующей — а если за час или за 2? кроме перехода Сидней → Токио,
    там чаще продолжение». Один набор входов на все варианты выхода: первый всплеск монеты в сессии после часа ожидания и раньше
    самого раннего выхода этой сессии. Сделки независимы (пересечения по монете не режем)."""
    H = 3600_000
    var = {
        "Сидней": [("за 1 ч", -H), ("на открытии Токио", 0), ("+1 ч в Токио", H), ("через весь Токио (10:00)", 7 * H)],
        "Токио": [("за 2 ч", -2 * H), ("за 1 ч", -H), ("на открытии Лондона", 0), ("+1 ч в Лондоне", H)],
        "Лондон": [("за 2 ч", -2 * H), ("за 1 ч", -H), ("на открытии НЙ", 0), ("+1 ч в НЙ", H)],
        "Нью-Йорк": [("за 2 ч", -2 * H), ("за 1 ч", -H), ("на открытии Сиднея", 0), ("+1 ч в Сиднее", H)],
    }
    first: dict[tuple, dict] = {}
    late: dict[tuple, dict] = {}
    for s in sorted(spikes(), key=lambda x: x["t"]):
        if s["oi1h"] is not None and s["oi1h"] >= FLIP:
            continue
        name, so, nx, wd = sess(s["t"])
        if s["t"] - so < H:
            continue
        s.update(ses=name, so=so, nx=nx, wd=wd)
        cut = nx + min(d for _, d in var[name])
        key = (s["sym"], so)
        if s["t"] < cut:
            first.setdefault(key, s)
        elif s["t"] >= nx - 2 * H:
            late.setdefault(key, s)
    L = ["", "## Г. Когда выходить — один набор входов на все варианты (первый всплеск монеты в сессии после часа ожидания и раньше самого "
         "раннего выхода; клетка: сделок · в плюс · сумма % · $ при 500 $)", ""]
    for name, vs in var.items():
        tr = [s for s in first.values() if s["ses"] == name]
        res = {lab: [] for lab, _ in vs}
        for s in tr:
            rr = [exit_at(s, s["nx"] + d) for _, d in vs]
            if any(r is None for r in rr):
                continue                                   # все варианты по одной сделке — или никакой
            for (lab, _), r in zip(vs, rr):
                res[lab].append(dict(r=r * 100, wd=s["wd"]))
        L += [f"### {name} → следующая ({len(next(iter(res.values())))} сделок)", "", "| день | " + " | ".join(lab for lab, _ in vs) + " |",
              "|---|" + "---|" * len(vs)]
        for wd in WD + ["все"]:
            L.append(f"| {wd} | " + " | ".join(summ([x for x in res[lab] if wd == 'все' or x['wd'] == wd]) for lab, _ in vs) + " |")
        L.append("")
    L += ["### Входы в последние 2 ч сессии (после часа ожидания) — входить ли вообще", "",
          "| сессия | выход на открытии следующей | +1 ч в следующей |", "|---|---|---|"]
    for name in var:
        tr = [s for s in late.values() if s["ses"] == name]
        a, b = [], []
        for s in tr:
            ra, rb = exit_at(s, s["nx"]), exit_at(s, s["nx"] + H)
            if ra is None or rb is None:
                continue
            a.append(dict(r=ra * 100)); b.append(dict(r=rb * 100))
        L.append(f"| {name} | {summ(a)} | {summ(b)} |")
    return L


def main() -> int:
    t0 = time.time()
    bd = Board(load_board())
    L = [f"# Быстрые сделки внутри сессии ({datetime.now(MSK):%d.%m %H:%M})", "",
         "Окна (UTC+3): Сидней 00–03, Токио 03–10, Лондон 10–16, Нью-Йорк 16–24; первый час — ожидание.", ""]
    L += part_a(bd)
    lb, _ = part_b(bd)
    L += lb
    L += part_c(bd)
    L += part_d()
    L += ["", f"_Посчитано за {time.time() - t0:.0f} с._"]
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
