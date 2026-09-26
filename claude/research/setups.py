"""СДЕЛКИ НА 5–10% ПО РЕЕСТРУ (26.09, владелец: «смотри, на каких сделках можно зарабатывать хотя бы 5–10%»). Скан всех монет архива по четырём сетапам со счётом:
  A «сползание» (шорт отскока): медиана фандинга за сутки ≤ −0.05%, цена ниже макс 72 ч на 20%+, отскок от мин 6 баров ≥ +5% и бар закрылся ниже прошлого —
    цель минимум 72 ч (R18: второго хода 0/2; R24: ONE 17/17 в новый минимум);
  B «конец-лидер» (шорт): лидер (≥+70%/48 ч) сломан (−15% от макс суток) за 48 ч, более низкий максимум без объёма, интерес ниже, чем 6 баров назад —
    цель 25% от максимума суток (R4; лидер через 48 ч ниже 14/17);
  C «толпа в лонге после хода» (шорт): фандинг последней выплаты ≥ +0.05% и максимум за 60 дней, ход от мин 20 дн ≥ +30% — вниз за 10 дн 2/3, медиана −6% (R36);
  D «лестница на шортах» (лонг на откате к стыку): фандинг ≤ −0.3%, интерес +20% за сутки, цена в 10% от макс 48 ч и откат от него ≥ 5% — толчки +5…+23%
    на открытии сессий (R2, R14-вариант; ARK/LSK/SKR на выходных).
    .venv/bin/python claude/research/setups.py
"""
import json, statistics as st
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; L = timezone(timedelta(hours=3))
def med(v): v = sorted(x for x in v if x is not None); return v[len(v) // 2] if v else None
res = {"A": [], "B": [], "C": [], "D": []}
for p in sorted((ROOT / "cq_v2" / "intraday").glob("*.jsonl")):
    rows = []
    for line in p.read_text().splitlines()[-150:]:
        try: rows.append(json.loads(line))
        except ValueError: continue
    rows = [r for r in rows if r.get("px") and r.get("oi")]
    if len(rows) < 100: continue
    s = p.stem.upper() + "USDT"; i = len(rows) - 1
    C = [float(r["px"]) for r in rows]; H = [float(r.get("h") or r["px"]) for r in rows]; Lo = [float(r.get("l") or r["px"]) for r in rows]
    OI = [float(r["oi"]) for r in rows]; F = [r.get("funding") for r in rows]; QV = [float(((r.get("kv") or {}).get("qv")) or 0) for r in rows]
    fm = med(F[i - 48:i + 1]); fund = F[i]
    hi72, lo72 = max(H[i - 144:i + 1]) if i >= 144 else max(H), min(Lo[i - 144:i + 1]) if i >= 144 else min(Lo)
    hi48, hi24 = max(H[i - 96:i + 1]), max(H[i - 48:i + 1])
    lo6 = min(Lo[i - 6:i + 1]); r48 = C[i] / C[i - 96] - 1
    # A
    if fm is not None and fm <= -0.05 and C[i] <= hi72 * 0.8 and lo6 and C[i - 1] / lo6 - 1 >= 0.05 and C[i] < C[i - 1]:
        res["A"].append((s, C[i], f"фандинг {fm:+.2f}%/сутки · −{(1 - C[i] / hi72) * 100:.0f}% от макс 72 ч · отскок +{(C[i - 1] / lo6 - 1) * 100:.0f}% кончился · цель {lo72:.6g} ({(lo72 / C[i] - 1) * 100:+.0f}%)"))
    # B
    if r48 >= 0.7 and C[i] <= hi24 * 0.85:
        vol_ok = QV[i] <= (med(QV[i - 48:i]) or 0); oi_ok = OI[i] < OI[i - 6]; hi4 = max(H[i - 3:i + 1])
        if hi4 < hi24 and C[i] < C[i - 1] and C[i] > C[i - 6] and (vol_ok or oi_ok) and (fund is None or float(fund) <= 0.02):
            tgt = hi24 * 0.75
            res["B"].append((s, C[i], f"лидер +{r48 * 100:.0f}%/48 ч, −{(1 - C[i] / hi24) * 100:.0f}% от макс суток · низкий максимум · объём {'тихий' if vol_ok else 'нет'} · интерес {'уходит' if oi_ok else 'нет'} · цель {tgt:.6g} ({(tgt / C[i] - 1) * 100:+.0f}%)"))
    # C (дневной фандинг из cq_v2/<coin>.json)
    try:
        d = json.loads((ROOT / "cq_v2" / f"{p.stem}.json").read_text()); fr = sorted((r for r in d.get("funding", []) if r.get("datetime")), key=lambda r: r["datetime"])
        fday = [float(r.get("funding_rate") or 0) for r in fr[-60:]]
        o = sorted((r for r in d.get("ohlcv", []) if r.get("datetime")), key=lambda r: r["datetime"]); cl = [float(r["close"]) for r in o[-21:]]
        run20 = (cl[-1] / min(cl) - 1) * 100 if cl else 0
        if fday and fund is not None and float(fund) >= 0.05 and float(fund) >= max(fday[:-1] or [0]) and run20 >= 30:
            res["C"].append((s, C[i], f"фандинг {float(fund):+.3f}% — рекорд за 60 дн · ход +{run20:.0f}% от мин 20 дн · толпа в лонге → вниз за 10 дн 2/3, медиана −6% (n=12)"))
    except Exception: pass
    # D
    oi24 = OI[i] / OI[i - 48] - 1 if OI[i - 48] else 0
    if fund is not None and float(fund) <= -0.3 and oi24 >= 0.20 and C[i] >= hi48 * 0.90 and C[i] <= hi48 * 0.95:
        res["D"].append((s, C[i], f"фандинг {float(fund):+.2f}% · интерес +{oi24 * 100:.0f}%/сутки · откат −{(1 - C[i] / hi48) * 100:.0f}% от макс 48 ч · толчок на стыке +5…+23% (R2)"))
names = {"A": "A · шорт отскока на сползании (R18/R24)", "B": "B · шорт лидера после слома (R27/R4)", "C": "C · шорт толпы в лонге после хода (R36)", "D": "D · лонг на шортовой лестнице у стыка (R2/R14)"}
print(f"скан {datetime.now(L).strftime('%d.%m %H:%M')}")
for k in "ABCD":
    print(f"\n{names[k]} — {len(res[k])}:")
    for s, px, why in res[k][:8]: print(f"  {s[:-4]:<10} {px:.6g} · {why}")
