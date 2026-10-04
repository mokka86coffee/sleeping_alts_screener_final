#!/usr/bin/env python3
"""МОИ МОНЕТЫ (03.10 владелец: «возьми монеты, которые ты видишь сам, и запиши результат»; «ты проверь сначала сам свой анализ»).
Бумажный журнал моих собственных входов, 1000 $ на монету, комиссия 0.1 % на круг. Бота и демо не трогает. Два вида записей:
  1) по уровню (03.10 утро): лонг, выход один — часовая свеча закрылась под уровнем «ломает». Цели и срока нет.
  2) группой (03.10, проверка отпечатков из leaders_tv.md ВНЕ выборки): вся группа целиком, без выбора «на глаз»; сторона, цель, стоп, срок заданы заранее;
     по часовым свечам: задет стоп → стоп; задета цель → цель; оба в одной свече → стоп; срок вышел → закрытие по цене.
    .venv/bin/python claude/research/my_picks.py                                  — обновить и показать
    .venv/bin/python claude/research/my_picks.py add SYM kind level "почему"      — запись по уровню (цена с биржи сейчас)
    .venv/bin/python claude/research/my_picks.py addg ГРУППА side tp sl дней SYM1,SYM2 "почему"   — группа (side 1 лонг / -1 шорт; tp, sl в долях)
Запросы к бирже: один на монету раз в запуск (часовые свечи с момента входа) — прогон не нагружает.
Состояние: output/my_picks.json · журнал: claude/research/my_picks.md"""
import json, sys, time, urllib.request, urllib.parse
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
if len(sys.argv) >= 8 and sys.argv[1] == "addg":
    grp, side, tp, sl, days = sys.argv[2], int(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6]); why = sys.argv[8] if len(sys.argv) > 8 else ""
    allp = {x["symbol"]: float(x["price"]) for x in (get(f"{F}/fapi/v1/ticker/price") or [])}; have = {(p["sym"], p.get("group")) for p in d["picks"] if p["status"] == "open"}; miss = []
    for s in sys.argv[7].split(","):
        sym = s.strip().upper(); sym = sym if sym.endswith("USDT") else sym + "USDT"
        if sym not in allp: miss.append(sym); continue
        if (sym, grp) in have: continue
        d["picks"].append(dict(sym=sym, kind="группа", group=grp, side=side, tp=tp, sl=sl, days=days, why=why, px=allp[sym], at=time.time(), status="open"))
    save(d)
    if miss: print("нет цены на бирже, не записаны:", ", ".join(miss))
now = time.time()
for p in d["picks"]:
    if p["status"] == "closed" and p.get("now") is not None and p.get("max") is not None: continue      # закрытые не перезапрашиваем
    k = get(f"{F}/fapi/v1/klines?symbol={urllib.parse.quote(p['sym'])}&interval=1h&startTime={int(p['at'] // 3600 * 3600) * 1000}&limit=1000") or []
    k = [x for x in k if int(x[0]) / 1000 >= p["at"] - 3600]
    if not k: continue
    e = p["px"]; sd = p.get("side", 1); closed = [x for x in k if int(x[6]) / 1000 < now and int(x[0]) / 1000 >= p["at"]]
    if p["status"] == "open" and p.get("kind") == "группа":
        for x in closed:
            hi, lo, cl, t1 = float(x[2]), float(x[3]), float(x[4]), int(x[6]) / 1000
            stop = (lo <= e * (1 - p["sl"])) if sd == 1 else (hi >= e * (1 + p["sl"])); tgt = (hi >= e * (1 + p["tp"])) if sd == 1 else (lo <= e * (1 - p["tp"]))
            if stop: p.update(status="closed", out=e * (1 - sd * p["sl"]), out_at=t1, res=round((-p["sl"] - FEE) * 100, 2), how="стоп"); break
            if tgt: p.update(status="closed", out=e * (1 + sd * p["tp"]), out_at=t1, res=round((p["tp"] - FEE) * 100, 2), how="цель"); break
            if t1 >= p["at"] + p["days"] * 86400: p.update(status="closed", out=cl, out_at=t1, res=round((sd * (cl / e - 1) - FEE) * 100, 2), how="срок"); break
    elif p["status"] == "open":
        for x in closed:                                     # выход: часовая свеча закрылась под уровнем
            if float(x[4]) < p["level"]:
                p.update(status="closed", out=float(x[4]), out_at=int(x[6]) / 1000, res=round((float(x[4]) / e - 1 - FEE) * 100, 2)); break
    end = p.get("out_at", now); seg = [x for x in k if int(x[0]) / 1000 <= end] or k[:1]
    up = round((max(float(x[2]) for x in seg) / e - 1) * 100, 2); dn = round((min(float(x[3]) for x in seg) / e - 1) * 100, 2)
    p["max"], p["min"] = (up, dn) if sd == 1 else (-dn, -up)
    p["now"] = float(k[-1][4]); p["now_pct"] = round(sd * (p["now"] / e - 1) * 100, 2)
save(d)
f = lambda t: datetime.fromtimestamp(t, L).strftime("%d.%m %H:%M")
val = lambda p: (p.get("res") if p["status"] == "closed" else p.get("now_pct", 0.0)) or 0.0
lv = [p for p in d["picks"] if p.get("kind") != "группа"]; gr = {}
for p in d["picks"]:
    if p.get("kind") == "группа": gr.setdefault(p["group"], []).append(p)
rows = ["# Мои монеты — бумажный журнал (обновлено " + f(now) + ")", "", "1000 $ на монету, комиссия 0.1 % на круг. Бот и демо не затронуты.", ""]
summ = []
for g, ps in gr.items():
    p0 = ps[0]; tot = sum(val(p) for p in ps) * SIZE / 100; cl = [p for p in ps if p["status"] == "closed"]
    head = (f"## Группа «{g}» — {'лонг' if p0['side'] == 1 else 'шорт'}, цель {p0['tp']:.0%}, стоп {p0['sl']:.0%}, срок {p0['days']:g} дн · записана {f(min(p['at'] for p in ps))}")
    line = (f"Монет {len(ps)} · открыто {len(ps) - len(cl)} · цель {sum(1 for p in cl if p.get('how') == 'цель')} · стоп {sum(1 for p in cl if p.get('how') == 'стоп')} · срок {sum(1 for p in cl if p.get('how') == 'срок')} · "
            f"итог {tot:+.0f} $ (закрытые {sum(val(p) for p in cl) * SIZE / 100:+.0f} $, открытые по текущей цене {sum(val(p) for p in ps if p['status'] == 'open') * SIZE / 100:+.0f} $)")
    rows += [head, "", p0.get("why", ""), "", line, ""]
    for p in sorted(ps, key=lambda p: -val(p)):
        rows.append(f"- {p['sym'][:-4]}: вход {p['px']:g} · " + (f"{p.get('how')} {f(p['out_at'])}, {val(p):+.1f}%" if p["status"] == "closed" else f"сейчас {p.get('now', 0):g}, {val(p):+.1f}%") + f" · макс {p.get('max', 0):+.1f}% · мин {p.get('min', 0):+.1f}%")
    rows.append(""); summ.append(f"{g}: {tot:+.0f} $ ({len(ps) - len(cl)} откр., цель {sum(1 for p in cl if p.get('how') == 'цель')}, стоп {sum(1 for p in cl if p.get('how') == 'стоп')})")
rows += ["## По уровню (лонг, выход — часовая свеча закрылась под уровнем)", "", "| монета | тип | вход | когда | ломает | сейчас | итог/сейчас | макс | мин | статус | почему |", "|---|---|---|---|---|---|---|---|---|---|---|"]
tot = 0.0
for p in lv:
    r = val(p); tot += r * SIZE / 100
    rows.append(f"| {p['sym'][:-4]} | {p['kind']} | {p['px']:g} | {f(p['at'])} | {p['level']:g} | {p.get('now', 0):g} | {r:+.2f}% | {p.get('max', 0):+.1f}% | {p.get('min', 0):+.1f}% | "
                + (f"закрыта {f(p['out_at'])} по {p['out']:g}" if p["status"] == "closed" else "открыта") + f" | {p['why']} |")
rows += ["", f"Итого по уровню: {tot:+.0f} $ ({sum(1 for p in lv if p['status'] == 'open')} открыто, {sum(1 for p in lv if p['status'] == 'closed')} закрыто)"]
MD.write_text("\n".join(rows) + "\n", encoding="utf-8")
print(" · ".join(f"{p['sym'][:-4]} {val(p):+.1f}%{' (закрыта)' if p['status'] == 'closed' else ''}" for p in lv) + f" · по уровню {tot:+.0f} $" + ("".join(" · " + s for s in summ)))
