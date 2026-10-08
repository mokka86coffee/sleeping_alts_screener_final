#!/usr/bin/env python3
"""R57 снято и R80 (08.10): сканер больше не пропускает вынос из-за широкой свечи; шорт после выноса шортов при свече выноса ≥ FAST3_FLUSH_WIDE_BAR % идёт особо:
всегда 900 $, стоп 20 %, цель 20 %, срок 16 ч, после 5 % стоп на вход, после 10 % стоп на +5 %; вынос лонгов и правило шести часов его не закрывают.
Запуск: .venv/bin/python claude/research/test_wide_stop.py"""
import sys, inspect, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft, core_config as cc
bad = []
if cc.FAST3_FLUSH_BAR_MAX: bad.append("R57 не снято: FAST3_FLUSH_BAR_MAX не ноль")
if (cc.FAST3_FLUSH_WIDE_BAR, cc.FAST3_FLUSH_WIDE_SL, cc.FAST3_FLUSH_WIDE_USD, cc.FAST3_FLUSH_WIDE_HOLD_MIN, cc.FAST3_FLUSH_WIDE_TP) != (8.0, 0.20, 900.0, 960, 0.20): bad.append("мерки R80 не те")
if (cc.FAST3_FLUSH_WIDE_BE_AT, cc.FAST3_FLUSH_WIDE_TRAIL_AT, cc.FAST3_FLUSH_WIDE_TRAIL_TO) != (0.05, 0.10, 0.05): bad.append("перенос стопа R80 не 5 % → вход, 10 % → +5 %")
src = inspect.getsource(ft.flush_entries)
i = src.find('if not kind and new_side == -1 and side == "short":'); j = src.find("stop_abs=_wsl")
if not (0 <= i < j): bad.append("в сканере нет ветки R80 перед входом")
if 'p.get("wide")' not in src: bad.append("сканер не бережёт открытый шорт на широкой свече от других выносов")
for fn in (ft.step, ft.wake_step):
    if "wide_walk(e, pos, k)" not in inspect.getsource(fn): bad.append(f"{fn.__name__}: нет ведения позиции R80")
# вход сканера
ft.ses_gate = lambda now, t_bar, side=1: (True, "тест", None); ft._rate_ok = lambda now, note=False: None
ft._flat_target = lambda sym, c, tgt: (tgt, ""); ft.fon = lambda: {}; ft._bub = lambda sym: {}
now = time.time()
st, ev, msgs = {"open": {}}, [], []
ft._open_short_now(st, ev, msgs, "TESTUSDT", 1.0, int(now * 1000), now, "R52 вынос → против хода: тест", "всплеск/вынос", False, side=-1, mode="", stop_abs=cc.FAST3_FLUSH_WIDE_SL)
p = st["open"].get("TESTUSDT") or {}
if (p.get("stop"), p.get("target"), p.get("hold_min"), p.get("wide")) != (0.20, 0.20, 960, True): bad.append(f"вход R80: стоп/цель/срок/метка {p.get('stop')}, {p.get('target')}, {p.get('hold_min')}, {p.get('wide')}")
if not ev or ev[0].get("usd_fix") != 900.0: bad.append("во входе R80 нет суммы 900 $")
ft._size_events(st, ev, now, "всплеск/вынос")
if ev and (ev[0].get("usd_in") != 900.0 or abs(st["open"]["TESTUSDT"].get("k", 0) - 900.0 / ft.FAST3_SIZE) > 1e-3): bad.append(f"размер входа R80 {ev and ev[0].get('usd_in')} $, ждали 900")
st2, ev2 = {"open": {}}, []
ft._open_short_now(st2, ev2, [], "TESTUSDT", 1.0, int(now * 1000), now, "R52 вынос → против хода: тест", "всплеск/вынос", False, side=-1, mode="")
p2 = st2["open"].get("TESTUSDT") or {}
if p2.get("stop") != cc.FAST3_SHORT_SL or p2.get("wide") or ev2[0].get("usd_fix"): bad.append("обычный вход сканера задет: стоп не 10 % или получил метку R80")
# ведение по свечам
bar = lambda h, l: [0, 1.0, h, l, 1.0]; P = dict(stop=0.20, target=0.20)
def chk(name, bars, want):
    r = ft.wide_walk(1.0, P, bars)
    got = (None if r[0] is None else round(r[0], 4), r[1], r[2])
    if got != want: bad.append(f"{name}: {got}, ждали {want}")
chk("рост 15 % не выбивает", [bar(1.15, 1.0)], (None, None, None))
chk("рост 21 % — стоп", [bar(1.21, 1.0)], (-0.20, "стоп", None))
chk("после −5 % стоп на входе", [bar(1.0, 0.94)], (None, None, 0.0))
chk("после −5 % возврат к входу", [bar(1.0, 0.94), bar(1.001, 0.97)], (0.0, "стоп в безубыток", 0.0))
chk("после −10 % стоп на +5 %", [bar(1.0, 0.94), bar(0.96, 0.895)], (None, None, 0.05))
chk("после −10 % возврат к −5 %", [bar(1.0, 0.94), bar(0.96, 0.895), bar(0.951, 0.9)], (0.05, "стоп в +5%", 0.05))
chk("цель 20 %", [bar(1.0, 0.94), bar(0.94, 0.89), bar(0.9, 0.79)], (0.20, "цель", 0.05))
# вынос лонгов и правило шести часов не закрывают
W = dict(sym="TESTUSDT", side=-1, px=1.0, t_ms=int((now - 8 * 3600) * 1000), at=now - 8 * 3600, stop=0.20, target=0.20, wide=True, flush=True, rule="R52 вынос → против хода: тест")
if ft.fuel_exit("TESTUSDT", W, now, 0.97) is not None: bad.append("вынос лонгов закрывает шорт R80")
if ft._stall_exit(W, [bar(1.05, 0.99)] * 200, now, 1.04) is not None: bad.append("правило шести часов (R66) закрывает шорт R80")
if ft._hold_lim(dict(W, hold_min=960)) != 960: bad.append("срок R80 не 16 часов")
print("R57 снято, R80: " + ("ок — шорт на широкой свече выноса: 900 $, стоп и цель 20 %, срок 16 ч, стоп на вход после 5 % и на +5 % после 10 %; остальные входы не задеты" if not bad else "СБОЙ: " + "; ".join(bad)))
sys.exit(1 if bad else 0)
