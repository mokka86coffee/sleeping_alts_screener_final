#!/usr/bin/env python3
"""ЧТО ИЗМЕНИЛОСЬ: настоящие сделки бота за последние 48 ч против пересчёта тем же кодом по нынешним правилам (03.10 19:20, владелец: «проверь все сделки бота после всех изменений
за последние 48 часов по всем правилам и напиши, что изменилось»; «много разногласий будет, я нить теряю — проверь сначала, и потом будет понятно»).
Настоящие: журнал до слияния (копия в scratchpad) + живые события после него. Пересчёт: папка replay_day.py (REPLAY_HOURS=48). Книга «всплеск/вынос».
    .venv/bin/python claude/research/replay_compare.py ПАПКА_ПЕРЕСЧЁТА ЖУРНАЛ_ДО_СЛИЯНИЯ"""
import sys, json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
ROOT = Path(__file__).resolve().parents[2]; WD = Path(sys.argv[1]); OLD = Path(sys.argv[2]); L = timezone(timedelta(hours=3))
meta = json.load(open(WD / "meta.json")); T0, T1 = meta["d0"], meta["end"]; f = lambda t: datetime.fromtimestamp(t, L).strftime("%d.%m %H:%M")
def load(p, pred=lambda r: True):
    ent, ex = {}, {}
    for ln in open(p, encoding="utf-8"):
        try: r = json.loads(ln)
        except ValueError: continue
        if not pred(r): continue
        if r.get("kind") == "entry": ent[(r["sym"], round(r["at"]))] = r
        elif r.get("kind") in ("exit_long", "exit_short"): ex[(r["sym"], round(r.get("opened_at", 0)))] = r
    return ent, ex
ent_r, ex_r = load(OLD)
cut = max(r["at"] for r in ent_r.values()) if ent_r else 0
e2, x2 = load(ROOT / "output" / "paper_fast3.jsonl", lambda r: not r.get("replay") and r.get("at", 0) > 1791036600)   # живые события после слияния 17:10
ent_r.update(e2); ex_r.update(x2)
ent_p, ex_p = load(WD / "output" / "paper_fast3.jsonl")
def trades(ent, ex):
    out = []
    for (sym, at), e in ent.items():
        if not (T0 <= e["at"] <= T1): continue
        x = ex.get((sym, at)); out.append(dict(sym=sym, at=e["at"], side=e["side"], px=e["px"], rule=str(e.get("rule") or ""), usd=x.get("usd") if x else None, why=str(x.get("why_exit")) if x else "открыта", out=x["at"] if x else None))
    return sorted(out, key=lambda t: t["at"])
def kind(t):
    r = t["rule"]
    if "ошибка сканера" in t["why"]: return "ошибочная пачка сканера 03.10 (моя ошибка)"
    if r.startswith("R52") or r.startswith("R49") or "вынос →" in r[:40] or "вынос шортов →" in r[:40]: return "сканер выносов"
    if r.startswith("всплеск → шорт 5/5"): return "всплеск → шорт 5/5"
    if "вход после вершины" in r or r.startswith("перевёрнутый") or "сторона перевёрнута" in r[:80]: return "шорт после вершины / переворот"
    if "лонг-переворот" in r or "переворот" in r[:30]: return "переворот"
    return "лонг по всплеску" if t["side"] == 1 else "шорт прочий"
R = trades(ent_r, ex_r); P = trades(ent_p, ex_p)
def summ(nm, T):
    cl = [t for t in T if t["usd"] is not None]; print(f"\n{nm}: входов {len(T)}, закрыто {len(cl)} на {sum(t['usd'] for t in cl):+.0f} $, в плюс {sum(1 for t in cl if t['usd'] > 0)}, ещё открыто {len(T) - len(cl)}")
    g = defaultdict(list)
    for t in T: g[kind(t)].append(t)
    for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
        c = [t for t in v if t["usd"] is not None]; print(f"    {k:44s} входов {len(v):3d} · закрыто {len(c):3d} · {sum(t['usd'] for t in c):+6.0f} $ · в плюс {sum(1 for t in c if t['usd'] > 0)} · лонгов {sum(1 for t in v if t['side'] == 1)} / шортов {sum(1 for t in v if t['side'] == -1)}")
    d = defaultdict(list)
    for t in cl: d[datetime.fromtimestamp(t["at"], L).strftime("%d.%m")].append(t["usd"])
    print("    по дню входа: " + " · ".join(f"{k}: {len(v)} сд. {sum(v):+.0f} $" for k, v in sorted(d.items(), key=lambda kv: (kv[0][3:], kv[0][:2]))))
print(f"окно {f(T0)} → {f(T1)}")
summ("НАСТОЯЩИЕ СДЕЛКИ БОТА", R); summ("НАСТОЯЩИЕ без ошибочной пачки", [t for t in R if "ошибка сканера" not in t["why"]]); summ("ПЕРЕСЧЁТ ПО НЫНЕШНИМ ПРАВИЛАМ", P)
# сопоставление: та же монета, вход в пределах 15 минут
used = set(); same = flip = 0; only_r = []; flips = []
for t in R:
    if "ошибка сканера" in t["why"]: continue
    m = next((j for j, p in enumerate(P) if j not in used and p["sym"] == t["sym"] and abs(p["at"] - t["at"]) <= 900), None)
    if m is None: only_r.append(t); continue
    used.add(m)
    if P[m]["side"] == t["side"]: same += 1
    else: flip += 1; flips.append((t, P[m]))
only_p = [p for j, p in enumerate(P) if j not in used]
u = lambda T: sum(t["usd"] or 0 for t in T)
print(f"\nСОПОСТАВЛЕНИЕ (монета и время входа ±15 мин): совпало со стороной {same} · та же точка, другая сторона {flip} · было, а теперь не берётся {len(only_r)} ({u(only_r):+.0f} $) · не было, а теперь берётся {len(only_p)} ({u(only_p):+.0f} $)")
print("\nТА ЖЕ ТОЧКА, ДРУГАЯ СТОРОНА:")
for a, b in flips: print(f"  {f(a['at'])} {a['sym'][:-4]:9s} было {'Л' if a['side'] == 1 else 'Ш'} {a['usd'] if a['usd'] is not None else 0:+5.0f}$ ({a['why'][:22]}) → стало {'Л' if b['side'] == 1 else 'Ш'} {b['usd'] if b['usd'] is not None else 0:+5.0f}$ ({b['why'][:22]}) · {kind(b)}")
for nm, T in (("БЫЛО, ТЕПЕРЬ НЕ БЕРЁТСЯ", only_r), ("НЕ БЫЛО, ТЕПЕРЬ БЕРЁТСЯ", only_p)):
    g = defaultdict(list)
    for t in T: g[kind(t)].append(t)
    print(f"\n{nm}:")
    for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])): print(f"  {k}: {len(v)} входов, {u(v):+.0f} $ · " + ", ".join(f"{t['sym'][:-4]} {'Л' if t['side'] == 1 else 'Ш'} {f(t['at'])[6:]} {(t['usd'] or 0):+.0f}" for t in v[:14]) + (" …" if len(v) > 14 else ""))
