"""КТО СЛЕДУЮЩИЙ (26.09, владелец: «давай следующую, которая пойдёт, определи»). Скан всех монет архива по признакам НАЧАЛА со счётом:
R34 — интерес +15% за 3 ч (после сигнала +10% за 48 ч у 52%, +40% у 15%; у спящей монеты); R1 — интерес за 24 ч ≥ +20% при цене ±5% (набор при стоящей цене);
R23 — покупки по рынку (средний тейкер 3 баров ≥ 1.2); R20/R14 — фандинг ≤ −0.05% (шорты — топливо); R19 — спот покупает (сумма дельты спота за 6 баров > 0);
тихий объём (× к медиане 48 < 3 — ещё не бегут). Вес: R34 3, R1 2, остальные по 1. Не вход, а список «смотреть», с вероятностями из реестра.
    .venv/bin/python claude/research/next.py
"""
import json, statistics as st
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; L = timezone(timedelta(hours=3))
nm = {}
try: nm = json.loads((ROOT / "output" / "near_move.json").read_text()).get("coins") or {}
except Exception: pass
out = []
for p in sorted((ROOT / "cq_v2" / "intraday").glob("*.jsonl")):
    rows = []
    for line in p.read_text().splitlines()[-60:]:
        try: rows.append(json.loads(line))
        except ValueError: continue
    rows = [r for r in rows if r.get("px") and r.get("oi")]
    if len(rows) < 50: continue
    s = p.stem.upper() + "USDT"; i = len(rows) - 1
    OI = [float(r["oi"]) for r in rows]; C = [float(r["px"]) for r in rows]
    oi3 = (OI[i] / OI[i - 6] - 1) * 100 if OI[i - 6] else 0
    oi24 = (OI[i] / OI[i - 48] - 1) * 100 if OI[i - 48] else 0
    px24 = (C[i] / C[i - 48] - 1) * 100
    tk = [((r.get("fut") or {}).get("tk")) for r in rows[i - 2:i + 1]]; tkm = sum(float(x) for x in tk) / 3 if all(x is not None for x in tk) else None
    fund = rows[i].get("funding"); spot = sum(float(((r.get("spot") or {}).get("d")) or 0) for r in rows[i - 5:i + 1])
    qv = [float(((r.get("kv") or {}).get("qv")) or 0) for r in rows]; vx = qv[i] / (st.median(qv[i - 48:i]) or 1)
    run = float(((nm.get(s) or {}).get("nums") or {}).get("run_from_low7") or 0)
    score, why = 0, []
    if oi3 >= 15: score += 3; why.append(f"R34 интерес +{oi3:.0f}%/3ч")
    if oi24 >= 20 and abs(px24) <= 5: score += 2; why.append(f"R1 интерес +{oi24:.0f}%/24ч при цене {px24:+.1f}%")
    if tkm is not None and tkm >= 1.2: score += 1; why.append(f"покупки по рынку {tkm:.2f}")
    if fund is not None and float(fund) <= -0.05: score += 1; why.append(f"фандинг {float(fund):+.2f}% (шорты)")
    if spot > 0 and (rows[i].get("spot") or {}).get("d") is not None: score += 1; why.append(f"спот +{spot/1e3:.0f}K")
    if vx < 3: why.append(f"объём тихий ×{vx:.1f}")
    else: why.append(f"объём ×{vx:.1f}")
    if score >= 3:
        out.append((score, s, run, px24, oi3, oi24, why))
out.sort(key=lambda x: (-x[0], -x[4]))
print(f"скан {datetime.now(L).strftime('%d.%m %H:%M')} по последним закрытым получасовкам архива · кандидатов с баллом ≥3: {len(out)}")
print(f"{'монета':<10}{'балл':>4} {'от мин 7д':>9} {'цена 24ч':>9} {'интерес 3ч':>10} {'интерес 24ч':>11}  признаки")
for sc, s, run, px24, oi3, oi24, why in out[:12]:
    stage = "спит" if run < 20 else "в ходу" if run >= 40 else "поднялась"
    prob = "+10% за 48ч у 52%, +40% у 15%" if run < 40 else "+10% у 73%, +40% у 44% (уже в ходу)"
    print(f"{s[:-4]:<10}{sc:>4} {run:>8.0f}% {px24:>+8.1f}% {oi3:>+9.0f}% {oi24:>+10.0f}%  {stage} · {' · '.join(why)} → {prob if any('R34' in w for w in why) else 'без R34 — счёта на вход нет'}")
