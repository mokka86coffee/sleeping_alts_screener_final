"""04.10 20:20: сканер выносов не берёт шорт в монете ручного списка лестницы (R47). Запуск: .venv/bin/python claude/research/test_scanman.py"""
import os, sys, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import fast_tier as ft
from core_config import FAST3_NO_SHORT_MANUAL

assert ft._manual_no_short("MONUSDT") and "MONUSDT" in FAST3_NO_SHORT_MANUAL
assert not ft._manual_no_short("BTCUSDT")
src = inspect.getsource(ft.flush_entries)
i_pe = src.index("if rise >= _pr:"); i_man1 = src.index("_manual_no_short(sym)", i_pe); i_set = src.index("_pump_end_set(sym, now)", i_pe)
assert i_pe < i_man1 < i_set, "R58: проверка списка должна стоять до отметки сквиза и закрытия лонга"
i_side = src.index("new_side = -1 if kind"); i_man2 = src.index("new_side == -1 and _manual_no_short(sym)"); i_close = src.index('kind="exit_long" if sd == 1 else "exit_short"')
assert i_side < i_man2 < i_close, "обычная клетка: проверка списка до закрытия открытой позиции и входа"
print("сканер и ручной список лестницы: ок")
