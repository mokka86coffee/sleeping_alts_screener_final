"""04.10 — владелец по MUBARAK (шорт сканера, 6 часов не шёл, закрыт −6.1 %): «надо такие шорты в лонги переворачивать», «вернее сделать ещё правило для лонгов по этому
принципу, по тому что брались шорты». Счёт по закрытым шортам журнала на часовых свечах TradingView: шорт прожил 6 часов и на шестом часу в минусе → вместо простого закрытия
лонг от этой цены. Параметры лонга — как у уже существующего переворота (flip_check, 01.10): цель +10 %, стоп на минимуме этих 6 часов, срок 24 часа."""
import json, time, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; TV = ROOT / "claude" / "research" / "tvd"; H6 = 6 * 3600
def hb(sym):
    p = TV / f"{sym}.P_60.json"
    return json.load(open(p))["bars"] if p.exists() else None
rows = []; n_all = 0
for f in ("paper_fast3.jsonl", "paper_wake.jsonl"):
    for l in open(ROOT / "output" / f, encoding="utf-8"):
        try: r = json.loads(l)
        except ValueError: continue
        if r.get("kind") != "exit_short" or not r.get("opened_at"): continue
        n_all += 1
        t0 = r["opened_at"]; e = r["px_in"]; b = hb(r["sym"])
        if not b or r["at"] - t0 < H6: continue
        t6 = t0 + H6
        win = [x for x in b if t0 <= x[0] and x[0] + 3600 <= t6 + 3600]
        nxt = [x for x in b if x[0] >= t6][:25]
        if len(win) < 5 or len(nxt) < 6: continue
        p6 = nxt[0][1]                                      # цена открытия часа после шести часов
        rule = str(r.get("rule", "")); kind = "сканер" if "R52" in rule or "R49" in rule else "5/5" if "шорт 5/5" in rule else "А/А2" if rule.startswith("А") else "прочие"
        rec = dict(sym=r["sym"][:-4], kind=kind, minus=p6 > e, short_usd=r.get("usd", 0), day=time.strftime("%d.%m", time.localtime(r["at"])))
        if p6 > e:
            stop = min(x[3] for x in win); res = None
            for x in nxt[1:]:
                if x[3] <= stop: res = stop / p6 - 1; break
                if x[2] >= p6 * 1.10: res = 0.10; break
            if res is None: res = nxt[-1][4] / p6 - 1
            rec.update(long_usd=(res - 0.001) * 1000, close6_usd=((1 - p6 / e) - 0.001) * 1000, stop_dist=(1 - stop / p6) * 100)
        rows.append(rec)
print(f"закрытых шортов {n_all}; прожили 6 часов и есть свечи: {len(rows)}; из них на шестом часу в минусе: {sum(x['minus'] for x in rows)}")
m = [x for x in rows if x["minus"]]
def s(nm, xs):
    if xs: print(f"{nm}: {len(xs)} сд. · как было (шорт до своего выхода) {sum(x['short_usd'] for x in xs):+.0f} $ · закрыть на 6-м часу {sum(x['close6_usd'] for x in xs):+.0f} $ · лонг после закрытия {sum(x['long_usd'] for x in xs):+.0f} $ (в плюс {sum(x['long_usd'] > 0 for x in xs)}, на сделку {sum(x['long_usd'] for x in xs) / len(xs):+.1f} $)")
s("все в минусе на 6-м часу", m)
for k in ("сканер", "5/5", "А/А2", "прочие"): s("  " + k, [x for x in m if x["kind"] == k])
days = sorted({x["day"] for x in m}, key=lambda d: (d[3:], d[:2]))
print("лонг после закрытия, по дням: " + " · ".join(f"{d} {sum(x['long_usd'] for x in m if x['day'] == d):+.0f} ({sum(x['day'] == d for x in m)})" for d in days))
print("стоп лонга от входа, %: медиана", round(sorted(x["stop_dist"] for x in m)[len(m) // 2], 1) if m else None)
