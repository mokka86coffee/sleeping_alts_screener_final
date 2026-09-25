"""Анатомия хода по получасовкам Binance за 30 дней (cq_v2/hist/tops/<SYM>.json).
Точки разворота — зигзаг: разворот засчитывается, когда цена ушла от экстремума на REV и больше
(REV — мерка для разметки, не правило). Ход — нога вверх от минимума до максимума не меньше LEG.
Пишет anatomy.csv: база, первый большой ход (старт → вершина), откат (докуда), повторный ход (откуда, когда,
докуда), второй откат. Цены — закрытия часовок (из получасовок); время — местное (UTC+3)."""
import csv, json, sys
from datetime import datetime, timezone
from pathlib import Path
REV, LEG = 0.25, 0.50
P = Path("/Users/evgenijminko/Work/random/python/cq_v2/hist/tops")
def L(ms): return datetime.fromtimestamp(ms / 1000 + 3 * 3600, timezone.utc).strftime("%d.%m %H:%M")
def zigzag(kl):
    pts, d, ext_i = [], 0, 0
    for i, (t, h, l, c) in enumerate(kl):
        if d == 0:                                   # до первого разворота — от самого низкого/высокого закрытия
            mn = min(range(i + 1), key=lambda j: kl[j][3]); mx = max(range(i + 1), key=lambda j: kl[j][3])
            if c >= kl[mn][3] * (1 + REV): d, pts = 1, [(mn, "lo")]; ext_i = i
            elif c <= kl[mx][3] * (1 - REV): d, pts = -1, [(mx, "hi")]; ext_i = i
            continue
        if d > 0:
            if c > kl[ext_i][3]: ext_i = i
            elif c <= kl[ext_i][3] * (1 - REV): pts.append((ext_i, "hi")); d, ext_i = -1, i
        else:
            if c < kl[ext_i][3]: ext_i = i
            elif c >= kl[ext_i][3] * (1 + REV): pts.append((ext_i, "lo")); d, ext_i = 1, i
    pts.append((ext_i, "hi" if d > 0 else "lo"))
    return pts
def px(kl, i, kind): return kl[i][3]
rows = []
for sym in sys.argv[1:]:
    k30 = json.loads((P / f"{sym}USDT.json").read_text())["kl"]
    kl = []                                   # часовки: закрытие второй получасовки, максимум/минимум пары
    for i in range(0, len(k30) - 1, 2):
        a_, b_ = k30[i], k30[i + 1]
        kl.append([a_[0], max(a_[1], b_[1]), min(a_[2], b_[2]), b_[3]])
    z = zigzag(kl)
    legs = [(a, b) for a, b in zip(z, z[1:]) if a[1] == "lo" and px(kl, b[0], "hi") >= px(kl, a[0], "lo") * (1 + LEG)]
    r = {"sym": sym}
    if not legs:
        r["note"] = f"нет ноги вверх ≥{LEG*100:.0f}% за 30 дней"; rows.append(r); continue
    (a, b) = legs[0]
    lo, hi = px(kl, a[0], "lo"), px(kl, b[0], "hi")
    base_days = sum(1 for k in kl[max(0, a[0]-168):a[0]] if k[3] <= lo * 1.2) / 24
    r.update(start=L(kl[a[0]][0]), start_px=lo, base_days_within20=round(base_days, 1),
             peak1=L(kl[b[0]][0]), peak1_px=hi, move1_pct=round((hi/lo-1)*100), move1_h=(kl[b[0]][0]-kl[a[0]][0])//3600000)
    zi = z.index(b)
    if zi + 1 < len(z):
        c = z[zi + 1]; clo = px(kl, c[0], "lo")
        r.update(pullback1=L(kl[c[0]][0]), pullback1_px=clo, pullback1_pct=round((clo/hi-1)*100),
                 kept_of_move1=round((clo-lo)/(hi-lo)*100), pullback1_h=(kl[c[0]][0]-kl[b[0]][0])//3600000)
        if zi + 2 < len(z):
            d2 = z[zi + 2]; h2 = px(kl, d2[0], "hi")
            r.update(peak2=L(kl[d2[0]][0]), peak2_px=h2, move2_pct=round((h2/clo-1)*100),
                     peak2_vs_peak1=round((h2/hi-1)*100), move2_start_after_peak1_h=(kl[c[0]][0]-kl[b[0]][0])//3600000)
            if zi + 3 < len(z):
                e = z[zi + 3]; elo = px(kl, e[0], "lo")
                r.update(pullback2=L(kl[e[0]][0]), pullback2_px=elo, pullback2_pct=round((elo/h2-1)*100),
                         pullback2_vs_start=round((elo/lo-1)*100))
    last = kl[-1][3]; r["now_vs_start_pct"] = round((last/lo-1)*100); r["now_vs_peak1_pct"] = round((last/hi-1)*100)
    rows.append(r)
cols = ["sym","start","start_px","base_days_within20","peak1","peak1_px","move1_pct","move1_h","pullback1","pullback1_px",
        "pullback1_pct","kept_of_move1","pullback1_h","move2_start_after_peak1_h","peak2","peak2_px","move2_pct","peak2_vs_peak1",
        "pullback2","pullback2_px","pullback2_pct","pullback2_vs_start","now_vs_start_pct","now_vs_peak1_pct","note"]
out = Path(__file__).with_name("anatomy.csv")
new = not out.exists()
with out.open("a", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols); new and w.writeheader(); [w.writerow(r) for r in rows]
for r in rows: print(r)
