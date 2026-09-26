"""КОГО ИЗ ЛИДЕРОВ ПОЙМАЛА БЫ ВНУТРИДНЕВНАЯ ПОДПИСЬ R34 (26.09, продолжение four_signs.py: дневные 5 признаков видят 28% лидеров накануне первого +40% за 48 ч).
Для каждого лидера (anatomy.csv) берём момент Б — первый получасовой бар с закрытием ≥ +40% к закрытию 48 ч назад — и смотрим 24 ч ДО него:
был ли рост интереса за 3 ч ≥ +15% (ярус A из R34) или ≥ +8% (ярус B) по Binance openInterestHist 30m, и за сколько часов до Б он случился впервые.
Плюс тот же вопрос про дневные признаки (judge() накануне) — чтобы сложить: кого видят дни, кого часы, кого никто.
    .venv/bin/python claude/research/intraday_catch.py
"""
import csv, json, sys, time, urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import near_move as nm
L3 = timezone(timedelta(hours=3)); H = 3600000; B = 1800000
def get(u): return json.loads(urllib.request.urlopen(u, timeout=20).read())
def oi_hist(sym, t0, t1):
    d = get(f"https://fapi.binance.com/futures/data/openInterestHist?symbol={sym}USDT&period=30m&startTime={t0}&endTime={t1}&limit=500")
    return {int(x["timestamp"]): float(x["sumOpenInterestValue"]) for x in d}
def cut(d, day): return {k: [r for r in v if r.get("datetime", "")[:10] <= day] for k, v in d.items() if isinstance(v, list)}
rows = list(csv.DictReader(open(Path(__file__).with_name("anatomy.csv"), encoding="utf-8")))
res = []
print(f"{'монета':<9}{'Б (первый +40%)':<16}| дни (judge накануне) | часы: макс. рост интереса за 3 ч в 24 ч до Б · первый ≥+15% за ... ч до Б · ≥+8%")
for r in rows:
    try:
        t_s = int(datetime.strptime(r["start"] + ".2026", "%d.%m %H:%M.%Y").replace(tzinfo=L3).timestamp() * 1000)
        t_p = int(datetime.strptime(r["peak1"] + ".2026", "%d.%m %H:%M.%Y").replace(tzinfo=L3).timestamp() * 1000)
    except Exception: continue
    p = ROOT / "cq_v2" / "hist" / "tops" / f"{r['sym']}USDT.json"
    if not p.exists(): continue
    kl = json.loads(p.read_text())["kl"]; by = {k[0]: k[3] for k in kl}
    tB = next((k[0] for k in kl if t_s <= k[0] <= t_p and by.get(k[0] - 48 * H) and k[3] / by[k[0] - 48 * H] - 1 >= 0.40), None)
    if not tB: continue
    dayB = (datetime.fromtimestamp(tB / 1000, L3) - timedelta(days=1)).strftime("%Y-%m-%d")
    pc = ROOT / "cq_v2" / f"{r['sym'].lower()}.json"
    j = nm.judge(cut(json.loads(pc.read_text()), dayB)) if pc.exists() else None
    sc = (j or {}).get("score")
    try:
        oi = oi_hist(r["sym"], tB - 27 * H, tB)
    except Exception as e:
        print(r["sym"], "нет интереса:", type(e).__name__); continue
    ts = sorted(t for t in oi if tB - 24 * H <= t <= tB)
    best, firstA, firstB = 0.0, None, None
    for t in ts:
        p3 = oi.get(t - 6 * B)
        if not p3: continue
        g = (oi[t] / p3 - 1) * 100; best = max(best, g)
        if g >= 15 and firstA is None: firstA = (tB - t) / H
        if g >= 8 and firstB is None: firstB = (tB - t) / H
    print(f"{r['sym']:<9}{datetime.fromtimestamp(tB / 1000, L3).strftime('%d.%m %H:%M'):<16}| {str(sc):>4} {str((j or {}).get('group')):<8} | {best:+6.1f}% · {('%.1f' % firstA) if firstA is not None else '—':>5} · {('%.1f' % firstB) if firstB is not None else '—':>5}")
    res.append(dict(sym=r["sym"], sc=sc, best=best, fA=firstA, fB=firstB, move=float(r["move1_pct"])))
    time.sleep(0.1)
n = len(res)
days_ok = [x for x in res if x["sc"] is not None and x["sc"] >= 5]
hA = [x for x in res if x["fA"] is not None]; hB = [x for x in res if x["fB"] is not None]
both = [x for x in res if x in days_ok and x in hA]; none = [x for x in res if x not in days_ok and x not in hB]
print(f"\nСВОДКА по {n} лидерам (окно 24 ч до первого +40% за 48 ч):")
print(f"  дни (≥5 признаков накануне): {len(days_ok)}/{n} · часы ярус A (интерес ≥+15% за 3 ч): {len(hA)}/{n} · ярус B (≥+8%): {len(hB)}/{n}")
print(f"  и дни, и часы A: {len(both)} · только часы A: {len([x for x in hA if x not in days_ok])} · только дни: {len([x for x in days_ok if x not in hA])} · никто (ни дни, ни B): {len(none)}/{n}")
if hA: print(f"  ярус A — за сколько часов до Б впервые: медиана {sorted(x['fA'] for x in hA)[len(hA)//2]:.1f} ч, ≥6 ч заранее у {sum(1 for x in hA if x['fA'] >= 6)}/{len(hA)}")
big = [x for x in res if x["move"] >= 100]
print(f"  ходы ≥+100% ({len(big)}): дни {sum(1 for x in big if x in days_ok)} · часы A {sum(1 for x in big if x['fA'] is not None)} · B {sum(1 for x in big if x['fB'] is not None)} · никто {sum(1 for x in big if x in none)}")
print("  никто:", [x["sym"] for x in none])
