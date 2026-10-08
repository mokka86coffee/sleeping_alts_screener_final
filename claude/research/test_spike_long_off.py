#!/usr/bin/env python3
"""R78 (06.10) и его отмена (08.10, владелец: «лонги верни на всплесках»): выключатель лонгов на всплеске стоит в обеих книгах перед проверкой окна
без лонгов и не задевает шорты; сейчас он ВКЛЮЧАЕТ лонги (FAST3_SPIKE_LONG_ON = True). Запуск: .venv/bin/python claude/research/test_spike_long_off.py"""
import sys, inspect
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft, core_config as cc
bad = []
if cc.FAST3_SPIKE_LONG_ON is not True: bad.append("FAST3_SPIKE_LONG_ON не True — владелец 08.10 вернул лонги на всплесках")
if ft._spike_long_off(): bad.append("_spike_long_off() режет лонги при включённой настройке")
for fn in (ft.step, ft.wake_step):
    src = inspect.getsource(fn); i = src.find("if sd == 1 and not _ws and _spike_long_off()"); j = src.find("_lw = _long_window_closed(now)")
    if not (0 <= i < j): bad.append(f"{fn.__name__}: выключателя нет перед окном без лонгов")
    if "лонги на всплеске выключены (R78)" not in src: bad.append(f"{fn.__name__}: нет подписи отказа")
keep = cc.FAST3_SPIKE_LONG_ON; cc.FAST3_SPIKE_LONG_ON = False
if not ft._spike_long_off(): bad.append("при выключенной настройке выключатель не режет — механизм сломан")
cc.FAST3_SPIKE_LONG_ON = keep
print("R78: " + ("ок — лонги на всплеске включены (владелец 08.10), выключатель на месте в обеих книгах и работает" if not bad else "СБОЙ: " + "; ".join(bad)))
sys.exit(1 if bad else 0)
