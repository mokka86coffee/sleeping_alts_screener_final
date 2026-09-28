#!/usr/bin/env python3
"""МЕТКИ СЛЕЖКИ КАК СИГНАЛЫ (28.09, владелец: «ты следил за несколькими монетами — какие из стратегий на них бы сработали»; «у тебя была слежка
за ними каждые 3 минуты»; «делай, да»).

Строки coin_watch.py (SEI с 04:00 каждые 3 мин, SEI/ONE/PLAY с 10:36 раз в 10 мин) достаются из истории чата (отдельного журнала не было).
Каждая метка ⚑ — сигнал в сторону, которую она значит по нашим правилам:
  «цена растёт, интерес падает — закрываются» → шорт (конец хода); «толпа — максимум суток» → шорт; «R21 вынос шортов максимум суток» → шорт;
  «плита сверху крупнейшая» → шорт; «новый максимум 7 дн» → лонг (продолжение); «цена падает, интерес растёт — набирают против» → лонг (топливо);
  «плита снизу крупнейшая» → лонг; итоги «вниз» (с 16:59, из ответов владельцу) → шорт.
Исход по 3m свечам Binance: что раньше — +5% или −5% в сторону сигнала за 4 ч (оба в одной свече — считаем стоп); иначе — итог через 4 ч
(или сейчас, если 4 ч не прошло — помечено). Отдельно — метки «на шуме» (цена за 3 мин и интерес за 5 мин по модулю ≤ 0.1%) и первая метка серии
(та же метка той же монеты не раньше чем через 30 мин).

    .venv/bin/python claude/research/watch_flags.py        # → watch_flags.md
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core_http import get_json  # noqa: E402

L = timezone(timedelta(hours=3))
OUT = Path(__file__).with_name("watch_flags.md")
TR = Path.home() / ".claude/projects/-Users-evgenijminko-Work-random-python/306d2849-9ba7-438a-ba8b-3aa0df8511d4.jsonl"
DAY = datetime(2026, 9, 28, tzinfo=L)
LINE = re.compile(r"(\d\d:\d\d) (SEI|ONE|PLAY) ([0-9.]+) · 3м ([+\-−]?[0-9.]+)%.*?интерес 1ч [^/]*/ 5м ([+\-−]?[0-9.]+)%(.*?)(?=\\n\d\d:\d\d (?:SEI|ONE|PLAY) |\"|$)")
FLAGS = [("закрываются", "цена растёт, интерес падает — закрываются", -1), ("максимум суток 2", "толпа — максимум суток", -1),
         ("R21", "вынос шортов — максимум суток (R21)", -1), ("плита сверху", "плита сверху — крупнейшая за сутки", -1),
         ("максимум 7 дн", "новый максимум 7 дн", 1), ("набирают против", "цена падает, интерес растёт — набирают против", 1),
         ("плита снизу", "плита снизу — крупнейшая за сутки", 1)]
# итоги «вниз» из ответов владельцу (10-мин проверки с 16:59): SEI и PLAY — вниз всё время, ONE — вниз 17:19–17:49
VERDICT = [(c, t) for c in ("SEI", "PLAY") for t in ("16:59", "17:09", "17:19", "17:30", "17:40", "17:49", "17:59")] + \
          [("ONE", t) for t in ("17:19", "17:31", "17:40", "17:49")]
num = lambda s: float(s.replace("−", "-"))  # noqa: E731


def main() -> int:
    raw = TR.read_text(encoding="utf-8", errors="ignore")
    obs = {}
    for m in LINE.finditer(raw):
        t, c, px, p3, oi5, tail = m.groups()
        k = (c, t)
        flags = [(lab, sd) for key, lab, sd in FLAGS if "⚑" in tail and key in tail]
        if k not in obs or len(flags) > len(obs[k]["flags"]):
            obs[k] = dict(c=c, t=t, px=float(px), p3=num(p3), oi5=num(oi5), flags=flags)
    sig = []
    for (c, t), o in obs.items():
        for lab, sd in o["flags"]:
            sig.append(dict(o, lab=lab, sd=sd, noise=abs(o["p3"]) <= .1 or abs(o["oi5"]) <= .1))
    for c, t in VERDICT:
        o = obs.get((c, t))
        if o:
            sig.append(dict(o, lab="итог «вниз» (мой)", sd=-1, noise=False))
    K = {}
    for c in ("SEI", "ONE", "PLAY"):
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": c + "USDT", "interval": "3m",
                     "startTime": int(DAY.replace(hour=3).timestamp() * 1000), "limit": 1500}) or []
        K[c] = [(int(x[0]), float(x[2]), float(x[3]), float(x[4])) for x in k]
    now = datetime.now(L).timestamp() * 1000
    for s in sig:
        h, m = map(int, s["t"].split(":"))
        t0 = int(DAY.replace(hour=h, minute=m).timestamp() * 1000)
        bars = [b for b in K[s["c"]] if b[0] + 180_000 > t0 and b[0] < t0 + 4 * 3600_000]
        e, sd, res, how = s["px"], s["sd"], None, ""
        for tb, hi, lo, cl in bars:
            up, dn = (hi / e - 1) * 100 * sd, (lo / e - 1) * 100 * sd
            best, worst = max(up, dn), min(up, dn)
            if worst <= -5:
                res, how = -5.1, "стоп"; break
            if best >= 5:
                res, how = 4.9, "цель"; break
        if res is None and bars:
            res = (bars[-1][3] / e - 1) * 100 * sd - .1
            how = "4 ч" if t0 + 4 * 3600_000 <= now else "идёт"
        at = lambda dt: next(((b[3] / e - 1) * 100 * sd for b in K[s["c"]] if b[0] >= t0 + dt), None)  # noqa: E731
        s.update(res=res, how=how, r1=at(3600_000), r4=at(4 * 3600_000))
    sig.sort(key=lambda s: (s["lab"], s["c"], s["t"]))
    # первая метка серии: та же метка той же монеты не раньше 30 мин после прошлой
    last = {}
    for s in sorted(sig, key=lambda s: s["t"]):
        k = (s["c"], s["lab"]); h, m = map(int, s["t"].split(":")); mm = h * 60 + m
        s["first"] = k not in last or mm - last[k] >= 30
        last[k] = mm
    f = lambda x: "—" if x is None else f"{x:+.1f}%"  # noqa: E731
    md = [f"# Метки слежки как сигналы ({datetime.now(L):%d.%m %H:%M})", "",
          f"Строк слежки: {len(obs)} (SEI {sum(1 for k in obs if k[0]=='SEI')}, ONE {sum(1 for k in obs if k[0]=='ONE')}, "
          f"PLAY {sum(1 for k in obs if k[0]=='PLAY')}), сигналов: {len(sig)}. Исход: +5% / −5% в сторону сигнала за 4 ч по 3m свечам Binance "
          "(оба в одной свече — стоп), иначе итог через 4 ч; «идёт» — 4 ч ещё не прошло, итог на сейчас. 500 $ на сигнал. Только 28.09, три монеты.", "",
          "| метка | сторона | сигналов | в плюс | итог $ | через 1 ч, медиана | первые в серии: сигналов · в плюс · $ | без шума: сигналов · в плюс · $ |",
          "|---|---|---|---|---|---|---|---|"]
    by = defaultdict(list)
    for s in sig:
        by[s["lab"]].append(s)
    agg = lambda g: (len(g), sum(1 for s in g if s["res"] > 0), sum(s["res"] * 5 for s in g))  # noqa: E731
    for lab, g in sorted(by.items(), key=lambda kv: -len(kv[1])):
        g = [s for s in g if s["res"] is not None]
        if not g:
            continue
        n, w, u = agg(g); fn, fw, fu = agg([s for s in g if s["first"]]); nn, nw, nu = agg([s for s in g if not s["noise"]])
        r1 = [s["r1"] for s in g if s["r1"] is not None]
        md.append(f"| {lab} | {'лонг' if g[0]['sd'] > 0 else 'шорт'} | {n} | {w} ({w / n * 100:.0f}%) | {u:+.0f} | {f(st.median(r1)) if r1 else '—'} | "
                  f"{fn} · {fw} · {fu:+.0f} | {nn} · {nw} · {nu:+.0f} |")
    md += ["", "## По монетам", "", "| монета | метка | сигналов | в плюс | итог $ |", "|---|---|---|---|---|"]
    for c in ("SEI", "ONE", "PLAY"):
        for lab, g in sorted(by.items()):
            g2 = [s for s in g if s["c"] == c and s["res"] is not None]
            if g2:
                n, w, u = agg(g2)
                md.append(f"| {c} | {lab} | {n} | {w} | {u:+.0f} |")
    # 28.09 владелец: «сделай разбивку, в какое время сделка вышла в плюс, в какое в минус» — по часу сигнала (UTC+3) и сессиям
    ses = lambda t: "Сидней" if t < 3 else "Токио" if t < 10 else "Лондон" if t < 16 else "Нью-Йорк"  # noqa: E731
    G = [s for s in sig if s["res"] is not None]
    main2 = [lab for lab, _ in sorted(by.items(), key=lambda kv: -len(kv[1]))][:2]
    md += ["", "## По времени сигнала (час UTC+3): в плюс / в минус", "",
           "| час | сессия | все: + / − · $ | " + " | ".join(f"{m}: + / − · $" for m in main2) + " |", "|---|---|---|" + "---|" * len(main2)]
    cell = lambda g: f"{sum(1 for s in g if s['res'] > 0)} / {sum(1 for s in g if s['res'] <= 0)} · {sum(s['res'] * 5 for s in g):+.0f}" if g else "—"  # noqa: E731
    for h in sorted({int(s["t"][:2]) for s in G}):
        g = [s for s in G if int(s["t"][:2]) == h]
        md.append(f"| {h:02d}:00 | {ses(h)} | {cell(g)} | " + " | ".join(cell([s for s in g if s["lab"] == m]) for m in main2) + " |")
    md += ["", "| сессия | все: + / − · $ | " + " | ".join(f"{m}: + / − · $" for m in main2) + " |", "|---|---|" + "---|" * len(main2)]
    for sn in ("Токио", "Лондон", "Нью-Йорк"):
        g = [s for s in G if ses(int(s["t"][:2])) == sn]
        md.append(f"| {sn} | {cell(g)} | " + " | ".join(cell([s for s in g if s["lab"] == m]) for m in main2) + " |")
    md += ["", "## Все сигналы", "", "| время | монета | цена | метка | сторона | шум | исход | через 1 ч | через 4 ч |", "|---|---|---|---|---|---|---|---|---|"]
    for s in sorted(sig, key=lambda s: (s["t"], s["c"])):
        md.append(f"| {s['t']} | {s['c']} | {s['px']:.6g} | {s['lab']} | {'лонг' if s['sd'] > 0 else 'шорт'} | {'да' if s['noise'] else ''} | "
                  f"{f(s['res'])} {s['how']} | {f(s['r1'])} | {f(s['r4'])} |")
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    i = md.index("## По времени сигнала (час UTC+3): в плюс / в минус")
    print("\n".join(md[i:md.index('## Все сигналы')]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
