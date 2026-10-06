"""R75 (06.10): часы без входов перед сессией (09–11, 15–17) действуют только на лонги — «стыки это сливы, там не шорты нельзя брать, а лонги». Без сети."""
import sys, time
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import core_config as cc
import fast_tier as ft
ok = True
def chk(name, got, want):
    global ok
    if got != want:
        ok = False; print("СБОЙ R75:", name, "получили", got, "ждали", want)
def at(h, m=30):                                             # среда: вне окна без лонгов и не пропускаемый день
    return datetime(2026, 10, 7, h, m, tzinfo=ft.L).timestamp()
def blocked(h, side):
    now = at(h); r = ft.ses_gate(now, int(now * 1000) - 180_000, side)
    return (not r[0]) and "за час до открытия" in str(r[1])
cc.FAST3_NO_ENTRY_HOURS = [(9, 11), (15, 17)]; cc.FAST3_NO_ENTRY_SHORTS_TOO = False
chk("лонг 09:30 — стык, запрет", blocked(9, 1), True)
chk("лонг 15:30 — стык, запрет", blocked(15, 1), True)
chk("шорт 09:30 — стык шорту не запрет", blocked(9, -1), False)
chk("шорт 15:30 — стык шорту не запрет", blocked(15, -1), False)
chk("лонг 13:30 — не стык", blocked(13, 1), False)
cc.FAST3_NO_ENTRY_SHORTS_TOO = True
chk("выключатель: шорт 15:30 снова под запретом", blocked(15, -1), True)
chk("в настройках: шорты в стыках берём", __import__("importlib").reload(cc).FAST3_NO_ENTRY_SHORTS_TOO, False)
chk("в настройках: порог пампа 40", cc.FAST3_PUMP_RISE, 40.0)
chk("в настройках: лондонского порога ×10 нет", cc.FAST3_LONDON_SPIKE_X, 0.0)
import re
_now = at(12); _p = ft.BASE_DIR / "output" / "london_count.json"
_keep = _p.read_text(encoding="utf-8") if _p.exists() else None
ft._oi7 = lambda sym: 1.0
_r = ft.london_gate("AAAUSDT", _now, "всплеск: бар +2% на объёме ×5.2 (100K$)")
if _keep is None:
    _p.unlink(missing_ok=True)
else:
    _p.write_text(_keep, encoding="utf-8")                       # счётчик Лондона возвращаем как был
chk("Лондон 12:30, всплеск ×5.2 — отказа по объёму нет", bool(_r and "всплеск" in _r), False)
import json as _js
def _lg(day, h, n):                                              # счётчик Лондона на этот день = n → что скажет ворота
    _t = datetime(2026, 10, day, h, 30, tzinfo=ft.L).timestamp()
    _p.write_text(_js.dumps({"day": datetime.fromtimestamp(_t, ft.L).strftime("%Y-%m-%d"), "n": n}), encoding="utf-8")
    return ft.london_gate("AAAUSDT", _t, "всплеск: бар +2% на объёме ×5.2 (100K$)")
try:
    chk("понедельник 05.10, Лондон, уже 5 входов — отказ", bool(_lg(5, 12, 5)), True)
    chk("вторник 06.10, Лондон, уже 5 входов — отказ", bool(_lg(6, 12, 5)), True)
    chk("среда 07.10, Лондон, уже 5 входов — ограничения нет", _lg(7, 12, 5), None)
    chk("суббота 10.10, Лондон, уже 9 входов — ограничения нет", _lg(10, 12, 9), None)
    chk("вторник 06.10, 18:30 — не Лондон", _lg(6, 18, 5), None)
finally:
    if _keep is None:
        _p.unlink(missing_ok=True)
    else:
        _p.write_text(_keep, encoding="utf-8")
chk("в настройках: Лондон ограничен в пн и вт", cc.FAST3_LONDON_DAYS, ["пн", "вт"])
print("R75: ок" if ok else "R75: СБОЙ")
