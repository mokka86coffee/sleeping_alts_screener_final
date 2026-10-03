#!/usr/bin/env python3
"""МОИ МОНЕТЫ (03.10 владелец: «возьми монеты, которые ты видишь сам, и запиши результат»; «скидываешь мне то, что я сам могу увидеть»).
Бумажный журнал моих собственных входов: лонг по цене на момент записи, 1000 $ на монету. Выход один — часовая свеча закрылась под уровнем «ломает»
(пробой: верх полки; полка: низ полки). Цели и срока нет. Бота и демо не трогает.
    .venv/bin/python claude/research/my_picks.py            — обновить и показать
    .venv/bin/python claude/research/my_picks.py add SYM kind level "почему"   — добавить (цена берётся с биржи сейчас)
Состояние: output/my_picks.json · таблица: claude/research/my_picks.md"""
import json, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; ST = ROOT / "output" / "my_picks.json"; MD = Path(__file__).with_suffix(".md")
L = timezone(timedelta(hours=3)); F = "https://fapi.binance.com"; SIZE = 1000.0; FEE = 0.001
def get(u):
    for _ in range(3):
        try: return json.load(urllib.request.urlopen(u, timeout=20))
        except Exception: time.sleep(1)
    return None
def load():
    try: return json.loads(ST.read_text(encoding="utf-8"))
    except (OSError, ValueError): return {"picks": []}
def save(d): ST.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
d = load()
if len(sys.argv) >= 5 and sys.argv[1] == "add":
    sym = sys.argv[2].upper(); sym = sym if sym.endswith("USDT") else sym + "USDT"
    px = float(get(f"{F}/fapi/v1/ticker/price?symbol={sym}")["price"])
    d["picks"].append(dict(sym=sym, kind=sys.argv[3], level=float(sys.argv[4]), why=sys.argv[5] if len(sys.argv) > 5 else "", px=px, at=time.time(), status="open"))
    save(d)
now = time.time()
for p in d["picks"]:
    k = get(f"{F}/fapi/v1/klines?symbol={p['sym']}&interval=1h&startTime={int(p['at'] // 3600 * 3600) * 1000}&limit=1000") or []
    k = [x for x in k if int(x[0]) / 1000 >= p["at"] - 3600]
    if not k: continue
    e = p["px"]; closed = [x for x in k if int(x[6]) / 1000 < now and int(x[0]) / 1000 >= p["at"]]
    if p["status"] == "open":
        for x in closed:                                     # выход: часовая свеча закрылась под уровнем
            if float(x[4]) < p["level"]:
                p.update(status="closed", out=float(x[4]), out_at=int(x[6]) / 1000, res=round((float(x[4]) / e - 1 - FEE) * 100, 2)); break
    end = p.get("out_at", now); seg = [x for x in k if int(x[0]) / 1000 <= end]
    p["max"] = round((max(float(x[2]) for x in seg) / e - 1) * 100, 2); p["min"] = round((min(float(x[3]) for x in seg) / e - 1) * 100, 2)
    p["now"] = float(k[-1][4]); p["now_pct"] = round((p["now"] / e - 1) * 100, 2)
save(d)
f = lambda t: datetime.fromtimestamp(t, L).strftime("%d.%m %H:%M")
rows = ["# Мои монеты — бумажный журнал (обновлено " + f(now) + ")", "", "Лонг по цене записи, 1000 $, выход — часовая свеча закрылась под уровнем. Без цели и срока.", "",
        "| монета | тип | вход | когда | ломает | сейчас | итог/сейчас | макс | мин | статус | почему |", "|---|---|---|---|---|---|---|---|---|---|---|"]
tot = 0.0
for p in d["picks"]:
    r = p.get("res") if p["status"] == "closed" else p.get("now_pct", 0.0); tot += (r or 0) * SIZE / 100
    rows.append(f"| {p['sym'][:-4]} | {p['kind']} | {p['px']:g} | {f(p['at'])} | {p['level']:g} | {p.get('now', 0):g} | {r:+.2f}% | {p.get('max', 0):+.1f}% | {p.get('min', 0):+.1f}% | "
                + (f"закрыта {f(p['out_at'])} по {p['out']:g}" if p["status"] == "closed" else "открыта") + f" | {p['why']} |")
rows += ["", f"Итого при 1000 $ на монету: {tot:+.0f} $ ({sum(1 for p in d['picks'] if p['status'] == 'open')} открыто, {sum(1 for p in d['picks'] if p['status'] == 'closed')} закрыто)"]
MD.write_text("\n".join(rows) + "\n", encoding="utf-8")
print(" · ".join(f"{p['sym'][:-4]} {(p.get('res') if p['status'] == 'closed' else p.get('now_pct', 0)):+.1f}%{' (закрыта)' if p['status'] == 'closed' else ''}" for p in d["picks"]) + f" · итого {tot:+.0f} $")
