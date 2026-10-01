#!/usr/bin/env python3
"""ЛИДЕРЫ ПО ДНЯМ (01.10, владелец: «по лидерам сделай разбивку по дням»). Источники: output/leaders.json (текущие лидеры фона: first_seen, max_change_pct, hits_by_day), output/leaders_archive.json
(архив; строки повторяются каждый прогон — берём по (монета, first_seen) последнюю), output/pump_leaders.json (лидер по пампу: +40% за сутки, листинг > 180 дн, оборот).
По каждому дню (UTC+3): «новые лидеры» — монеты, у которых first_seen в этот день (время, сессия, максимум хода от основы, ×от основы), «активные» — монеты с хитами в этот день (hits_by_day, текущие лидеры).
    .venv/bin/python claude/research/leaders_by_day.py → leaders_by_day.md"""
import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; HERE = Path(__file__).parent
L = timezone(timedelta(hours=3))
SES = (("Сидней", 0, 3), ("Токио", 3, 10), ("Лондон", 10, 16), ("Нью-Йорк", 16, 24))
def loc(s): return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(L)
ep = {}
for l in (ROOT / "output/leaders_archive.json").open(encoding="utf-8"):
    if not l.strip(): continue
    a = json.loads(l); ep[(a["symbol"], a["first_seen"])] = dict(sym=a["symbol"][:-4], first=a["first_seen"], mx=a.get("max_change_pct"), upx=a.get("max_up_x"), why=a.get("reason", "")[:30], src="архив", hbd={})
for sym, v in json.load(open(ROOT / "output/leaders.json")).items():
    fs = v.get("first_seen") or v.get("add_at")
    if not fs: continue
    ep[(sym, fs)] = dict(sym=sym[:-4], first=fs, mx=v.get("max_change_pct"), upx=v.get("max_up_x"), why="сейчас в лидерах", src="тек", hbd=v.get("hits_by_day") or {})
P = json.load(open(ROOT / "output/pump_leaders.json"))
days = defaultdict(lambda: {"new": [], "act": []})
for e in ep.values():
    t = loc(e["first"]); d = t.strftime("%Y-%m-%d"); ses = next(n for n, a, b in SES if a <= t.hour < b)
    days[d]["new"].append((t, e, ses))
    for dd, h in (e["hbd"] or {}).items(): days[dd]["act"].append((e["sym"], h, e["mx"], e["upx"]))
md = [f"# Лидеры по дням ({datetime.now(L):%d.%m %H:%M}, UTC+3)", "",
      f"Эпизодов лидера (монета, first_seen): {len(ep)}; текущих {sum(1 for e in ep.values() if e['src'] == 'тек')}; лидеров по пампу (+40%/сутки) в `pump_leaders.json`: {len(P)}. Ход — максимум от основы лидера (`max_change_pct`), ×от основы (`max_up_x`). «Активные» — по хитам в день (только для текущих лидеров, `hits_by_day`). Не проверено.", ""]
for d in sorted(days, reverse=True)[:18]:
    dn, da = days[d]["new"], days[d]["act"]
    md += [f"## {d[8:]}.{d[5:7]}", ""]
    if dn:
        md.append("**Новые лидеры:** " + "; ".join(f"{e['sym']} {t:%H:%M} {s} ход +{(e['mx'] or 0):.0f}% (×{e['upx'] or 0:.1f})" for t, e, s in sorted(dn, key=lambda x: x[0])))
    else: md.append("**Новых лидеров нет**")
    if da:
        da.sort(key=lambda x: -x[1])
        md.append("**Активные (хитов в день):** " + ", ".join(f"{s} {h}" for s, h, m, u in da[:10]) + (f" … всего {len(da)}" if len(da) > 10 else ""))
    md.append("")
(HERE / "leaders_by_day.md").write_text("\n".join(md) + "\n", encoding="utf-8"); print("\n".join(md[:60]))
