"""ПРИЗНАКИ НАЧАЛА НА ВСЕХ МОНЕТАХ, НЕ ТОЛЬКО НА ПОШЕДШИХ (26.09, хвост 4 из CONTEXT.md; R23: у PHA и ARK перед прыжком балла — три получасовки подряд
покупок по рынку (тейкер 1.4–1.9) и интерес +18…+34%). Здесь тот же признак ищется по всем 154 монетам за 30 дней и считается, как часто за ним идёт ход.
Данные: Binance takerlongshortRatio (30m, покупки/продажи по рынку), openInterestHist (30m, интерес в $), закрытия из cq_v2/hist/tops.
Признак (мерка из R23, не правило): ярус A — средний тейкер трёх получасовок ≥ 1.2 и интерес за 3 ч ≥ +8%; ярус B — ≥ 1.1 и ≥ +5%; цена за три бара не упала.
Строгая версия (все три бара ≥ 1.3, интерес ≥ +8% за 1.5 ч) дала 1 сигнал за 30 дней — слишком жёстко.
Исход: максимум закрытия за следующие 48 ч ≥ +10% / ≥ +20% / ≥ +40%; провал ≤ −10% раньше, чем +10%. База — все бары. Разрезы: фон доски за 24 ч; монета уже в ходу
(≥+40% за 48 ч) или спит (< +20%). Один сигнал на монету в 12 ч.
    .venv/bin/python claude/research/start_signs.py
"""
import json, statistics as st, time, urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
P = Path(__file__).resolve().parents[2] / "cq_v2" / "hist" / "tops"; B = 1800000; L = timezone(timedelta(hours=3))
def get(u): return json.loads(urllib.request.urlopen(u, timeout=20).read())
def hist(ep, sym, key):
    out, end = {}, None
    for _ in range(4):
        u = f"https://fapi.binance.com/futures/data/{ep}?symbol={sym}&period=30m&limit=500" + (f"&endTime={end}" if end else "")
        d = get(u)
        if not d: break
        out.update({int(x["timestamp"]): float(x[key]) for x in d}); end = int(d[0]["timestamp"]) - 1
        if len(d) < 500: break
    return out
kl = {p.stem: json.loads(p.read_text())["kl"] for p in P.glob("*.json") if p.stem != "BTCUSDT"}
idx = {s: {k[0]: i for i, k in enumerate(v)} for s, v in kl.items()}
memo = {}
def board(t):
    if t not in memo:
        ch = [v[idx[s][t]][3] / v[idx[s][t - 48 * B]][3] - 1 for s, v in kl.items() if t in idx[s] and t - 48 * B in idx[s]]
        memo[t] = st.median(ch) * 100 if ch else None
    return memo[t]
def outcome(v, i):
    base = v[i][3]; mx, first = 0.0, "стоит"
    for x in v[i + 1:i + 97]:
        r = x[3] / base - 1
        if first == "стоит":
            if r <= -0.10: first = "провал"
            elif r >= 0.10: first = "плюс10"
        mx = max(mx, r)
    return mx * 100, first
sig, base_all = [], []
t0 = time.time()
for n, (s, v) in enumerate(sorted(kl.items())):
    try:
        tk = hist("takerlongshortRatio", s, "buySellRatio"); oi = hist("openInterestHist", s, "sumOpenInterestValue")
    except Exception as e:
        print(s, "нет данных:", type(e).__name__); continue
    last = -10 ** 18
    for i in range(100, len(v) - 97):
        t = v[i][0]
        if i % 6 == 0:   # база: каждый третий час
            base_all.append(outcome(v, i))
        ts = [t - 2 * B, t - B, t]
        if not all(x in tk for x in ts) or t not in oi or (t - 6 * B) not in oi: continue
        tkm = sum(tk[x] for x in ts) / 3; oich = (oi[t] / oi[t - 6 * B] - 1) * 100
        tier = "A" if (tkm >= 1.2 and oich >= 8) else ("B" if (tkm >= 1.1 and oich >= 5) else None)
        if not tier: continue
        if v[i][3] < v[i - 3][3]: continue
        if t - last < 24 * B: continue
        last = t
        mx, first = outcome(v, i)
        m48 = (v[i][3] / v[i - 96][3] - 1) * 100
        sig.append(dict(sym=s, t=t, mx=mx, first=first, bg=board(t), m48=m48, tk=tkm, oi=oich, tier=tier))
    if n % 20 == 0: print(f"  {n}/{len(kl)} монет, {time.time() - t0:.0f} с, сигналов {len(sig)}", flush=True)
    time.sleep(0.05)
def stat(name, g, base=False):
    if not g: return
    if base:
        mx = [x[0] for x in g]; first = Counter(x[1] for x in g)
    else:
        mx = [x["mx"] for x in g]; first = Counter(x["first"] for x in g)
    n = len(mx)
    print(f"  {name:<46} n={n:5d} · ≥+10% за 48 ч {sum(1 for m in mx if m >= 10) / n * 100:3.0f}% · ≥+20% {sum(1 for m in mx if m >= 20) / n * 100:3.0f}% · ≥+40% {sum(1 for m in mx if m >= 40) / n * 100:3.0f}%"
          f" · +10% раньше −10% {first['плюс10'] / n * 100:3.0f}% · провал раньше {first['провал'] / n * 100:3.0f}%")
print(f"\nсигналов {len(sig)} у {len(set(x['sym'] for x in sig))} монет; база {len(base_all)} баров")
stat("БАЗА — все бары (каждый третий час)", base_all, base=True)
stat("ПРИЗНАК A: средний тейкер 3 баров ≥1.2 + интерес за 3 ч ≥+8%", [x for x in sig if x["tier"] == "A"])
stat("ПРИЗНАК B: тейкер ≥1.1 + интерес ≥+5% (без A)", [x for x in sig if x["tier"] == "B"])
stat("ПРИЗНАК A+B", sig)
stat("  монета спала (< +20% за 48 ч)", [x for x in sig if x["m48"] < 20])
stat("  монета уже в ходу (≥ +40% за 48 ч)", [x for x in sig if x["m48"] >= 40])
stat("  доска > +1%", [x for x in sig if x["bg"] is not None and x["bg"] > 1])
stat("  доска −1…+1%", [x for x in sig if x["bg"] is not None and -1 <= x["bg"] <= 1])
stat("  доска < −1%", [x for x in sig if x["bg"] is not None and x["bg"] < -1])
stat("  спала и доска > +1%", [x for x in sig if x["m48"] < 20 and x["bg"] is not None and x["bg"] > 1])
stat("  спала и доска ≤ +1%", [x for x in sig if x["m48"] < 20 and x["bg"] is not None and x["bg"] <= 1])
stat("  тейкер ≥ 1.4 (сильнее)", [x for x in sig if x["tk"] >= 1.4])
stat("  интерес ≥ +15% за три бара", [x for x in sig if x["oi"] >= 15])
print("\nсигналы с ходом ≥ +40% за 48 ч (монета · время · тейкер · интерес за 3 бара · было за 48 ч · максимум дальше):")
for x in sorted(sig, key=lambda x: -x["mx"])[:20]:
    print(f"  {x['sym'][:-4]:<9} {datetime.fromtimestamp(x['t'] / 1000, L).strftime('%d.%m %H:%M')} · тейкер {x['tk']:.2f} · интерес {x['oi']:+.0f}% · было {x['m48']:+.0f}% · дальше {x['mx']:+.0f}%")
