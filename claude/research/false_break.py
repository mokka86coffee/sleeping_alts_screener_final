"""ПРОБОЙ И БЫСТРЫЙ ВОЗВРАТ ПОД УРОВЕНЬ (26.09, по видео Щукина: «пробой уровня и быстрый возврат в диапазон — ловушка, стопы вошедших на пробой — топливо
вниз; шорт с целью продолжения коррекции»; его сделки ASR, ID, FOLKS). Проверка на архиве получасовок cq_v2/hist/tops (30 дней, 154 монеты).
Мерки разметки, не правила: уровень — максимум high за предыдущие 48 баров (24 ч); пробой — закрытие выше уровня; «быстрый возврат» — в течение
следующих 2 баров (1 ч) закрытие ниже уровня; «удержался» — оба следующих бара закрылись не ниже уровня. Исход от закрытия бара возврата (или 2-го бара
после пробоя для удержавшихся) за 24 бара (12 ч): «вниз», если −5% раньше +5%; «вверх» — наоборот; «стоит». Одно событие на монету в 12 ч.
Разрезы: фон доски (медиана хода всех монет за 24 ч на баре пробоя), монета «в ходу» (закрытие ≥ +40% к закрытию 48 ч назад), размер пробойного бара.
    .venv/bin/python claude/research/false_break.py
"""
import json, statistics as st
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
P = Path(__file__).resolve().parents[2] / "cq_v2" / "hist" / "tops"; B = 1800000
kl = {p.stem: json.loads(p.read_text())["kl"] for p in P.glob("*.json") if p.stem != "BTCUSDT"}
idx = {s: {k[0]: i for i, k in enumerate(v)} for s, v in kl.items()}
memo = {}
def board(t):
    if t not in memo:
        ch = [v[idx[s][t]][3] / v[idx[s][t - 48 * B]][3] - 1 for s, v in kl.items() if t in idx[s] and t - 48 * B in idx[s]]
        memo[t] = st.median(ch) * 100 if ch else None
    return memo[t]
ev = []
for s, v in kl.items():
    last = -10 ** 18
    for i in range(96, len(v) - 27):
        lvl = max(x[1] for x in v[i - 48:i])
        if v[i][3] <= lvl or v[i][0] - last < 24 * B: continue
        nxt = v[i + 1:i + 3]
        ret = next((j for j, x in enumerate(nxt) if x[3] < lvl), None)
        kind = "возврат" if ret is not None else "удержался"
        j0 = i + 1 + ret if ret is not None else i + 2
        base = v[j0][3]; out = "стоит"
        for x in v[j0 + 1:j0 + 25]:
            if x[3] <= base * 0.95: out = "вниз"; break
            if x[3] >= base * 1.05: out = "вверх"; break
        move48 = (v[i][3] / v[i - 96][3] - 1) * 100 if i >= 96 else None
        bar = (v[i][3] / v[i - 1][3] - 1) * 100
        ev.append(dict(sym=s, t=v[i][0], kind=kind, out=out, bg=board(v[i][0]), move=move48, bar=bar))
        last = v[i][0]
print(f"пробоев максимума суток: {len(ev)}; из них с быстрым возвратом {sum(1 for e in ev if e['kind'] == 'возврат')}, удержались {sum(1 for e in ev if e['kind'] == 'удержался')}\n")
def grp(name, sel):
    g = [e for e in ev if sel(e)]
    if len(g) < 5: return
    c = Counter(e["out"] for e in g)
    print(f"  {name:<58} n={len(g):4d} · вниз {c['вниз'] / len(g) * 100:3.0f}% · вверх {c['вверх'] / len(g) * 100:3.0f}% · стоит {c['стоит'] / len(g) * 100:3.0f}%")
for kind in ("возврат", "удержался"):
    print(f"ПРОБОЙ {kind.upper()} — исход за 12 ч (−5% раньше +5% = вниз):")
    K = lambda e, kind=kind: e["kind"] == kind
    grp("все", K)
    grp("доска за сутки > +1%", lambda e: K(e) and e["bg"] is not None and e["bg"] > 1)
    grp("доска −1…+1%", lambda e: K(e) and e["bg"] is not None and -1 <= e["bg"] <= 1)
    grp("доска < −1%", lambda e: K(e) and e["bg"] is not None and e["bg"] < -1)
    grp("монета в ходу (≥ +40% за 48 ч)", lambda e: K(e) and e["move"] is not None and e["move"] >= 40)
    grp("  в ходу и доска > +1%", lambda e: K(e) and e["move"] is not None and e["move"] >= 40 and e["bg"] is not None and e["bg"] > 1)
    grp("  в ходу и доска ≤ +1%", lambda e: K(e) and e["move"] is not None and e["move"] >= 40 and e["bg"] is not None and e["bg"] <= 1)
    grp("монета не в ходу (< +40%)", lambda e: K(e) and e["move"] is not None and e["move"] < 40)
    grp("пробойный бар ≥ +5%", lambda e: K(e) and e["bar"] >= 5)
    grp("пробойный бар < +5%", lambda e: K(e) and e["bar"] < 5)
    print()
# по монетам: у кого возвраты чаще всего вниз (почерк ММ), минимум 4 возврата
per = defaultdict(list)
for e in ev:
    if e["kind"] == "возврат": per[e["sym"]].append(e["out"])
rows = [(s, len(o), sum(1 for x in o if x == "вниз") / len(o) * 100) for s, o in per.items() if len(o) >= 4]
print("монеты с ≥4 возвратами: доля «вниз» — топ и низ:")
for s, n, d in sorted(rows, key=lambda r: -r[2])[:8]: print(f"  {s[:-4]:<10} n={n:2d} · вниз {d:3.0f}%")
print("  …")
for s, n, d in sorted(rows, key=lambda r: r[2])[:6]: print(f"  {s[:-4]:<10} n={n:2d} · вниз {d:3.0f}%")
