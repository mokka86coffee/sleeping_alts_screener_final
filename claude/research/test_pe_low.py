#!/usr/bin/env python3
"""R85 (11.10 владелец: «выход через 72 часа как сейчас или если цена на 20% выше исторического дна за 2 месяца»): шорт «конец роста» закрывается у дна.
Дно подставное, биржу и книги не трогает. Итог — строка «R85: ок»."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft
import core_config

errs = []
def chk(c, m):
    if not c: errs.append(m)
core_config.MANUAL_BY_USER_PUMP_END_LOW_DAYS = 60; core_config.MANUAL_BY_USER_PUMP_END_LOW_PCT = 20
LOW = 0.00131                                                             # JCT: дно за 2 месяца, уровень выхода 0.001572
chk(ft.pump_end_low_exit("JCTUSDT", 0.0019, low=LOW) is None, "цена 45 % над дном — выхода быть не должно")
chk(ft.pump_end_low_exit("JCTUSDT", 0.00158, low=LOW) is None, "цена чуть выше уровня — выхода быть не должно")
r = ft.pump_end_low_exit("JCTUSDT", 0.00157, low=LOW)
chk(r and "R85" in r and "0.001572" in r, f"цена у уровня — должен быть выход: {r}")
chk(ft.pump_end_low_exit("JCTUSDT", 0.0012, low=LOW), "цена ниже дна — выход")
core_config.MANUAL_BY_USER_PUMP_END_LOW_PCT = 0
chk(ft.pump_end_low_exit("JCTUSDT", 0.0012, low=LOW) is None, "0 % — условие выключено")
core_config.MANUAL_BY_USER_PUMP_END_LOW_PCT = 20
real = ft._low_days; ft._low_days = lambda sym, days: None
chk(ft.pump_end_low_exit("JCTUSDT", 0.0012) is None, "нет дневных свечей — условие молчит")
ft._low_days = lambda sym, days: 0.002 if days == 60 else None
chk(ft.pump_end_low_exit("JCTUSDT", 0.0024), "дно берётся за число суток из настройки")
ft._low_days = real
# цена выхода владельца (manual_exit_px, manual_exit_from)
K = [[1000, 0, 0.0026, 0.00154, 0.0016], [2000, 0, 0.0020, 0.00185, 0.0019]]      # первая свеча прокалывает 0.0016, вторая нет
P = {"manual_exit_px": 0.0016}
r = ft.manual_exit(P, 0.002788, -1, K)
chk(r[0] is not None and abs(r[0] - (1 - 0.0016 / 0.002788)) < 1e-9 and "владельца" in r[1], f"шорт: минимум свечей позиции дошёл — выход по цене владельца: {r}")
chk(ft.manual_exit({"manual_exit_px": 0.0016, "manual_exit_from": 2000}, 0.002788, -1, K) == (None, None), "шорт: до цены дошли раньше, чем её поставили, — выхода нет")
chk(ft.manual_exit({"manual_exit_px": 0.0019, "manual_exit_from": 2000}, 0.002788, -1, K)[0] is not None, "шорт: дошли после того, как цену поставили, — выход")
chk(ft.manual_exit({"manual_exit_px": 0.0025}, 0.002, 1, K)[0] is not None and ft.manual_exit({"manual_exit_px": 0.003}, 0.002, 1, K)[0] is None, "лонг: выход по максимуму")
chk(ft.manual_exit({}, 0.1, -1, K) == (None, None), "нет поля — правило молчит")
# R86: не шортить дно
core_config.MANUAL_BY_USER_SHORT_LOW_DAYS = 60; core_config.MANUAL_BY_USER_SHORT_LOW_PCT = 20
r = ft.short_low_block("AIOTUSDT", -1, px=0.0452, low=0.040)
chk(r and "R86" in r, f"шорт в 13 % над дном должен быть отклонён: {r}")
chk(ft.short_low_block("AIOTUSDT", -1, px=0.0481, low=0.040) is None, "шорт выше уровня «дно + 20 %» проходит")
chk(ft.short_low_block("AIOTUSDT", 1, px=0.0401, low=0.040) is None, "лонгов правило не касается")
core_config.MANUAL_BY_USER_SHORT_LOW_PCT = 0
chk(ft.short_low_block("AIOTUSDT", -1, px=0.0401, low=0.040) is None, "0 % — правило выключено")
core_config.MANUAL_BY_USER_SHORT_LOW_PCT = 20
import os
os.environ["FAST_POT_OFF"] = "1"; os.environ.pop("FAST_SHORT_LOW_OFF", None)
real_block = ft.short_low_block; ft.short_low_block = lambda sym, side, px=None, low=None: real_block(sym, side, px=0.0452, low=0.040)
st = {"open": {}, "last_exit": {}}; ev = []; msgs = []
import time as _t
ok = ft._open_short_now(st, ev, msgs, "AAAUSDT", 0.0452, int(_t.time() * 1000), _t.time(), "R52 вынос → против хода: вынос лонгов 10K$", "всплеск/вынос", False, side=-1)
chk(ok is False and not st["open"] and any("R86" in m for m in msgs), f"общий путь входа открыл шорт у дна: {msgs}")
ft.short_low_block = real_block
print("R85, R86: ок" if not errs else "СБОЙ R85/R86: " + "; ".join(errs))
