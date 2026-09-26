"""БАЗА ДЛЯ intraday_catch.py: как часто в ЛЮБЫХ сутках у ЛЮБОЙ монеты есть рост интереса ≥ +15% (и ≥ +8%) за 3 ч — по всем 154 монетам за 30 дней (Binance
openInterestHist 30m). Если такие сутки — редкость, то «42 из 43 лидеров за сутки до первого +40%» значимо; если норма — нет.
Также: доля таких сигналов, после которых монета за 48 ч делает ≥ +40% (то же, что R34, но только по интересу, без тейкера).
    .venv/bin/python claude/research/oi_base_rate.py
"""
import json, time, urllib.request
from pathlib import Path
P = Path(__file__).resolve().parents[2] / "cq_v2" / "hist" / "tops"; B = 1800000; H = 3600000
def get(u): return json.loads(urllib.request.urlopen(u, timeout=20).read())
def hist(sym):
    out, end = {}, None
    for _ in range(4):
        d = get(f"https://fapi.binance.com/futures/data/openInterestHist?symbol={sym}&period=30m&limit=500" + (f"&endTime={end}" if end else ""))
        if not d: break
        out.update({int(x["timestamp"]): float(x["sumOpenInterestValue"]) for x in d}); end = int(d[0]["timestamp"]) - 1
        if len(d) < 500: break
    return out
days_total = days_A = days_B = 0; sigA = 0; sigA_40 = 0; sigA_10 = 0
t0 = time.time()
for n, p in enumerate(sorted(P.glob("*.json"))):
    if p.stem == "BTCUSDT": continue
    kl = json.loads(p.read_text())["kl"]; by = {k[0]: k[3] for k in kl}
    try: oi = hist(p.stem)
    except Exception: continue
    ts = sorted(oi)
    g3 = {t: (oi[t] / oi[t - 6 * B] - 1) * 100 for t in ts if (t - 6 * B) in oi}
    # сутки — скользящие окна по 48 баров с шагом 24 ч
    for i in range(0, len(ts) - 48, 48):
        w = [g3[t] for t in ts[i:i + 48] if t in g3]
        if not w: continue
        days_total += 1; days_A += max(w) >= 15; days_B += max(w) >= 8
    last = -10 ** 18
    for t in ts:
        if g3.get(t, 0) < 15 or t - last < 12 * H or t not in by: continue
        last = t; sigA += 1
        fut = [by[x] for x in range(t + B, t + 48 * H + 1, B) if x in by]
        if fut:
            mx = max(fut) / by[t] - 1; sigA_40 += mx >= 0.40; sigA_10 += mx >= 0.10
    if n % 30 == 0: print(f"  {n} монет, {time.time() - t0:.0f} с", flush=True)
    time.sleep(0.05)
print(f"\nсуток всего {days_total}: с ростом интереса ≥+15% за 3 ч — {days_A} ({days_A / days_total * 100:.0f}%), ≥+8% — {days_B} ({days_B / days_total * 100:.0f}%)")
print(f"сигналов ≥+15% за 3 ч (не чаще раза в 12 ч на монету): {sigA}; за 48 ч после — ≥+10% у {sigA_10 / max(sigA, 1) * 100:.0f}%, ≥+40% у {sigA_40 / max(sigA, 1) * 100:.0f}%")
