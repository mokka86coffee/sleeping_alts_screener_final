#!/usr/bin/env python3
"""R58 НА ДРУГИХ МЕСЯЦАХ (03.10 22:10, владелец на оговорку «один растущий месяц, подбор на тех же данных»: «и что это за хуйня?»).
Часовых ликвидаций у TradingView хватает только на месяц, поэтому то же правило пересказано на 4-часовых барах, где данных 3,5 месяца (22.06–03.10), включая падающий июнь и плоский июль —
на этих месяцах правило не подбиралось. Сигнал: рекордный за сутки 4-часовой бар выноса шортов (R61), минимумы за 48 ч (12 баров) растут, максимум бара выноса выше минимума за 48 ч на 60 %+.
Вход: когда цена в следующие 24 ч вернулась к максимуму бара выноса, по этой цене. Стоп 10 %; после −5 % стоп в точку входа; через 8 ч (2 бара вместо 6 часов), если стоп не перенесён:
цена выше входа — закрытие, иначе стоп в точку входа; выход через 16 ч (4 бара). В баре входа проверяется только стоп (худший случай). Только запись."""
import json, glob, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT)); D = Path(__file__).parent / "tvd"; L = timezone(timedelta(hours=3))
import fast_tier as ft
own = ft._own_mm(); R = []; R0 = []
for f in sorted(glob.glob(str(D / "*_240.json"))):
    d = json.load(open(f))
    if not isinstance(d, dict): continue
    sym = d["sym"].split(":")[1].replace(".P", ""); b = d["bars"]
    if sym in own or len(b) < 100: continue
    try:
        if len(json.load(open(D / Path(f).name.replace("_240.json", "_1D.json")))["bars"]) < 180: continue
    except Exception: continue
    LS, LL = {}, {}
    for x in d.get("liq") or []:
        if x[1]: LL[x[0]] = abs(x[1])
        if len(x) > 2 and x[2]: LS[x[0]] = abs(x[2])
    busy = -1
    for i in range(13, len(b) - 11):
        t = b[i][0]; win = LS.get(t, 0.0)
        if win <= 0 or i <= busy: continue
        prev = [v for h, v in LS.items() if t - 86400 <= h < t]
        if not prev or win <= max((v for h, v in LL.items() if t - 86400 <= h <= t), default=0.0): continue
        mx = max(prev); mean = sum(prev) / len(prev)
        if win < (1.3 * mx if (len(prev) > 1 and mx >= 2 * mean) else 2 * mx): continue
        l48 = [x[3] for x in b[i - 12:i]]; f3, l3 = l48[:4], l48[-4:]
        if not (min(l3) > min(f3) and sum(l3) > sum(f3)): continue
        if (b[i][2] / min(l48) - 1) * 100 < 60: continue
        lvl = b[i][2]; j = next((q for q in range(i + 1, i + 7) if b[q][2] >= lvl), None)
        # для сравнения: вход сразу по закрытию бара сквиза
        def out(e, seq):
            be = False
            for n, (tt, o, h, l, c, v) in enumerate(seq, 1):
                if h >= (e if be else e * 1.10): return (0.0, "безубыток") if be else (-.10, "стоп")
                if not be and n > 0 and l <= e * .95: be = True
                if n >= 2 and not be:
                    if c > e: return 1 - c / e, "8 ч: выше входа"
                    be = True
            return 1 - seq[-1][4] / e, "срок"
        r0, h0 = out(b[i][4], b[i + 1:i + 5]); R0.append((t, r0, h0, sym))
        if j is None: continue
        # бар входа: только стоп (порядок внутри бара неизвестен)
        if b[j][2] >= lvl * 1.10: r, how = -.10, "стоп"
        else: r, how = out(lvl, b[j + 1:j + 5])
        R.append((b[j][0], r, how, sym)); busy = j + 4
def rep(nm, T):
    n = len(T); 
    if not n: print(nm, "нет"); return
    how = defaultdict(list)
    for _, r, h, _ in T: how[h].append(r)
    print(f"{nm}: сделок {n} · {(sum(r for _, r, _, _ in T) * 1000 - n) / n:+.1f}$ на сделку · в плюс {sum(1 for _, r, _, _ in T if r > 0) * 100 // n}% · " + " · ".join(f"{k} {len(v)} ({sum(v) * 1000 / len(v):+.0f}$)" for k, v in sorted(how.items(), key=lambda kv: -len(kv[1]))))
    bym = defaultdict(list)
    for t, r, _, _ in T: bym[datetime.fromtimestamp(t, L).strftime("%m.%y")].append(r)
    print("    по месяцам: " + " · ".join(f"{m}: {len(v)} сд. {sum(v) * 1000 - len(v):+.0f}$ ({(sum(v) * 1000 - len(v)) / len(v):+.0f}$/сд.)" for m, v in sorted(bym.items(), key=lambda kv: (kv[0][3:], kv[0][:2]))))
print(f"сигналов «рост и памп» на 4-часовых: {len(R0)} · цена вернулась к верху бара сквиза: {len(R)}")
rep("ВХОД НА ВЕРХЕ БАРА СКВИЗА (как внесено)", R); rep("ВХОД СРАЗУ по закрытию бара сквиза", R0)
