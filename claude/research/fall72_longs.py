"""04.10 — правило владельца по BR: «брать историю монеты за 3 последних дня на часовых свечах и смотреть лои: если постепенное падение — не брать лонги; это просто отскоки,
пока не снесёт всех». Счёт по закрытым лонгам журнала бота на часовых свечах TradingView (claude/research/tvd, Binance не трогаем).
Мерка «падение» — та же, что у сканера (_move_10h): минимумы 72 часовых свечей до входа, первая треть против последней: падали = максимум и среднее последней трети ниже, чем у первой;
росли = минимум и среднее последней трети выше; иначе — «ни то ни другое»."""
import json, sys, time, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; TV = ROOT / "claude" / "research" / "tvd"
H = int(sys.argv[1]) if len(sys.argv) > 1 else 72
def lows(sym, t0):
    p = TV / f"{sym}.P_60.json"
    if not p.exists(): return None
    b = [x for x in json.load(open(p))["bars"] if x[0] + 3600 <= t0]
    return [x[3] for x in b[-H:]] if len(b) >= H else None
def move(lw):
    n = len(lw) // 3; f, l = lw[:n], lw[-n:]; a1, a2 = sum(f) / n, sum(l) / n
    if max(l) < max(f) and a2 < a1: return "падали", (a2 / a1 - 1) * 100
    if min(l) > min(f) and a2 > a1: return "росли", (a2 / a1 - 1) * 100
    return "ни то ни другое", (a2 / a1 - 1) * 100
def kind(rule):
    r = str(rule)
    if r.startswith("R52") or "R52 вынос" in r: return "сканер R52"
    if r.startswith("R59"): return "R59"
    if r.startswith("переворот") or "удержался" in r and r.startswith("переворот"): return "переворот в лонг"
    return "всплеск"
rows = []; skip = 0
for f in ("paper_fast3.jsonl", "paper_wake.jsonl"):
    for l in open(ROOT / "output" / f, encoding="utf-8"):
        try: r = json.loads(l)
        except ValueError: continue
        if r.get("kind") != "exit_long" or not r.get("opened_at"): continue
        lw = lows(r["sym"], r["opened_at"])
        if not lw: skip += 1; continue
        m, mv = move(lw)
        rows.append(dict(sym=r["sym"][:-4], usd=r.get("usd", 0), res=r["result_pct"], m=m, mv=mv, k=kind(r.get("rule")), day=time.strftime("%d.%m", time.localtime(r["at"])), why=str(r.get("why_exit", ""))[:14]))
print(f"закрытых лонгов со свечами {len(rows)}, без данных {skip}; окно {H} ч")
def s(nm, xs):
    if not xs: print(f"{nm}: нет"); return
    print(f"{nm}: {len(xs)} сд. · {sum(x['usd'] for x in xs):+.0f} $ · в плюс {sum(x['usd'] > 0 for x in xs)} · на сделку {sum(x['usd'] for x in xs) / len(xs):+.1f} $ · полных стопов {sum(x['res'] <= -9.5 for x in xs)}")
for m in ("падали", "ни то ни другое", "росли"):
    s(m, [x for x in rows if x["m"] == m])
print("— только лонги по всплеску:")
sp = [x for x in rows if x["k"] == "всплеск"]
for m in ("падали", "ни то ни другое", "росли"):
    s("  " + m, [x for x in sp if x["m"] == m])
print("— прочие лонги при падающих минимумах:"); 
for k in ("сканер R52", "R59", "переворот в лонг"): s("  " + k, [x for x in rows if x["k"] == k and x["m"] == "падали"])
fl = [x for x in sp if x["m"] == "падали"]
days = sorted({x["day"] for x in fl}, key=lambda d: (d[3:], d[:2]))
print("лонги по всплеску при падающих минимумах, по дням: " + " · ".join(f"{d} {sum(x['usd'] for x in fl if x['day'] == d):+.0f} $ ({sum(x['day'] == d for x in fl)})" for d in days))
print("BR:", [(x["day"], x["m"], f"{x['mv']:+.0f}%", round(x["usd"])) for x in rows if x["sym"] == "BR"])
print("SAND:", [(x["day"], x["m"], f"{x['mv']:+.0f}%", round(x["usd"])) for x in rows if x["sym"] == "SAND"])
c = collections.Counter(x["sym"] for x in fl); print("чаще всего:", c.most_common(8))
