#!/usr/bin/env python3
"""ПЕРЕСЧЁТ ДНЯ, шаг 3 — слияние в книгу бота (03.10, владелец: «…и внеси в бота, ошибочные все удали из книги»; «ошибочные те, что 120 открытых ночью»).
Из журнала output/paper_fast3.jsonl убираются сегодняшние события позиций, открытых сегодня до момента конца пересчёта (ошибочная пачка сканера и сделки по старым правилам),
кроме NIGHT (ручной вход по слову владельца) и позиций, открытых до полуночи. На их место встают входы и выходы пересчёта (rule с пометкой «пересчёт 03.10»).
В книгу (output/paper_fast3.json) добавляются позиции, которые по пересчёту ещё открыты; живые позиции бота не трогаются. Выполнять ТОЛЬКО при остановленном боте.
    .venv/bin/python claude/research/replay_merge.py ПАПКА_ПЕРЕСЧЁТА [--write]"""
import sys, json, time, shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
ROOT = Path(__file__).resolve().parents[2]; WD = Path(sys.argv[1]); WRITE = "--write" in sys.argv; L = timezone(timedelta(hours=3))
meta = json.load(open(WD / "meta.json")); d0, CUT, locked = meta["d0"], meta["end"], meta["locked"]
J = ROOT / "output" / "paper_fast3.jsonl"; SF = ROOT / "output" / "paper_fast3.json"; TAG = "пересчёт 03.10 по новым правилам: "
keep_old, today = [], []
for ln in open(J, encoding="utf-8"):
    try: r = json.loads(ln)
    except ValueError: continue
    (today if r.get("at", 0) >= d0 else keep_old).append(r)
def keep(r):
    s = r.get("sym"); k = r.get("kind")
    if s == "NIGHTUSDT": return True
    if k == "entry": return r["at"] >= CUT
    if k in ("exit_long", "exit_short"): return r.get("opened_at", 0) < d0 or r.get("opened_at", 0) >= CUT
    if k == "follow": return s in locked or r["at"] >= CUT
    return True
kept = [r for r in today if keep(r)]; drop = [r for r in today if not keep(r)]
rep = []
for ln in open(WD / "output" / "paper_fast3.jsonl", encoding="utf-8"):
    try: r = json.loads(ln)
    except ValueError: continue
    if r.get("kind") not in ("entry", "exit_long", "exit_short"): continue
    r["replay"] = "03.10"; r["rule"] = TAG + str(r.get("rule") or ""); rep.append(r)
new_today = sorted(kept + rep, key=lambda r: r["at"])
live = json.load(open(SF)); rs = json.load(open(WD / "state_end.json")); add = {}
for s, p in rs["open"].items():
    if s in live.get("open", {}): continue
    p = dict(p); p["rule"] = TAG + str(p.get("rule") or ""); p["replay"] = "03.10"; add[s] = p
new = dict(live); new["open"] = dict(live.get("open", {})); new["open"].update(add)
le = dict(live.get("last_exit", {}))
for s, t in rs.get("last_exit", {}).items():
    if t < 1e11: le[s] = max(le.get(s, 0), t)
new["last_exit"] = le
pend = dict(rs.get("pending", {})); pend.update(live.get("pending", {})); new["pending"] = {s: v for s, v in pend.items() if s not in new["open"]}
fh = dict(live.get("flush_hour", {}))
for s, h in rs.get("flush_hour", {}).items(): fh[s] = max(fh.get(s, 0), h)
new["flush_hour"] = fh
f = lambda t: datetime.fromtimestamp(t, L).strftime("%H:%M")
ex_drop = [r for r in drop if r.get("kind") in ("exit_long", "exit_short")]; ex_rep = [r for r in rep if r["kind"] != "entry"]; en_rep = [r for r in rep if r["kind"] == "entry"]
print(f"граница пересчёта {f(CUT)} · убираю из журнала: входов {sum(1 for r in drop if r.get('kind') == 'entry')}, выходов {len(ex_drop)} на {sum(r.get('usd', 0) for r in ex_drop):+.0f} $ "
      f"(из них ошибочная пачка {sum(1 for r in ex_drop if 'ошибка сканера' in str(r.get('why_exit')))} на {sum(r.get('usd', 0) for r in ex_drop if 'ошибка сканера' in str(r.get('why_exit'))):+.0f} $)")
print(f"вставляю пересчёт: входов {len(en_rep)}, выходов {len(ex_rep)} на {sum(r.get('usd', 0) for r in ex_rep):+.0f} $; в книгу добавляю открытых {len(add)}: {', '.join(s[:-4] for s in add)}")
kept_ex = [r for r in kept if r.get("kind") in ("exit_long", "exit_short")]
print(f"остаются настоящие выходы сегодня (позиции до полуночи и NIGHT): {len(kept_ex)} на {sum(r.get('usd', 0) for r in kept_ex):+.0f} $ → день после слияния: закрытые {sum(r.get('usd', 0) for r in kept_ex + ex_rep):+.0f} $")
if WRITE:
    bk = WD / "backup"; bk.mkdir(exist_ok=True); stamp = datetime.now(L).strftime("%H%M%S")
    shutil.copy(J, bk / f"paper_fast3_{stamp}.jsonl"); shutil.copy(SF, bk / f"paper_fast3_{stamp}.json")
    tmp = J.with_suffix(".merge_tmp")
    with open(tmp, "w", encoding="utf-8") as o:
        for r in keep_old + new_today: o.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(J)
    tmp = SF.with_suffix(".merge_tmp"); tmp.write_text(json.dumps(new, ensure_ascii=False), encoding="utf-8"); tmp.replace(SF)
    try:
        lc_r = json.load(open(WD / "output" / "london_count.json")); p = ROOT / "output" / "london_count.json"
        try: lc = json.load(open(p))
        except Exception: lc = {"day": lc_r.get("day"), "n": 0}
        if lc.get("day") == lc_r.get("day"): lc["n"] = max(lc.get("n", 0), lc_r.get("n", 0)); p.write_text(json.dumps(lc), encoding="utf-8")
    except Exception: pass
    print(f"записано; копии до слияния: {bk}")
