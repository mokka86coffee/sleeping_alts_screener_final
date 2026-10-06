#!/usr/bin/env python3
"""СТОРОЖ R77 (06.10, владелец: «так ты за этим следи»): повторные входы в ту же монету после быстрого выхода (до 9 мин) — сколько, чем кончились,
есть ли серии подряд. Читает журналы бота output/paper_fast3.jsonl и paper_wake.jsonl с момента включения R77. Время — UTC.
    .venv/bin/python claude/research/reentry_watch.py"""
import json, collections, datetime as dt
from pathlib import Path
B = Path(__file__).resolve().parents[2]
U = dt.timezone.utc
T0 = dt.datetime(2026, 10, 6, 16, 29, tzinfo=U).timestamp()      # правка R77; действует с перезапуска бота после неё
FAST = 10.5 * 60                                                 # как в fast_tier._exit_mark: 9 мин + 1,5 мин на приход прогона
f = lambda t: dt.datetime.fromtimestamp(t, U).strftime("%d.%m %H:%M")
tr = collections.defaultdict(list)
for fn in ("output/paper_fast3.jsonl", "output/paper_wake.jsonl"):
    for l in open(B / fn, encoding="utf-8"):
        try: e = json.loads(l)
        except ValueError: continue
        if str(e.get("kind", "")).startswith("exit") and float(e.get("opened_at") or 0) >= T0:
            tr[(e.get("book"), e["sym"])].append(e)
n_fast = n_re = 0; usd_re = 0.0; series = []
for (book, sym), xs in tr.items():
    xs.sort(key=lambda e: e["opened_at"]); run = 0
    for i, e in enumerate(xs):
        fast = e["at"] - e["opened_at"] < FAST
        n_fast += fast
        prev = xs[i - 1] if i else None
        if prev and prev["at"] - prev["opened_at"] < FAST and e["opened_at"] - prev["at"] < 2 * 3600:
            n_re += 1; usd_re += e.get("usd") or 0; run += 1
            print(f"повторный вход: {book} {sym[:-4]} {'лонг' if e['side'] == 1 else 'шорт'} {f(e['opened_at'])} → {f(e['at'])[6:]} {e['result_pct']:+.1f}% ({e.get('usd'):+.0f} $) · {e.get('why_exit')} | перед ним: выход {f(prev['at'])[6:]} {prev['result_pct']:+.1f}% · {prev.get('why_exit')}")
        else:
            run = 0
        if run >= 2: series.append((book, sym, run + 1))
print(f"с {f(T0)} UTC: быстрых выходов {n_fast} · повторных входов после них {n_re} · их итог {usd_re:+.0f} $")
print("СЕРИИ (три сделки подряд и больше в одной монете): " + (", ".join(f"{s[:-4]} ×{k} ({b})" for b, s, k in series) if series else "нет"))
