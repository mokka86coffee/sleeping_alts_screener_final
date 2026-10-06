#!/usr/bin/env python3
"""R78 (06.10): лонги на всплеске выключены в обеих книгах; выключатель стоит перед проверкой окна без лонгов и не задевает шорты."""
import sys, inspect
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft, core_config as cc
bad = []
if cc.FAST3_SPIKE_LONG_ON is not False: bad.append("FAST3_SPIKE_LONG_ON не False")
if not ft._spike_long_off(): bad.append("_spike_long_off() не видит выключатель")
for fn in (ft.step, ft.wake_step):
    src = inspect.getsource(fn); i = src.find("if sd == 1 and not _ws and _spike_long_off()"); j = src.find("_lw = _long_window_closed(now)")
    if not (0 <= i < j): bad.append(f"{fn.__name__}: выключателя нет перед окном без лонгов")
    if "лонги на всплеске выключены (R78)" not in src: bad.append(f"{fn.__name__}: нет подписи отказа")
keep = cc.FAST3_SPIKE_LONG_ON; cc.FAST3_SPIKE_LONG_ON = True
if ft._spike_long_off(): bad.append("при включённых лонгах выключатель всё равно режет")
cc.FAST3_SPIKE_LONG_ON = keep
print("R78: " + ("ок — лонги на всплеске выключены в обеих книгах, шорты и остальные лонги не задеты" if not bad else "СБОЙ: " + "; ".join(bad)))
sys.exit(1 if bad else 0)
