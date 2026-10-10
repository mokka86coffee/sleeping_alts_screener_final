#!/usr/bin/env python3
"""R83 (10.10 владелец «все так делай да»): книга «очередь» — лонг после трёх прогонов первой подряд, цель +20 %, стоп −20 %, без безубытка, без перезахода после стопа,
входы ср–вс UTC. Подставной журнал очереди во временной папке, свечи и цена подменены; книги бота и биржу не трогает. Итог — строка «R83: ок»."""
import json, sys, tempfile, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft
import bingx_trader as bx

T = Path(tempfile.mkdtemp()); LOGF = T / "queue_log.jsonl"
def iso(dt): return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
def write_runs(runs):
    """runs: [(dt, first_sym|None)] → журнал: строка _BG на прогон + строка place 1"""
    with LOGF.open("w", encoding="utf-8") as f:
        for dt, sym in runs:
            f.write(json.dumps({"at": iso(dt), "sym": "_BG", "btc_px": 1}) + "\n")
            f.write(json.dumps({"at": iso(dt), "sym": "ZZZUSDT", "place": 2, "in_queue": True}) + "\n")
            if sym: f.write(json.dumps({"at": iso(dt), "sym": sym, "place": 1, "in_queue": True}) + "\n")
now = datetime.now(timezone.utc)
r = [now - timedelta(minutes=m) for m in (95, 65, 35, 5)]
bars = {"v": []}
ft._k3_since = lambda sym, t_ms, now_ms: list(bars["v"])
ft._queue_price = lambda sym: 1.0
ft.cg = lambda *a, **k: None
base_cfg = ft._queue_cfg()
cfgv = dict(base_cfg, on=True, wdays=set(range(7)))
ft._queue_cfg = lambda: dict(cfgv)
errs = []
def chk(c, m):
    if not c: errs.append(m)
def step(st): return ft.queue_step(st, False, log_src=LOGF)

# 1. серия 2 — входа нет
write_runs([(r[0], "BBBUSDT"), (r[1], "AAAUSDT"), (r[2], "AAAUSDT"), (r[3], None)]); st = {"open": {}, "banned": {}}
step(st); chk(not st["open"], "вход при серии 2 / прогоне без первой")
write_runs([(r[0], "BBBUSDT"), (r[1], "AAAUSDT"), (r[2], "AAAUSDT"), (r[3], "AAAUSDT")]); st = {"open": {}, "banned": {}}
m = step(st); chk("AAAUSDT" in st["open"] and st["open"]["AAAUSDT"]["side"] == 1, "нет входа при трёх подряд: " + " | ".join(m))
chk(abs(st["open"]["AAAUSDT"]["target"] - 0.20) < 1e-9 and abs(st["open"]["AAAUSDT"]["stop"] - 0.20) < 1e-9, "цель/стоп не 20/20")
# 2. тот же прогон второй раз не разбирается; серия 4 входа не даёт
del st["open"]["AAAUSDT"]; step(st); chk(not st["open"], "повторный разбор того же прогона")
write_runs([(r[0], "AAAUSDT"), (r[1], "AAAUSDT"), (r[2], "AAAUSDT"), (r[3], "AAAUSDT")]); st = {"open": {}, "banned": {}}
step(st); chk(not st["open"], "вход при серии 4 (не третий прогон)")
# 3. старый прогон (> max_age) — входа нет
old = [now - timedelta(minutes=m) for m in (160, 130, 100, 70)]
write_runs([(old[0], "BBBUSDT"), (old[1], "AAAUSDT"), (old[2], "AAAUSDT"), (old[3], "AAAUSDT")]); st = {"open": {}, "banned": {}}
m = step(st); chk(not st["open"] and any("старше" in x for x in m), "вход по старому прогону: " + " | ".join(m))
# 4. день недели вне списка — входа нет
write_runs([(r[0], "BBBUSDT"), (r[1], "AAAUSDT"), (r[2], "AAAUSDT"), (r[3], "AAAUSDT")]); st = {"open": {}, "banned": {}}
cfgv = dict(base_cfg, on=True, wdays={d for d in range(7) if d != r[3].weekday()})
m = step(st); chk(not st["open"] and any("входы только" in x for x in m), "вход в запрещённый день: " + " | ".join(m))
cfgv = dict(base_cfg, on=True, wdays=set(range(7)))
# 5. стоп: низ свечи ≤ −20 % → выход, запрет; новая серия той же монеты — входа нет
st = {"open": {}, "banned": {}}; step(st); chk("AAAUSDT" in st["open"], "нет входа перед проверкой стопа")
bars["v"] = [[0, "1.0", "1.05", "0.79", "0.80", "0"]]
m = step(st); chk("AAAUSDT" not in st["open"] and "AAAUSDT" in st["banned"] and any("стоп" in x for x in m), "стоп не сработал: " + " | ".join(m))
bars["v"] = []
r2 = [now - timedelta(minutes=m) for m in (30, 20, 10, 2)]
write_runs([(r2[0], "BBBUSDT"), (r2[1], "AAAUSDT"), (r2[2], "AAAUSDT"), (r2[3], "AAAUSDT")])
m = step(st); chk("AAAUSDT" not in st["open"] and any("запрет" in x for x in m), "перезаход после стопа: " + " | ".join(m))
# 6. цель: верх свечи ≥ +20 % → выход в плюс, запрета нет; свеча и со стопом и с целью — стоп
write_runs([(r2[0], "BBBUSDT"), (r2[1], "CCCUSDT"), (r2[2], "CCCUSDT"), (r2[3], "CCCUSDT")]); st = {"open": {}, "banned": {}, "seen_run": None}
step(st); chk("CCCUSDT" in st["open"], "нет входа CCC")
bars["v"] = [[0, "1.0", "1.10", "0.95", "1.05", "0"], [0, "1.05", "1.21", "1.0", "1.15", "0"]]
m = step(st); chk("CCCUSDT" not in st["open"] and "CCCUSDT" not in st["banned"] and any("цель" in x for x in m), "цель не сработала: " + " | ".join(m))
bars["v"] = [[0, "1.0", "1.25", "0.78", "1.0", "0"]]
write_runs([(r2[0], "BBBUSDT"), (r2[1], "DDDUSDT"), (r2[2], "DDDUSDT"), (r2[3], "DDDUSDT")]); st = {"open": {}, "banned": {}}
step(st); m = step(st); chk("DDDUSDT" in st["banned"], "свеча со стопом и целью должна считаться стопом: " + " | ".join(m))
bars["v"] = []
# 7. зеркало BingX: входы только книг BINGX_BOOKS, выходы — любой книги
calls = []
bx.cfg = lambda: dict(bx.DEFAULTS, enabled=True, mode="demo", size_usd=10)
bx.state = lambda: {"open": {"XUSDT": {"side": 1, "px": 1.0}}, "pnl": {}}
bx.sync_stops = lambda c: []
bx.jlog = lambda *a, **k: None
bx.open_position = lambda sym, side, px, why="", c=None, size_usd=None: (calls.append(("open", sym)), {"ok": True})[1]
bx.close_position = lambda sym, px=None, why="", c=None: (calls.append(("close", sym)), {"ok": True})[1]
import core_config
core_config.BINGX_BOOKS = ("очередь",)
bx.on_events([dict(book="всплеск/вынос", sym="AUSDT", kind="entry", side=1, px=1.0), dict(book="очередь", sym="BUSDT", kind="entry", side=1, px=1.0),
              dict(book="пробуждение", sym="XUSDT", kind="exit_long", side=1, px_out=1.1, why_exit="цель")])
chk(("open", "BUSDT") in calls and ("open", "AUSDT") not in calls and ("close", "XUSDT") in calls, f"фильтр книг зеркала: {calls}")
print("R83: ок" if not errs else "СБОЙ R83: " + "; ".join(errs))
