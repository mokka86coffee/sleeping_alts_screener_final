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
print("R85: ок" if not errs else "СБОЙ R85: " + "; ".join(errs))
