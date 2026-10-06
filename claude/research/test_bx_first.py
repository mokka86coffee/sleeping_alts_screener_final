#!/usr/bin/env python3
"""«Сначала биржа, потом всё остальное» (06.10): сообщение о сделке в Телеграм не уходит в момент решения — ждёт в очереди и отправляется после ордеров BingX."""
import sys, time, inspect, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft
bad, calls = [], []
real = subprocess.Popen
class P:
    def __init__(self, a, **k): calls.append(a)
subprocess.Popen = P
try:
    pos = dict(sym="XUSDT", side=1, px=1.0, t_ms=int(time.time() * 1000), at=time.time(), target=0.05, stop=0.1, hold_min=120, rule="проба")
    ft._TGQ.clear()
    ft.cg("XUSDT", *ft.cg_caption("всплеск/вынос", "XUSDT", pos))
    if calls: bad.append("сообщение ушло сразу, до биржи")
    if len(ft._TGQ) != 1: bad.append("сообщение не встало в очередь")
    ft._tg_flush()
    if len(calls) != 1 or ft._TGQ: bad.append("очередь не отправлена")
finally:
    subprocess.Popen = real
for fn in (ft.step, ft.wake_step):
    src = inspect.getsource(fn); tail = src[src.rindex("if write:"):]
    i_bx, i_log, i_tg = tail.find("_bingx(ev)"), tail.find(".open(\"a\""), tail.find("_tg_flush()")
    if not (0 <= i_bx < i_log < i_tg): bad.append(f"{fn.__name__}: порядок не «биржа → журнал → Телеграм»")
print("БИРЖА ПЕРВОЙ: " + ("ок — ордера BingX идут до журнала и Телеграма в обеих книгах" if not bad else "СБОЙ: " + "; ".join(bad)))
sys.exit(1 if bad else 0)
