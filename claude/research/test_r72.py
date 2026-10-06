"""R72 (06.10): лонг не берём, пока цена не ушла ниже максимума 72 ч хотя бы на FAST3_TOP72_PCT %. Проверка чистой функции _top72_block без сети."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft
ft._slide = lambda sym: (False, False, 0.0)          # без запроса свечей
import core_config as _cc
_cc.FAST3_TOP72_ON = True                             # 06.10: в настройках R72 выключено владельцем — функцию проверяем включённой
ok = True
def chk(name, got, want_block):
    global ok
    if bool(got) != want_block:
        ok = False; print("СБОЙ R72:", name, "получили", repr(got))
ft._SLH["AAAUSDT"] = 100.0
chk("ближе 20% (цена 90) — отказ", ft._top72_block("AAAUSDT", 90.0), True)
chk("у максимума (цена 100) — отказ", ft._top72_block("AAAUSDT", 100.0), True)
chk("выше максимума (цена 105) — отказ", ft._top72_block("AAAUSDT", 105.0), True)
chk("глубже 20% (цена 75) — можно", ft._top72_block("AAAUSDT", 75.0), False)
chk("чуть ближе 20% (цена 80.5) — отказ", ft._top72_block("AAAUSDT", 80.5), True)
chk("чуть глубже 20% (цена 79.5) — можно", ft._top72_block("AAAUSDT", 79.5), False)
chk("нет данных — не блокируем", ft._top72_block("ZZZUSDT", 50.0), False)
chk("нет цены — не блокируем", ft._top72_block("AAAUSDT", 0.0), False)
_cc.FAST3_TOP72_ON = False
chk("выключено в настройках — не блокируем", ft._top72_block("AAAUSDT", 100.0), False)
print("R72: ок" if ok else "R72: СБОЙ")
