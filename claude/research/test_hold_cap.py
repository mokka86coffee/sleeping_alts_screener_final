"""R74 (06.10): потолок срока позиции 16 ч, исключение — шорт «конец роста» от вершины пампа (pump_end, 3 дня). Чистые функции, без сети."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import core_config as cc
import fast_tier as ft
import fast_state as fs
ok = True
def chk(name, got, want):
    global ok
    if got != want:
        ok = False; print("СБОЙ R74:", name, "получили", got, "ждали", want)
cc.FAST3_MAX_HOLD_MIN = 960
for f, nm in ((ft._hold_lim, "бот"), (fs._hold, "сайт")):
    chk(nm + ": сканер 7 дней → 16 ч", f(dict(hold_min=10080)), 960)
    chk(nm + ": удержанный лонг 24 ч → 16 ч", f(dict(hold_min=1440)), 960)
    chk(nm + ": всплеск 2 ч не меняется", f(dict(hold_min=120)), 120)
    chk(nm + ": сползание 16 ч не меняется", f(dict(hold_min=960, slide=True)), 960)
    chk(nm + ": зона 30–60 % сползания — тоже 16 ч", f(dict(hold_min=4320, slide=True, slide_tp=True)), 960)
    chk(nm + ": шорт «конец роста» — свои 3 дня", f(dict(hold_min=4320, pump_end=True)), 4320)
cc.FAST3_MAX_HOLD_MIN = 0
chk("потолок выключен — срок как записан", ft._hold_lim(dict(hold_min=10080)), 10080)
chk("в настройках: конец роста 3 дня", cc.FAST3_PUMP_END_HOLD_MIN, 4320)
chk("в настройках: зона 2 сползания 16 ч", cc.FAST3_SLIDE_ZONE2_HOLD_MIN, 960)
print("R74: ок" if ok else "R74: СБОЙ")
