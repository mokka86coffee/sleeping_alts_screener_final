#!/usr/bin/env python3
"""ПЕРЕСЧЁТ ДНЯ, шаг 3б — позиции пересчёта в книгу бота без гонки со сторожем (03.10 17:20).
Первое слияние записало книгу, когда сторож уже поднял бота со старой книгой в памяти, и бот её затёр. Здесь: берём замок бота (output/fast_tier.lock) сразу после его остановки —
пока замок у нас, новый бот не стартует («уже работает»); под замком читаем книгу, добавляем открытые позиции пересчёта, пишем, отпускаем.
    .venv/bin/python claude/research/replay_state_merge.py ПАПКА_ПЕРЕСЧЁТА PID_БОТА"""
import sys, json, os, time, fcntl, signal, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; WD = Path(sys.argv[1]); pid = int(sys.argv[2]); SF = ROOT / "output" / "paper_fast3.json"; TAG = "пересчёт 03.10 по новым правилам: "
lk = open(ROOT / "output" / "fast_tier.lock", "a")
os.kill(pid, signal.SIGTERM); t = time.time()
while True:
    try: fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB); break
    except OSError:
        if time.time() - t > 30: print("замок не получен за 30 с — ничего не менял"); sys.exit(1)
        time.sleep(0.02)
print(f"замок получен через {time.time() - t:.2f} с")
live = json.load(open(SF)); rs = json.load(open(WD / "state_end.json")); shutil.copy(SF, WD / "backup" / f"paper_fast3_before_state_merge_{int(time.time())}.json")
add = {}
for s, p in rs["open"].items():
    if s in live.get("open", {}): continue
    p = dict(p); p["rule"] = TAG + str(p.get("rule") or ""); p["replay"] = "03.10"; add[s] = p
live.setdefault("open", {}).update(add)
le = live.setdefault("last_exit", {})
for s, tt in rs.get("last_exit", {}).items():
    if tt < 1e11: le[s] = max(le.get(s, 0), tt)
pend = dict(rs.get("pending", {})); pend.update(live.get("pending", {})); live["pending"] = {s: v for s, v in pend.items() if s not in live["open"]}
fh = live.setdefault("flush_hour", {})
for s, h in rs.get("flush_hour", {}).items(): fh[s] = max(fh.get(s, 0), h)
tmp = SF.with_suffix(".merge_tmp"); tmp.write_text(json.dumps(live, ensure_ascii=False), encoding="utf-8"); tmp.replace(SF)
print(f"в книгу добавлено {len(add)}: {', '.join(s[:-4] for s in add)} · всего открыто {len(live['open'])}")
fcntl.flock(lk, fcntl.LOCK_UN); lk.close()
